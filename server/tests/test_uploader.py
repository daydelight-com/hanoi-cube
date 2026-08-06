"""クラウドアップローダのテスト(契約: firestore.md §1、仕様§3.2-1 オフライン耐性)。"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from app.cloud.uploader import Uploader, make_sink, play_document
from app.core.precompute import PrecomputeTable, load_table
from app.state.sqlite_store import SqliteStore
from app.state.store import PlayRecord

from tests.test_sqlite_store import make_play
from tests.test_state_machine import SCORED_BOARD, SCORED_POINTS, Driver, sent


@pytest.fixture(scope="module")
def table() -> PrecomputeTable:
    return load_table()


@pytest.fixture
def store() -> Iterator[SqliteStore]:
    s = SqliteStore(":memory:")
    yield s
    s.close()


class FakeSink:
    """失敗回数を指定できるアップロード先。"""

    def __init__(self, fail_times: int = 0) -> None:
        self.fail_times = fail_times
        self.uploaded: list[str] = []

    def upload(self, record: PlayRecord) -> None:
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("offline")
        self.uploaded.append(record.play_id)


def test_play_document_matches_contract() -> None:
    # firestore.md §1 のドキュメント形(ドキュメントIDは play_id なので本体に含まれない)
    doc = play_document(make_play())
    assert doc == {
        "player_name": "たろう",
        "score": 60,
        "fail_count": 0,
        "played_at": "2026-08-21T10:00:00+09:00",
        "judgements": [
            {
                "seq": 1,
                "board": "L/MS/L",
                "elapsed_ms": 12_345,
                "result": "scored",
                "points": 60,
                "min_moves": 15,
                "dup_of_seq": None,
                "tower_box_ids": {"a": ["large-1"], "b": ["medium-1", "small-1"], "c": ["large-2"]},
            },
            {
                "seq": 2,
                "board": "LMS/MS/L",
                "elapsed_ms": 30_000,
                "result": "unclearable",
                "points": 0,
                "min_moves": None,
                "dup_of_seq": None,
                "tower_box_ids": {
                    "a": ["large-1", "medium-1", "small-1"],
                    "b": ["medium-2", "small-2"],
                    "c": ["large-2"],
                },
            },
            {
                "seq": 3,
                "board": "L/MS/L",
                "elapsed_ms": 50_000,
                "result": "duplicate_same",
                "points": 0,
                "min_moves": 15,
                "dup_of_seq": 1,
                "tower_box_ids": {"a": ["large-2"], "b": ["medium-1", "small-1"], "c": ["large-1"]},
            },
        ],
    }
    # JSON化可能な素の型のみで構成される(Admin SDKにそのまま渡せる)
    assert isinstance(doc["judgements"], list)


def test_process_once_uploads_in_order(store: SqliteStore) -> None:
    store.save_play(make_play("p-2", played_at="2026-08-21T11:00:00+09:00"))
    store.save_play(make_play("p-1", played_at="2026-08-21T10:00:00+09:00"))
    sink = FakeSink()
    uploaded, remaining = Uploader(store, sink).process_once()
    assert (uploaded, remaining) == (2, 0)
    assert sink.uploaded == ["p-1", "p-2"]
    assert store.pending_uploads() == []


def test_process_once_keeps_queue_on_failure(store: SqliteStore) -> None:
    store.save_play(make_play("p-1", played_at="2026-08-21T10:00:00+09:00"))
    store.save_play(make_play("p-2", played_at="2026-08-21T11:00:00+09:00"))
    sink = FakeSink(fail_times=1)
    uploaded, remaining = Uploader(store, sink).process_once()
    assert (uploaded, remaining) == (0, 2)  # 先頭で失敗したらその周は打ち切り(順序維持)
    assert [p.play_id for p in store.pending_uploads()] == ["p-1", "p-2"]

    uploaded, remaining = Uploader(store, sink).process_once()  # 復旧後に再試行
    assert (uploaded, remaining) == (2, 0)
    assert sink.uploaded == ["p-1", "p-2"]


def test_offline_play_does_not_stop_game(table: PrecomputeTable, store: SqliteStore) -> None:
    """オフライン(アップロード常時失敗)でもプレイ→保存→ランキング表示が通る(DoD)。"""
    sink = FakeSink(fail_times=10**9)
    uploader = Uploader(store, sink)
    d = Driver(table, store)

    d.to_game_play()
    d.set_board(SCORED_BOARD)
    d.press("enter")
    uploader.process_once()  # プレイ中の失敗もゲーム状態に影響しない
    d.advance(60_000)
    assert d.screen == "result"
    d.machine.on_name_text("たろう", d.now)
    d.machine.on_name_done(d.now)
    out = d.press("enter")  # 保存+キュー投入
    assert d.screen == "ranking"
    entries = sent(out, "ranking")[-1].payload["entries"]
    assert entries[0]["score"] == SCORED_POINTS  # ローカルランキングは即時反映

    uploaded, remaining = uploader.process_once()
    assert (uploaded, remaining) == (0, 1)  # 未送信のままキューに残る

    sink.fail_times = 0  # 復旧したら再試行で送れる
    uploaded, remaining = uploader.process_once()
    assert (uploaded, remaining) == (1, 0)
    assert store.pending_uploads() == []


def test_run_loop_uploads_pending(store: SqliteStore) -> None:
    store.save_play(make_play("p-1"))
    sink = FakeSink()
    uploader = Uploader(store, sink, interval_s=0.01)

    async def scenario() -> None:
        task = asyncio.create_task(uploader.run())
        try:
            for _ in range(100):
                if sink.uploaded:
                    break
                await asyncio.sleep(0.01)
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(scenario())
    assert sink.uploaded == ["p-1"]


def test_make_sink_disabled_without_config() -> None:
    # conftest が関連環境変数を除去済み → クラウド連携なし(ゲームはローカルのみで動く)
    assert make_sink() is None
