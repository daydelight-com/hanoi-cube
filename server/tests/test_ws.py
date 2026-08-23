"""WS配信・スナップショット復元・モックCV接続のテスト(ws-messages.md)。

状態遷移の網羅は test_state_machine.py が担う。ここではAPI層の配線
(接続直後の snapshot、ボタン中継、切断→再接続での復元、CVループ)を検証する。
"""

from __future__ import annotations

from typing import Any

import pytest
from app.api.main import create_app
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession


def recv_until(ws: WebSocketTestSession, type_: str, *, limit: int = 200) -> dict[str, Any]:
    """boxes 等の高頻度メッセージを読み飛ばして目的の type を待つ。"""
    for _ in range(limit):
        msg = ws.receive_json()
        assert isinstance(msg, dict)
        if msg["type"] == type_:
            return msg
    raise AssertionError(f"no {type_!r} message within {limit} messages")


def test_display_and_controller_snapshot_on_connect() -> None:
    with TestClient(create_app(start_loop=False)) as client:
        with client.websocket_connect("/ws/display") as display:
            msg = display.receive_json()
            assert msg["type"] == "snapshot"
            assert msg["payload"]["screen"] == "idle_title"
            assert msg["payload"]["lang"] == "ja"
            assert msg["payload"]["board"] is None
            assert msg["payload"]["camera_side"] == "back"  # 既定(ws-messages.md §3)
        with client.websocket_connect("/ws/controller") as controller:
            msg = controller.receive_json()
            assert msg["type"] == "snapshot"
            assert msg["payload"] == {
                "screen": "idle_title",
                "lang": "ja",
                "input_mode": "buttons",
                "name_text": "",
            }


def test_display_snapshot_camera_side_front(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HANOI_CAMERA_SIDE", "front")
    with (
        TestClient(create_app(start_loop=False)) as client,
        client.websocket_connect("/ws/display") as display,
    ):
        assert display.receive_json()["payload"]["camera_side"] == "front"


def test_camera_side_invalid_falls_back_to_back(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("HANOI_CAMERA_SIDE", "left")
    with (
        caplog.at_level("WARNING", logger="app.api.main"),
        TestClient(create_app(start_loop=False)) as client,
        client.websocket_connect("/ws/display") as display,
    ):
        assert display.receive_json()["payload"]["camera_side"] == "back"
    assert any("HANOI_CAMERA_SIDE" in rec.message for rec in caplog.records)


def test_button_relays_to_display_and_snapshot_restores_after_reconnect() -> None:
    with TestClient(create_app(start_loop=False)) as client:
        with (
            client.websocket_connect("/ws/display") as display,
            client.websocket_connect("/ws/controller") as controller,
        ):
            assert display.receive_json()["type"] == "snapshot"
            assert controller.receive_json()["type"] == "snapshot"
            controller.send_json({"type": "button", "payload": {"button": "enter"}})
            msg = recv_until(display, "screen")
            assert msg["payload"]["screen"] == "mode_select"
        # 切断→再接続: snapshot だけで mode_select が復元される(DoD)
        with client.websocket_connect("/ws/display") as display:
            msg = display.receive_json()
            assert msg["type"] == "snapshot"
            assert msg["payload"]["screen"] == "mode_select"
            assert msg["payload"]["ctx"] == {"focus": "rules"}
        with client.websocket_connect("/ws/controller") as controller:
            assert controller.receive_json()["payload"]["screen"] == "mode_select"


def test_unknown_and_malformed_messages_ignored() -> None:
    with (
        TestClient(create_app(start_loop=False)) as client,
        client.websocket_connect("/ws/display") as display,
        client.websocket_connect("/ws/controller") as controller,
    ):
        display.receive_json()
        controller.receive_json()
        controller.send_json({"type": "nope", "payload": {}})  # 未知typeは無視
        controller.send_json({"type": "button", "payload": {"button": "quit"}})  # 不正payload
        controller.send_json({"type": "button", "payload": {"button": "enter"}})
        msg = recv_until(display, "screen")
        assert msg["payload"]["screen"] == "mode_select"


def test_cv_loop_streams_boxes_and_board() -> None:
    with (
        TestClient(create_app(start_loop=True)) as client,
        client.websocket_connect("/ws/display") as display,
    ):
        # 初期盤面(全箱待機)はループが先に処理していることがあるため、
        # snapshot か board メッセージのどちらかで届けばよい
        snapshot = display.receive_json()
        assert snapshot["type"] == "snapshot"
        if snapshot["payload"]["board"] is None:
            board = recv_until(display, "board")
            assert board["payload"]["board"] == "//"
            assert "kind" not in board["payload"]
        else:
            assert snapshot["payload"]["board"]["board"] == "//"
        boxes = recv_until(display, "boxes")
        assert len(boxes["payload"]["boxes"]) == 9
        # 開発用エンドポイントでモック盤面を変更 → board が配信される
        res = client.post("/api/mock/board", json={"board": "L/MS/L"})
        assert res.status_code == 200
        board = recv_until(display, "board")
        assert board["payload"]["board"] == "L/MS/L"
        assert board["payload"]["legal"] is True
        # 箱の個体もWS境界を越えて配信される(ws-messages.md §1。TS写しでは必須フィールド)
        assert board["payload"]["tower_box_ids"] == [
            ["large-1"],
            ["medium-1", "small-1"],
            ["large-2"],
        ]


def test_mock_endpoint_rejects_bad_board() -> None:
    with TestClient(create_app(start_loop=False)) as client:
        res = client.post("/api/mock/board", json={"board": "LLLL//"})
        assert res.status_code == 400


def test_mock_move_endpoint_applies_a_legal_move() -> None:
    with TestClient(create_app(start_loop=False)) as client:
        res = client.post("/api/mock/move", json={"box_id": "large-1", "target": "A"})
        assert res.status_code == 200
        server = client.app.state.game
        assert server.cv.last_board is not None
        assert server.cv.last_board.board == "L//"


def test_mock_endpoints_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HANOI_MOCK_API", "0")
    with TestClient(create_app(start_loop=False)) as client:
        res = client.post("/api/mock/board", json={"board": "L/MS/L"})
        assert res.status_code == 403


class _StubCv:
    """CvSource 準拠のスタブ(実CV選択のテストでワーカーを起動させないため)。"""

    def poll(self) -> list[Any]:
        return []


def test_make_cv_selects_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.cv.real
    from app.api.main import _make_cv
    from app.cv.mock import MockCv

    monkeypatch.setattr(app.cv.real, "RealCv", _StubCv)
    monkeypatch.delenv("HANOI_CV", raising=False)  # conftest の mock 常設を外して既定を踏む
    assert isinstance(_make_cv(), _StubCv)  # 既定は実CV
    monkeypatch.setenv("HANOI_CV", "mock")
    assert isinstance(_make_cv(), MockCv)  # モックは縮退経路として維持(CLAUDE.md 規則6)
    monkeypatch.setenv("HANOI_CV", "real")
    assert isinstance(_make_cv(), _StubCv)


def test_mock_endpoints_conflict_when_cv_is_real() -> None:
    app = create_app(start_loop=False)
    with TestClient(app) as client:
        app.state.game.cv = _StubCv()  # 実CV相当に差し替え
        res = client.post("/api/mock/board", json={"board": "L/MS/L"})
        assert res.status_code == 409


def test_api_ranking_empty() -> None:
    with TestClient(create_app(start_loop=False)) as client:
        assert client.get("/api/ranking").json() == {"entries": []}
