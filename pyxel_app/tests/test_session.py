"""session のテスト。

既存 StateMachine との照合(計画書 §7)、タイムアップ境界、クールダウン、時間表示。
"""

from __future__ import annotations

import random
from itertools import count, pairwise
from typing import cast

import pytest

from app.core.engine import Judgement
from app.core.precompute import PrecomputeTable, load_table
from app.cv.interface import BoxId, CvBoardUpdate
from app.state.machine import GAME_MS, JUDGE_COOLDOWN_MS, StateMachine
from app.state.store import MemoryStore
from session import (
    COUNTDOWN_STEPS,
    GAME_SEC,
    JUDGE_COOLDOWN_SEC,
    GameSession,
    JudgeRejection,
    Phase,
    SessionEvent,
)

# S1 テスト済みの検証値(server/tests/test_state_machine.py と同じ)
SCORED_BOARD = "L/MS/L"
SCORED_POINTS = 60
MIRROR_A = "LMS//"
MIRROR_A_POINTS = 21
MIRROR_B = "//LMS"
UNCLEARABLE_BOARD = "LMS/MS/L"

_BOX_NAME = {"L": "large", "M": "medium", "S": "small"}


@pytest.fixture(scope="module")
def table() -> PrecomputeTable:
    return load_table()


def board_update(board: str, t_ms: int) -> CvBoardUpdate:
    towers = board.split("/")
    serial = {"L": 0, "M": 0, "S": 0}

    def box_ids(tower: str) -> list[BoxId]:
        ids = []
        for size in tower:
            serial[size] += 1
            ids.append(cast(BoxId, f"{_BOX_NAME[size]}-{serial[size]}"))
        return ids

    a, b, c = towers
    return CvBoardUpdate(
        t_ms=t_ms,
        towers=(a, b, c),
        board=board,
        legal=True,
        tower_box_ids=(box_ids(a), box_ids(b), box_ids(c)),
    )


class MachineDriver:
    """既存 StateMachine を game_play まで進め、判定列を流す(照合の相手)。"""

    def __init__(self, table: PrecomputeTable) -> None:
        ids = count(1)
        self.machine = StateMachine(
            table, MemoryStore(), now_ms=0, id_factory=lambda: f"play-{next(ids)}"
        )
        m = self.machine
        m.on_button("enter", 0)  # idle_title → mode_select
        m.on_button("right", 0)
        m.on_button("right", 0)  # focus=game
        m.on_button("enter", 0)  # game_countdown
        m.tick(3_000)  # 3→2→1→GO。play_start_ms = 3000
        assert m.screen == "game_play"
        self.play_start_ms = 3_000

    def judge(self, board: str, elapsed_ms: int) -> tuple[str, int] | None:
        """判定結果 (result, points)。受け付けられなければ None。"""
        now = self.play_start_ms + elapsed_ms
        self.machine.tick(now)
        if self.machine.screen != "game_play":
            return None
        self.machine.on_cv_message(board_update(board, now), now)
        out = self.machine.on_button("enter", now)
        judged = [o for o in out if o.type == "judge"]
        if not judged:
            return None
        payload = judged[0].payload
        return (payload["result"], payload["points"])

    def snapshot(self) -> tuple[int, int, set[str], set[str], int]:
        m = self.machine
        return (m._score, m._fail_count, set(m._judged_keys), set(m._judged_boards), m._seq)


def started(table: PrecomputeTable, at: float = 100.0) -> tuple[GameSession, float]:
    """カウントダウンを終えてプレイ開始直後のセッションと開始時刻。"""
    s = GameSession(table)
    s.start(at)
    t0 = at + s.countdown_sec
    assert s.phase(t0) is Phase.PLAYING
    return s, t0


def as_judgement(result: Judgement | JudgeRejection) -> Judgement:
    assert isinstance(result, Judgement), result
    return result


# ---- StateMachine との照合 ----


def test_matches_state_machine_for_fixed_sequence(table: PrecomputeTable) -> None:
    sequence = [
        (SCORED_BOARD, 1_000),
        (SCORED_BOARD, 2_000),  # duplicate_same
        (MIRROR_A, 3_000),
        (MIRROR_B, 4_000),  # duplicate_mirror
        (UNCLEARABLE_BOARD, 5_000),
        (UNCLEARABLE_BOARD, 5_200),  # クールダウン中 → 両方とも無視
        (UNCLEARABLE_BOARD, 6_000),  # 2 回目の失敗
        ("L/M/S", 7_000),
    ]
    machine = MachineDriver(table)
    session, t0 = started(table)
    for board, elapsed_ms in sequence:
        expected = machine.judge(board, elapsed_ms)
        actual = session.judge(board, t0 + elapsed_ms / 1000)
        if expected is None:
            assert isinstance(actual, JudgeRejection), (board, elapsed_ms)
        else:
            j = as_judgement(actual)
            assert (j.result, j.points) == expected, (board, elapsed_ms)
    score, fails, keys, boards, seq = machine.snapshot()
    assert session.score == score == SCORED_POINTS + MIRROR_A_POINTS + 9  # L/M/S = 3 箱 * 3 手
    assert session.fail_count == fails == 2
    assert session.judged_keys == keys
    assert session.judged_boards == boards
    assert session.judge_count == seq == 7


@pytest.mark.parametrize("seed", range(20))
def test_matches_state_machine_for_random_sequences(table: PrecomputeTable, seed: int) -> None:
    """ランダムな合法盤面列(クールダウン・タイムアップを跨ぐ間隔)で集計が一致する。"""
    rng = random.Random(seed)
    boards = [e.board for e in table.boards]
    machine = MachineDriver(table)
    session, t0 = started(table)
    elapsed_ms = 0
    accepted = 0
    while elapsed_ms < GAME_MS + 2_000:
        board = rng.choice(boards)
        expected = machine.judge(board, elapsed_ms)
        actual = session.judge(board, t0 + elapsed_ms / 1000)
        if expected is None:
            assert isinstance(actual, JudgeRejection), (seed, board, elapsed_ms)
        else:
            j = as_judgement(actual)
            assert (j.result, j.points) == expected, (seed, board, elapsed_ms)
            accepted += 1
        elapsed_ms += rng.choice((100, 300, 499, 500, 501, 700, 1_500, 3_000))
    score, fails, keys, boards_seen, seq = machine.snapshot()
    assert session.score == score
    assert session.fail_count == fails
    assert session.judged_keys == keys
    assert session.judged_boards == boards_seen
    assert session.judge_count == seq == accepted
    assert accepted > 10


def test_apply_rules_scored_duplicate_unclearable(table: PrecomputeTable) -> None:
    session, t0 = started(table)
    j = as_judgement(session.judge(SCORED_BOARD, t0))
    assert j.result == "scored" and j.points == SCORED_POINTS
    assert session.judged_boards == {SCORED_BOARD} and session.judged_keys == {j.canonical_key}
    j = as_judgement(session.judge(UNCLEARABLE_BOARD, t0 + 1))
    assert j.result == "unclearable" and session.fail_count == 1 and session.score == SCORED_POINTS
    assert session.judged_boards == {SCORED_BOARD}  # 失敗は集合に入らない
    j = as_judgement(session.judge(MIRROR_A, t0 + 2))
    assert j.result == "scored"
    j = as_judgement(session.judge(MIRROR_B, t0 + 3))
    assert j.result == "duplicate_mirror" and j.points == 0
    assert MIRROR_B in session.judged_boards  # duplicate も生盤面集合へ
    j = as_judgement(session.judge(MIRROR_B, t0 + 4))
    assert j.result == "duplicate_same"
    assert session.score == SCORED_POINTS + MIRROR_A_POINTS
    assert session.fail_count == 1 and session.judge_count == 5


def test_illegal_board_is_rejected_without_side_effects(table: PrecomputeTable) -> None:
    session, t0 = started(table)
    assert session.judge("SL//", t0) is JudgeRejection.ILLEGAL_BOARD
    assert session.judge_count == 0 and session.cooldown_remaining(t0) == 0.0


# ---- タイムアップ境界 ----


def test_judge_just_before_deadline_is_valid_and_at_deadline_is_not(
    table: PrecomputeTable,
) -> None:
    session, t0 = started(table)
    deadline = t0 + GAME_SEC
    assert session.deadline == deadline
    j = as_judgement(session.judge(SCORED_BOARD, deadline - 1e-3))
    assert j.result == "scored" and session.score == SCORED_POINTS
    assert session.phase(deadline - 1e-3) is Phase.PLAYING
    # 直前の判定は有効だがクールダウンより先にタイムアップが効く
    assert session.judge(MIRROR_A, deadline) is JudgeRejection.TIME_UP
    assert session.judge(MIRROR_A, deadline + 5.0) is JudgeRejection.TIME_UP
    assert session.phase(deadline) is Phase.FINISHED and session.is_over(deadline)
    assert session.score == SCORED_POINTS and session.judge_count == 1


def test_judge_during_countdown_is_rejected(table: PrecomputeTable) -> None:
    session = GameSession(table)
    assert session.judge(SCORED_BOARD, 0.0) is JudgeRejection.NOT_PLAYING  # start 前
    session.start(10.0)
    assert session.judge(SCORED_BOARD, 10.0) is JudgeRejection.NOT_PLAYING
    assert session.judge(SCORED_BOARD, 12.999) is JudgeRejection.NOT_PLAYING
    assert as_judgement(session.judge(SCORED_BOARD, 13.0)).result == "scored"  # GO と同時は有効


# ---- クールダウン ----


def test_cooldown_blocks_then_allows(table: PrecomputeTable) -> None:
    assert JUDGE_COOLDOWN_SEC == JUDGE_COOLDOWN_MS / 1000
    session, t0 = started(table)
    as_judgement(session.judge(SCORED_BOARD, t0))
    assert session.judge(MIRROR_A, t0 + 0.3) is JudgeRejection.COOLDOWN
    assert session.cooldown_remaining(t0 + 0.3) == pytest.approx(0.2)
    assert session.judge(MIRROR_A, t0 + 0.499) is JudgeRejection.COOLDOWN
    assert as_judgement(session.judge(MIRROR_A, t0 + 0.5)).result == "scored"
    assert session.judge_count == 2
    # 拒否された判定はクールダウンを延長しない
    assert session.cooldown_remaining(t0 + 1.0) == 0.0


def test_rejected_judge_does_not_count(table: PrecomputeTable) -> None:
    session, t0 = started(table)
    as_judgement(session.judge(UNCLEARABLE_BOARD, t0))
    session.judge(UNCLEARABLE_BOARD, t0 + 0.1)
    assert session.fail_count == 1 and session.judge_count == 1


# ---- 時間・フェーズ・イベント ----


def test_countdown_values_and_events(table: PrecomputeTable) -> None:
    session = GameSession(table)
    assert session.poll(0.0) == []
    session.start(10.0)
    assert COUNTDOWN_STEPS == 3
    assert session.countdown_value(10.0) == 3
    assert session.countdown_value(10.999) == 3
    assert session.countdown_value(11.0) == 2
    assert session.countdown_value(12.0) == 1
    assert session.countdown_value(12.999) == 1
    assert session.countdown_value(13.0) is None
    assert session.poll(10.0) == [SessionEvent.COUNTDOWN_TICK]
    assert session.poll(10.5) == []
    assert session.poll(11.0) == [SessionEvent.COUNTDOWN_TICK]
    assert session.poll(12.0) == [SessionEvent.COUNTDOWN_TICK]
    assert session.poll(13.0) == [SessionEvent.GO]
    assert session.show_go(13.0) and session.show_go(13.9) and not session.show_go(14.0)
    assert session.poll(13.5) == []
    assert session.poll(73.0) == [SessionEvent.TIME_UP]
    assert session.poll(74.0) == []


def test_poll_catches_up_after_a_long_stall(table: PrecomputeTable) -> None:
    """処理落ちで数秒飛んでも GO / TIME_UP は 1 回ずつ出る(カウントダウンの段は最後だけ)。"""
    session = GameSession(table)
    session.start(0.0)
    assert session.poll(0.0) == [SessionEvent.COUNTDOWN_TICK]
    assert session.poll(2.5) == [SessionEvent.COUNTDOWN_TICK]  # 「1」
    assert session.poll(70.0) == [SessionEvent.GO, SessionEvent.TIME_UP]


def test_remaining_display_ceils_to_seconds(table: PrecomputeTable) -> None:
    session = GameSession(table)
    assert session.remaining_display(0.0) == "1:00"  # start 前
    session.start(0.0)
    assert session.remaining_display(1.0) == "1:00"  # カウントダウン中は満タン
    t0 = 3.0
    assert session.remaining_sec(t0) == GAME_SEC
    assert session.remaining_display(t0) == "1:00"
    assert session.remaining_display(t0 + 0.001) == "1:00"
    assert session.remaining_display(t0 + 1.0) == "0:59"
    assert session.remaining_display(t0 + 1.2) == "0:59"
    assert session.remaining_display(t0 + 50.0) == "0:10"
    assert session.remaining_display(t0 + 59.5) == "0:01"
    assert session.remaining_display(t0 + 60.0) == "0:00"
    assert session.remaining_display(t0 + 99.0) == "0:00"


def test_warning_in_last_ten_seconds(table: PrecomputeTable) -> None:
    session, t0 = started(table)
    assert not session.in_warning(t0 + 49.9)
    assert session.in_warning(t0 + 50.0)
    assert session.in_warning(t0 + 59.9)
    assert not session.in_warning(t0 + 60.0)  # 終了後は点滅しない


def test_warning_blink_alternates_every_quarter_second(table: PrecomputeTable) -> None:
    """赤 0.25 秒 → 白 0.25 秒の交互(deadline 基準)。警告外は常に False。"""
    session, t0 = started(table)
    deadline = session.deadline
    assert not session.warning_blink(t0 + 49.0)  # 警告前
    assert not session.warning_blink(deadline + 0.1)  # 終了後
    phases = [session.warning_blink(deadline - 10.0 + 0.25 * i + 0.125) for i in range(40)]
    assert all(a != b for a, b in pairwise(phases))  # 0.25 秒ごとに交互
    # 同じ 0.25 秒枠の中では変わらない
    assert session.warning_blink(deadline - 0.95) == session.warning_blink(deadline - 0.80)


def test_countdown_age_resets_each_digit(table: PrecomputeTable) -> None:
    session = GameSession(table)
    assert session.countdown_age(0.0) is None  # start 前
    session.start(10.0)
    assert session.countdown_age(10.0) == pytest.approx(0.0)
    assert session.countdown_age(10.9) == pytest.approx(0.9)
    assert session.countdown_age(11.0) == pytest.approx(0.0)  # 「2」に切り替わった直後
    assert session.countdown_age(12.4) == pytest.approx(0.4)
    assert session.countdown_age(13.0) is None  # プレイ開始後


def test_start_resets_everything(table: PrecomputeTable) -> None:
    session, t0 = started(table)
    as_judgement(session.judge(SCORED_BOARD, t0))
    as_judgement(session.judge(UNCLEARABLE_BOARD, t0 + 1))
    session.start(t0 + 2)
    assert session.score == 0 and session.fail_count == 0 and session.judge_count == 0
    assert session.judged_keys == set() and session.judged_boards == set()
    assert session.records == [] and session.best is None
    assert session.phase(t0 + 2) is Phase.COUNTDOWN
    assert session.cooldown_remaining(t0 + 2) == 0.0


# ---- リザルト用 ----


def test_records_and_best(table: PrecomputeTable) -> None:
    session, t0 = started(table)
    as_judgement(session.judge(MIRROR_A, t0))
    as_judgement(session.judge(UNCLEARABLE_BOARD, t0 + 1))
    as_judgement(session.judge(SCORED_BOARD, t0 + 2))
    as_judgement(session.judge(SCORED_BOARD, t0 + 3))  # duplicate
    assert [r.seq for r in session.records] == [1, 2, 3, 4]
    assert [r.result for r in session.records] == [
        "scored",
        "unclearable",
        "scored",
        "duplicate_same",
    ]
    assert session.records[2].elapsed_sec == pytest.approx(2.0)
    best = session.best
    assert best is not None and best.board == SCORED_BOARD and best.points == SCORED_POINTS


def test_best_prefers_earlier_on_tie(table: PrecomputeTable) -> None:
    session, t0 = started(table)
    as_judgement(session.judge(MIRROR_A, t0))
    as_judgement(session.judge("LMS/S/", t0 + 1))
    pts = [r.points for r in session.records]
    if pts[0] == pts[1]:
        best = session.best
        assert best is not None and best.seq == 1
