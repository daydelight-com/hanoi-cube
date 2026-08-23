"""input.drag の状態機械テスト: legal / illegal / 範囲外 / top 以外 / ドラッグ中は判定不可。"""

from __future__ import annotations

from app.core.board import Tower
from board_state import BoardState, InStaging, OnTower, RejectReason
from input.drag import (
    DragController,
    DragState,
    DropResult,
    StagingTarget,
    TowerTarget,
)


def test_idle_initially() -> None:
    ctl = DragController(BoardState.initial())
    assert ctl.state is DragState.IDLE
    assert not ctl.is_dragging
    assert ctl.can_judge()
    assert ctl.dragging_box is None
    assert ctl.release(TowerTarget("A")) is None  # Idle で release しても何も起きない
    assert ctl.cancel() is None


def test_press_pickable_enters_dragging() -> None:
    ctl = DragController(BoardState.from_board("LM//"))
    assert ctl.press("M1")
    assert ctl.state is DragState.DRAGGING
    assert ctl.dragging_box == "M1"
    assert ctl.origin == OnTower("A", 1)
    assert not ctl.can_judge()  # §4.5: Dragging 中は判定不可
    # 二重 press は無視
    assert not ctl.press("S1")
    assert ctl.dragging_box == "M1"


def test_press_non_top_box_is_ignored() -> None:
    ctl = DragController(BoardState.from_board("LM//"))
    assert not ctl.press("L1")  # 塔の下の箱
    assert ctl.state is DragState.IDLE
    assert ctl.can_judge()


def test_press_nothing_is_ignored() -> None:
    ctl = DragController(BoardState.initial())
    assert not ctl.press(None)
    assert ctl.state is DragState.IDLE


def test_release_legal_updates_board() -> None:
    state = BoardState.initial()
    ctl = DragController(state)
    assert ctl.press("L1")
    outcome = ctl.release(TowerTarget("B"))
    assert outcome is not None and outcome.placed
    assert outcome.result is DropResult.PLACED
    assert outcome.location == OnTower("B", 0)
    assert outcome.reason is None
    assert state.board_string() == "/L/"
    assert ctl.state is DragState.IDLE
    assert ctl.can_judge()


def test_release_illegal_returns_to_origin() -> None:
    state = BoardState.from_board("S//")
    ctl = DragController(state)
    assert ctl.press("L1")
    origin = ctl.origin
    outcome = ctl.release(TowerTarget("A"))
    assert outcome is not None
    assert outcome.result is DropResult.RETURNED_ILLEGAL
    assert outcome.reason is RejectReason.LARGER_ON_SMALLER
    assert outcome.location == origin
    assert state.location("L1") == origin
    assert state.board_string() == "S//"  # 盤面は変化しない
    assert ctl.state is DragState.IDLE


def test_release_out_of_range_returns_to_origin() -> None:
    state = BoardState.from_board("LMS//")
    ctl = DragController(state)
    assert ctl.press("S1")
    outcome = ctl.release(None)
    assert outcome is not None
    assert outcome.result is DropResult.RETURNED_OUT_OF_RANGE
    assert outcome.location == OnTower("A", 2)
    assert state.board_string() == "LMS//"
    assert ctl.state is DragState.IDLE


def test_cancel_outside_window() -> None:
    state = BoardState.initial()
    ctl = DragController(state)
    assert ctl.press("M2")
    outcome = ctl.cancel()
    assert outcome is not None and outcome.result is DropResult.RETURNED_OUT_OF_RANGE
    assert state.location("M2") == InStaging(4)
    assert ctl.state is DragState.IDLE


def test_release_to_staging_always_allowed() -> None:
    state = BoardState.from_board("LMS//")
    ctl = DragController(state)
    assert ctl.press("S1")
    # L 列のスロットを指しても S 列の空きへ入る
    outcome = ctl.release(StagingTarget(0))
    assert outcome is not None and outcome.placed
    assert isinstance(outcome.location, InStaging)
    assert outcome.location.slot in (6, 7, 8)
    assert state.board_string() == "LM//"
    # 空いている同列スロットを指せばそこへ
    assert ctl.press("M1")
    outcome = ctl.release(StagingTarget(outcome_slot := 5))
    assert outcome is not None and outcome.location == InStaging(outcome_slot)
    assert state.board_string() == "L//"


def test_release_same_place_is_noop_placed() -> None:
    state = BoardState.from_board("LM//")
    ctl = DragController(state)
    assert ctl.press("M1")
    outcome = ctl.release(TowerTarget("A"))
    assert outcome is not None and outcome.placed
    assert outcome.location == OnTower("A", 1)
    assert state.board_string() == "LM//"
    # L2 は slot 0。自分のスロットに戻すのも、埋まっている隣(L3 の slot 1)を指すのも slot 0 に収まる
    assert state.location("L2") == InStaging(0)
    assert ctl.press("L2")
    outcome = ctl.release(StagingTarget(0))
    assert outcome is not None and outcome.location == InStaging(0)
    assert ctl.press("L2")
    outcome = ctl.release(StagingTarget(1))
    assert outcome is not None and outcome.location == InStaging(0)
    assert state.location("L3") == InStaging(1)


def test_preview_highlight() -> None:
    ctl = DragController(BoardState.from_board("S//"))
    assert ctl.preview(TowerTarget("A")) is None  # 非ドラッグ
    assert ctl.press("L1")
    assert ctl.preview(TowerTarget("A")) is False  # 赤
    assert ctl.preview(TowerTarget("B")) is True  # 緑
    assert ctl.preview(StagingTarget(3)) is True
    assert ctl.preview(None) is None


def test_sequence_of_moves_reaches_target_board() -> None:
    """一連のドラッグでハノイの 3 手を再現する。"""
    state = BoardState.from_board("LMS//")
    ctl = DragController(state)
    moves: list[tuple[str, Tower]] = [("S1", "C"), ("M1", "B"), ("S1", "B")]
    for box, tower in moves:
        assert ctl.press(box)
        outcome = ctl.release(TowerTarget(tower))
        assert outcome is not None and outcome.placed, (box, tower)
    assert state.board_string() == "L/MS/"
