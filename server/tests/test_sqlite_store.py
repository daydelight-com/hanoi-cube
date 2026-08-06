"""SQLiteストアのテスト(仕様§7.1、順序規則は firestore.md §2)。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from app.state.sqlite_store import SqliteStore
from app.state.store import JudgementRecord, PlayRecord


def make_play(
    play_id: str = "play-1",
    *,
    name: str = "たろう",
    score: int = 60,
    fail_count: int = 0,
    played_at: str = "2026-08-21T10:00:00+09:00",
    with_judgements: bool = True,
) -> PlayRecord:
    judgements = []
    if with_judgements:
        judgements = [
            JudgementRecord(
                seq=1,
                board="L/MS/L",
                elapsed_ms=12_345,
                result="scored",
                points=60,
                min_moves=15,
                dup_of_seq=None,
                tower_box_ids=(["large-1"], ["medium-1", "small-1"], ["large-2"]),
            ),
            JudgementRecord(
                seq=2,
                board="LMS/MS/L",
                elapsed_ms=30_000,
                result="unclearable",
                points=0,
                min_moves=None,
                dup_of_seq=None,
                tower_box_ids=(
                    ["large-1", "medium-1", "small-1"],
                    ["medium-2", "small-2"],
                    ["large-2"],
                ),
            ),
            JudgementRecord(
                seq=3,
                board="L/MS/L",
                elapsed_ms=50_000,
                result="duplicate_same",
                points=0,
                min_moves=15,
                dup_of_seq=1,
                tower_box_ids=(["large-2"], ["medium-1", "small-1"], ["large-1"]),
            ),
        ]
    return PlayRecord(
        play_id=play_id,
        name=name,
        score=score,
        fail_count=fail_count,
        played_at=played_at,
        judgements=judgements,
    )


@pytest.fixture
def store() -> Iterator[SqliteStore]:
    s = SqliteStore(":memory:")
    yield s
    s.close()


def test_save_and_load_roundtrip(store: SqliteStore) -> None:
    record = make_play()
    store.save_play(record)
    assert store.play("play-1") == record
    assert store.play("unknown") is None


def test_ranking_order_and_provisional_rank(store: SqliteStore) -> None:
    # スコア降順 → 失敗数昇順 → played_at昇順(先着)
    store.save_play(
        make_play("p-low", score=10, fail_count=0, played_at="2026-08-21T10:00:00+09:00")
    )
    store.save_play(
        make_play("p-late", score=60, fail_count=1, played_at="2026-08-21T12:00:00+09:00")
    )
    store.save_play(
        make_play("p-clean", score=60, fail_count=0, played_at="2026-08-21T13:00:00+09:00")
    )
    store.save_play(
        make_play("p-early", score=60, fail_count=1, played_at="2026-08-21T11:00:00+09:00")
    )
    entries = store.ranking()
    assert [e.play_id for e in entries] == ["p-clean", "p-early", "p-late", "p-low"]
    assert [e.rank for e in entries] == [1, 2, 3, 4]

    # 暫定順位: 同点同失敗の既存プレイは先勝ちで上に付く(MemoryStore と同じ規則)
    assert store.provisional_rank(100, 0) == 1
    assert store.provisional_rank(60, 0) == 2
    assert store.provisional_rank(60, 1) == 4
    assert store.provisional_rank(0, 9) == 5


def test_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "plays.sqlite3"
    store = SqliteStore(path)
    store.save_play(make_play())
    store.mark_uploaded("play-1")
    store.close()

    reopened = SqliteStore(path)
    try:
        assert reopened.play("play-1") == make_play()
        assert reopened.pending_uploads() == []  # uploaded=1 も永続化されている
    finally:
        reopened.close()


def test_save_play_is_idempotent_replace(store: SqliteStore) -> None:
    store.save_play(make_play())
    store.mark_uploaded("play-1")
    updated = make_play(name="じろう", with_judgements=False)
    store.save_play(updated)  # 同一IDの再保存は全置換+再アップロード対象に戻る
    assert store.play("play-1") == updated
    assert len(store.ranking()) == 1
    assert [p.play_id for p in store.pending_uploads()] == ["play-1"]


def test_upload_queue_order_and_mark(store: SqliteStore) -> None:
    store.save_play(make_play("p-2", played_at="2026-08-21T11:00:00+09:00"))
    store.save_play(make_play("p-1", played_at="2026-08-21T10:00:00+09:00"))
    assert [p.play_id for p in store.pending_uploads()] == ["p-1", "p-2"]  # 保存時刻順

    store.mark_uploaded("p-1")
    assert [p.play_id for p in store.pending_uploads()] == ["p-2"]
    store.mark_uploaded("p-2")
    assert store.pending_uploads() == []
