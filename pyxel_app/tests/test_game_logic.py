"""screens.game_logic のテスト(Pyxel 非依存)。

ボタン / ドラッグの振り分け、ドラッグ中の判定禁止、時間イベント。
"""

from __future__ import annotations

import pytest

from app.core.precompute import PrecomputeTable, load_table
from board_state import BoardState
from input.drag import DragController
from input.pointer import PointerDriver
from scene import layout
from screens.game_logic import (
    FEEDBACK_SEC,
    HUD_HEIGHT,
    JUDGE_BUTTON,
    TITLE_BUTTON,
    FeedbackKind,
    GameEvent,
    GamePlay,
)
from session import GAME_SEC, GameSession
from tests.test_pointer import TopDownScene, screen_of

SCORED_BOARD = "L/MS/L"
SCORED_POINTS = 60
UNCLEARABLE_BOARD = "LMS/MS/L"


@pytest.fixture(scope="module")
def table() -> PrecomputeTable:
    return load_table()


def make(table: PrecomputeTable, board: str | None = None) -> tuple[GamePlay, float]:
    """プレイ開始直後(GO)の GamePlay と開始時刻。"""
    state = BoardState.initial() if board is None else BoardState.from_board(board)
    driver = PointerDriver(DragController(state), TopDownScene(state))
    session = GameSession(table)
    session.start(0.0)
    play = GamePlay(session, driver)
    t0 = session.started_at
    play.frame(0, 0, False, True, t0)  # COUNTDOWN/GO イベントを消化
    return play, t0


def judge_xy() -> tuple[int, int]:
    return JUDGE_BUTTON.rect.cx, JUDGE_BUTTON.rect.cy


def click(play: GamePlay, x: float, y: float, now: float) -> list[GameEvent]:
    events = play.frame(x, y, True, True, now)
    events += play.frame(x, y, False, True, now + 0.016)
    return events


# ---- 判定 ----


def test_judge_button_scores_and_gives_feedback(table: PrecomputeTable) -> None:
    play, t0 = make(table, SCORED_BOARD)
    events = click(play, *judge_xy(), t0 + 1.0)
    assert events == [GameEvent.JUDGE_OK]
    assert play.session.score == SCORED_POINTS
    fb = play.visible_feedback(t0 + 1.0)
    assert fb is not None and fb.kind is FeedbackKind.SCORED and fb.text == f"+{SCORED_POINTS}"
    assert play.visible_feedback(t0 + 1.0 + FEEDBACK_SEC - 0.01) is not None
    assert play.visible_feedback(t0 + 1.0 + FEEDBACK_SEC) is None


def test_judge_feedback_miss_and_already(table: PrecomputeTable) -> None:
    play, t0 = make(table, UNCLEARABLE_BOARD)
    assert click(play, *judge_xy(), t0 + 1.0) == [GameEvent.JUDGE_MISS]
    fb = play.visible_feedback(t0 + 1.0)
    assert fb is not None and fb.text == "MISS" and fb.kind is FeedbackKind.MISS
    assert play.session.fail_count == 1

    play, t0 = make(table, SCORED_BOARD)
    click(play, *judge_xy(), t0 + 1.0)
    assert click(play, *judge_xy(), t0 + 2.0) == [GameEvent.JUDGE_ALREADY]
    fb = play.visible_feedback(t0 + 2.0)
    assert fb is not None and fb.text == "ALREADY" and fb.kind is FeedbackKind.ALREADY


def test_judge_is_blocked_while_dragging(table: PrecomputeTable) -> None:
    play, t0 = make(table, SCORED_BOARD)
    driver = play.driver
    sx, sy = screen_of(layout.box_center(driver.board, "S1"))  # 塔 B の top
    assert play.frame(sx, sy, True, True, t0 + 1.0) == []
    assert driver.dragging_box == "S1"
    assert not play.judge_enabled(t0 + 1.0)
    # 押しっぱなしのまま Enter 相当
    assert play.press_judge(t0 + 1.1) is None
    assert play.session.judge_count == 0
    # 離して置く → 判定できる
    events = play.frame(sx, sy, False, True, t0 + 1.2)
    assert events == [GameEvent.PLACE]
    assert play.judge_enabled(t0 + 1.3)
    assert play.press_judge(t0 + 1.3) is GameEvent.JUDGE_OK


def test_judge_button_press_does_not_start_a_drag(table: PrecomputeTable) -> None:
    """ボタンで始まった押下は、離すまでドラッグに流さない(ボタン上に箱が重なっていても掴まない)。"""
    play, t0 = make(table, SCORED_BOARD)
    driver = play.driver
    jx, jy = judge_xy()
    assert play.frame(jx, jy, True, True, t0 + 1.0) == [GameEvent.JUDGE_OK]
    assert driver.dragging_box is None
    # 押したまま箱の上へ動かしても掴まない
    sx, sy = screen_of(layout.box_center(driver.board, "S1"))
    assert play.frame(sx, sy, True, True, t0 + 1.1) == []
    assert driver.dragging_box is None
    assert play.frame(sx, sy, False, True, t0 + 1.2) == []
    # 離した後は通常どおり掴める
    assert play.frame(sx, sy, True, True, t0 + 1.3) == []
    assert driver.dragging_box == "S1"


def test_cooldown_and_countdown_reject_silently(table: PrecomputeTable) -> None:
    state = BoardState.from_board(SCORED_BOARD)
    driver = PointerDriver(DragController(state), TopDownScene(state))
    session = GameSession(table)
    session.start(0.0)
    play = GamePlay(session, driver)
    t0 = session.started_at
    play.frame(0, 0, False, True, 0.0)
    play.frame(0, 0, False, True, 1.0)  # 「2」
    assert click(play, *judge_xy(), 1.5) == []  # カウントダウン中(判定の音も演出も無し)
    assert play.session.judge_count == 0
    play.frame(0, 0, False, True, t0)  # GO
    assert click(play, *judge_xy(), t0 + 1.0) == [GameEvent.JUDGE_OK]
    assert not play.judge_enabled(t0 + 1.2)
    assert click(play, *judge_xy(), t0 + 1.2) == []  # クールダウン
    assert play.judge_enabled(t0 + 1.5)
    assert click(play, *judge_xy(), t0 + 1.6) == [GameEvent.JUDGE_ALREADY]


# ---- 時間イベント ----


def test_countdown_go_and_time_up_events(table: PrecomputeTable) -> None:
    state = BoardState.initial()
    driver = PointerDriver(DragController(state), TopDownScene(state))
    session = GameSession(table)
    session.start(10.0)
    play = GamePlay(session, driver)
    assert play.frame(0, 0, False, True, 10.0) == [GameEvent.COUNTDOWN]
    assert play.frame(0, 0, False, True, 11.0) == [GameEvent.COUNTDOWN]
    assert play.frame(0, 0, False, True, 12.0) == [GameEvent.COUNTDOWN]
    assert play.frame(0, 0, False, True, 13.0) == [GameEvent.GO]
    assert play.frame(0, 0, False, True, 13.0 + GAME_SEC) == [GameEvent.TIME_UP]
    assert play.frame(0, 0, False, True, 13.0 + GAME_SEC + 1) == []


def test_drag_is_allowed_during_countdown(table: PrecomputeTable) -> None:
    state = BoardState.initial()
    driver = PointerDriver(DragController(state), TopDownScene(state))
    session = GameSession(table)
    session.start(10.0)
    play = GamePlay(session, driver)
    sx, sy = screen_of(layout.box_center(state, "S1"))
    play.frame(sx, sy, False, True, 10.4)
    play.frame(sx, sy, True, True, 10.5)
    assert driver.dragging_box == "S1"
    tx, ty = screen_of(layout.tower_position("C"))
    play.frame(tx, ty, True, True, 10.6)
    assert play.frame(tx, ty, False, True, 10.7) == [GameEvent.PLACE]
    assert state.tower_string("C") == "S"


def test_time_up_while_dragging_returns_box_and_blocks_input(table: PrecomputeTable) -> None:
    play, t0 = make(table)
    driver = play.driver
    sx, sy = screen_of(layout.box_center(driver.board, "S1"))
    play.frame(sx, sy, True, True, t0 + 1.0)
    assert driver.dragging_box == "S1"
    before = driver.board.board_string()
    tx, ty = screen_of(layout.tower_position("A"))
    events = play.frame(tx, ty, True, True, t0 + GAME_SEC)
    assert events == [GameEvent.TIME_UP]
    assert driver.dragging_box is None
    assert driver.board.board_string() == before
    # 終了後は離しても置かれない・掴めない
    assert play.frame(tx, ty, False, True, t0 + GAME_SEC + 0.1) == []
    assert play.frame(sx, sy, True, True, t0 + GAME_SEC + 0.2) == []
    assert driver.dragging_box is None


def test_judge_just_before_time_up_counts(table: PrecomputeTable) -> None:
    play, t0 = make(table, SCORED_BOARD)
    jx, jy = judge_xy()
    events = play.frame(jx, jy, True, True, t0 + GAME_SEC - 0.001)
    assert events == [GameEvent.JUDGE_OK]
    events = play.frame(jx, jy, False, True, t0 + GAME_SEC)
    assert events == [GameEvent.TIME_UP]
    assert play.session.score == SCORED_POINTS


# ---- TITLE ボタン・配置 ----


def test_title_button_emits_title_event(table: PrecomputeTable) -> None:
    play, t0 = make(table)
    assert click(play, TITLE_BUTTON.rect.cx, TITLE_BUTTON.rect.cy, t0 + 1.0) == [
        GameEvent.BUTTON,
        GameEvent.TITLE,
    ]


def test_button_rects_fit_the_screen_and_avoid_the_hud(table: PrecomputeTable) -> None:
    for b in (JUDGE_BUTTON, TITLE_BUTTON):
        r = b.rect
        assert r.x >= 0 and r.x + r.w <= 320
        assert r.y >= HUD_HEIGHT and r.y + r.h <= 240
    jr, tr = JUDGE_BUTTON.rect, TITLE_BUTTON.rect
    assert tr.x + tr.w <= jr.x  # 重ならない


def test_button_held_at_creation_does_not_pick_a_box(table: PrecomputeTable) -> None:
    """RETRY を押したまま入場しても、その押下で箱を掴まない。"""
    state = BoardState.initial()
    driver = PointerDriver(DragController(state), TopDownScene(state))
    session = GameSession(table)
    session.start(0.0)
    play = GamePlay(session, driver)
    sx, sy = screen_of(layout.box_center(state, "S1"))
    play.frame(sx, sy, True, True, 0.0)
    assert driver.dragging_box is None
    play.frame(sx, sy, False, True, 0.1)
    play.frame(sx, sy, True, True, 0.2)
    assert driver.dragging_box == "S1"


def test_title_button_at_time_up_is_ignored(table: PrecomputeTable) -> None:
    """タイムアップと同じフレームの TITLE 押下はリザルトを飛ばさない(Codex レビュー指摘)。"""
    play, t0 = make(table)
    tx, ty = TITLE_BUTTON.rect.cx, TITLE_BUTTON.rect.cy
    assert play.frame(tx, ty, True, True, t0 + GAME_SEC) == [GameEvent.TIME_UP]
    assert play.frame(tx, ty, False, True, t0 + GAME_SEC + 0.1) == []
    assert click(play, tx, ty, t0 + GAME_SEC + 0.2) == []
