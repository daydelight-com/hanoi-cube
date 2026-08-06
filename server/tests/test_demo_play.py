"""全パターンデモ記録のテスト(app/cloud/demo_play.py)。

DoD: 全512盤面が過不足なく1回ずつ入り、並びが「得点降順 → 鏡像重複 → クリア不可」で
あること。得点・失敗数が判定エンジンと一致し、Firestore ドキュメント形に載ること。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from app.cloud.demo_play import (
    DEFAULT_PLAY_ID,
    PlaysSink,
    build_all_patterns_play,
    ordered_boards,
    run_cli,
    tower_box_ids,
)
from app.cloud.uploader import play_document
from app.core.board import box_count, canonical_key, mirror_board
from app.core.precompute import load_table
from app.state.store import PlayRecord

TABLE = load_table()
RECORD = build_all_patterns_play(table=TABLE)


def test_covers_all_512_boards_exactly_once() -> None:
    boards = [j.board for j in RECORD.judgements]
    assert len(boards) == 512
    assert len(set(boards)) == 512
    assert {e.board for e in TABLE.boards} == set(boards)


def test_seq_and_elapsed_are_monotonic_within_play_time() -> None:
    assert [j.seq for j in RECORD.judgements] == list(range(1, 513))
    elapsed = [j.elapsed_ms for j in RECORD.judgements]
    assert elapsed == sorted(elapsed)
    assert elapsed[0] >= 0 and elapsed[-1] < 60_000


def test_order_is_scored_desc_then_mirrors_then_unclearable() -> None:
    results = [j.result for j in RECORD.judgements]
    # duplicate_same は起きない(同じ盤面文字列を2回置かないため)
    assert "duplicate_same" not in results
    first_dup = results.index("duplicate_mirror")
    first_fail = results.index("unclearable")
    assert set(results[:first_dup]) == {"scored"}
    assert set(results[first_dup:first_fail]) == {"duplicate_mirror"}
    assert set(results[first_fail:]) == {"unclearable"}  # 失敗パターンは最後
    scored_points = [j.points for j in RECORD.judgements[:first_dup]]
    assert scored_points == sorted(scored_points, reverse=True)
    assert len(scored_points) == 124  # docs/game/score_ranking.md のクラス数


def test_scored_boards_are_canonical_keys_and_mirrors_follow_them() -> None:
    by_seq = {j.seq: j for j in RECORD.judgements}
    for j in RECORD.judgements:
        if j.result == "scored":
            assert j.board == canonical_key(j.board)
            assert j.points == box_count(j.board) * TABLE.entry(j.board).min_moves  # type: ignore[operator]
            assert j.dup_of_seq is None
        elif j.result == "duplicate_mirror":
            assert j.points == 0
            origin = by_seq[j.dup_of_seq]  # type: ignore[index]
            assert origin.result == "scored"
            assert origin.board == mirror_board(j.board)
        else:
            assert (j.points, j.min_moves, j.dup_of_seq) == (0, None, None)


def test_totals_match_judgements() -> None:
    assert RECORD.score == sum(j.points for j in RECORD.judgements)
    assert RECORD.fail_count == sum(1 for j in RECORD.judgements if j.result == "unclearable")
    assert RECORD.score > 0 and RECORD.fail_count > 0
    assert 1 <= len(RECORD.name) <= 10


def test_rejects_out_of_range_name() -> None:
    with pytest.raises(ValueError, match="player_name"):
        build_all_patterns_play(table=TABLE, name="")
    with pytest.raises(ValueError, match="player_name"):
        build_all_patterns_play(table=TABLE, name="あ" * 11)
    logs: list[str] = []
    assert run_cli(["--name", "あ" * 11], print_fn=logs.append) == 2
    assert any("player_name" in line for line in logs)


def test_ordered_boards_is_deterministic() -> None:
    assert ordered_boards(TABLE) == ordered_boards(TABLE)


def test_tower_box_ids_match_board_sizes() -> None:
    assert tower_box_ids("LMS//L") == (["large-1", "medium-1", "small-1"], [], ["large-2"])
    for j in RECORD.judgements:
        ids = j.tower_box_ids
        flat = [box for tower in ids for box in tower]
        assert len(set(flat)) == len(flat)  # 個体の重複割り当てなし
        sizes = "/".join("".join(box[0].upper() for box in tower) for tower in ids)
        assert sizes == j.board  # サイズ列は盤面と一致(cv-interface.md §3)


def test_play_document_shape() -> None:
    doc = play_document(RECORD)
    assert doc["player_name"] == RECORD.name
    assert len(doc["judgements"]) == 512
    assert set(doc["judgements"][0]["tower_box_ids"]) == {"a", "b", "c"}
    json.dumps(doc, ensure_ascii=False)  # Firestore に載る前にJSON化できること


def test_cli_out_writes_json_without_uploading(tmp_path: Path) -> None:
    out = tmp_path / "play.json"
    logs: list[str] = []

    def fail_sink() -> PlaysSink:  # 投入経路に入ったら失敗させる
        raise AssertionError("--out では投入しない")

    code = run_cli(
        ["--out", str(out)],
        sink_factory=fail_sink,
        input_fn=lambda _: "yes",
        print_fn=logs.append,
    )
    assert code == 0
    doc = json.loads(out.read_text(encoding="utf-8"))
    assert len(doc["judgements"]) == 512
    assert any("書き出しました" in line for line in logs)


def test_cli_aborts_without_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    logs: list[str] = []

    def fail_sink() -> PlaysSink:
        raise AssertionError("中止時は投入しない")

    code = run_cli(
        [],
        sink_factory=fail_sink,
        input_fn=lambda _: "no",
        print_fn=logs.append,
    )
    assert code == 1
    assert any("中止" in line for line in logs)


def test_cli_uploads_on_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    uploaded: list[PlayRecord] = []

    class FakeSink:
        def upload(self, record: PlayRecord) -> None:
            uploaded.append(record)

    code = run_cli(
        [],
        sink_factory=FakeSink,
        input_fn=lambda _: "yes",
        print_fn=lambda _: None,
    )
    assert code == 0
    assert [r.play_id for r in uploaded] == [DEFAULT_PLAY_ID]
    assert len(uploaded[0].judgements) == 512


def test_cli_errors_without_cloud_config(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in (
        "FIRESTORE_EMULATOR_HOST",
        "HANOI_FIREBASE_CREDENTIALS",
        "GOOGLE_APPLICATION_CREDENTIALS",
    ):
        monkeypatch.delenv(var, raising=False)
    logs: list[str] = []
    code = run_cli([], input_fn=lambda _: "yes", print_fn=logs.append)
    assert code == 2
    assert any("接続設定がありません" in line for line in logs)
