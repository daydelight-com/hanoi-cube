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
        with client.websocket_connect("/ws/controller") as controller:
            msg = controller.receive_json()
            assert msg["type"] == "snapshot"
            assert msg["payload"] == {
                "screen": "idle_title",
                "lang": "ja",
                "input_mode": "buttons",
                "name_text": "",
            }


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


def test_mock_endpoint_rejects_bad_board() -> None:
    with TestClient(create_app(start_loop=False)) as client:
        res = client.post("/api/mock/board", json={"board": "LLLL//"})
        assert res.status_code == 400


def test_mock_endpoints_disabled_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HANOI_MOCK_API", "0")
    with TestClient(create_app(start_loop=False)) as client:
        res = client.post("/api/mock/board", json={"board": "L/MS/L"})
        assert res.status_code == 403


def test_api_ranking_empty() -> None:
    with TestClient(create_app(start_loop=False)) as client:
        assert client.get("/api/ranking").json() == {"entries": []}
