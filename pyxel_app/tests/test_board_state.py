"""board_state のテスト: 全 512 盤面の往復、配置ルール違反 3 種、top 判定(計画書 P2 DoD)。"""

from __future__ import annotations

import pytest

from app.core.board import board_from_index, board_index, is_legal_board
from board_state import (
    BOX_IDS,
    BoardState,
    IllegalPlacementError,
    InStaging,
    OnTower,
    RejectReason,
    size_of,
    slot_size,
    staging_slots_for,
)

ALL_BOARDS = [board_from_index(i) for i in range(512)]


def test_box_ids_and_slots() -> None:
    assert len(BOX_IDS) == 9
    assert [size_of(b) for b in BOX_IDS].count("L") == 3
    assert staging_slots_for("L") == (0, 1, 2)
    assert staging_slots_for("S") == (6, 7, 8)
    assert [slot_size(s) for s in range(9)] == ["L"] * 3 + ["M"] * 3 + ["S"] * 3
    with pytest.raises(ValueError):
        size_of("X1")
    with pytest.raises(ValueError):
        slot_size(9)


def test_initial_all_in_staging() -> None:
    state = BoardState.initial()
    assert state.board_string() == "//"
    assert all(isinstance(state.location(b), InStaging) for b in BOX_IDS)
    assert all(state.is_pickable(b) for b in BOX_IDS)
    assert state.top_of("A") is None


@pytest.mark.parametrize("board", ALL_BOARDS)
def test_roundtrip_all_512(board: str) -> None:
    """所在 → 文字列 → board_index → 復元 が一致する。"""
    state = BoardState.from_board(board)
    assert state.board_string() == board
    index = state.board_index()
    assert index == board_index(board)
    assert board_from_index(index) == board
    # 待機エリアの箱は塔上の箱と合わせて 9 個、スロット重複なし
    staged = state.staging_occupancy()
    on_towers = sum(len(state.tower_stack(t)) for t in ("A", "B", "C"))
    assert len(staged) + on_towers == 9
    assert all(slot_size(s) == size_of(b) for s, b in staged.items())


def test_from_board_rejects_illegal() -> None:
    with pytest.raises(ValueError):
        BoardState.from_board("SL//")
    with pytest.raises(ValueError):
        BoardState.from_board("LMS/LMS/LMSL")


# ---- 配置ルール違反 3 種(仕様書 §4.4) ----


def test_reject_larger_on_smaller() -> None:
    state = BoardState.from_board("S//")
    assert state.check_place("M1", "A") is RejectReason.LARGER_ON_SMALLER
    with pytest.raises(IllegalPlacementError) as ei:
        state.place_on_tower("L1", "A")
    assert ei.value.reason is RejectReason.LARGER_ON_SMALLER
    assert state.board_string() == "S//"  # 盤面は変化しない


def test_reject_same_size() -> None:
    state = BoardState.from_board("L//")
    assert state.check_place("L2", "A") is RejectReason.SAME_SIZE
    with pytest.raises(IllegalPlacementError) as ei:
        state.place_on_tower("L2", "A")
    assert ei.value.reason is RejectReason.SAME_SIZE
    assert state.board_string() == "L//"


def test_reject_fourth_box() -> None:
    state = BoardState.from_board("LMS//")
    for box in ("L2", "M2", "S2"):
        assert state.check_place(box, "A") is RejectReason.TOWER_FULL
    with pytest.raises(IllegalPlacementError) as ei:
        state.place_on_tower("S2", "A")
    assert ei.value.reason is RejectReason.TOWER_FULL
    assert state.board_string() == "LMS//"


def test_legal_placements_build_tower() -> None:
    state = BoardState.initial()
    assert state.place_on_tower("L1", "B") == OnTower("B", 0)
    assert state.place_on_tower("M1", "B") == OnTower("B", 1)
    assert state.place_on_tower("S1", "B") == OnTower("B", 2)
    assert state.board_string() == "/LMS/"
    assert is_legal_board(state.board_string())
    # 同じ塔の top を同じ塔に置き直すのは合法(自分自身を除いて判定)
    assert state.can_place("S1", "B")
    assert state.place_on_tower("S1", "B") == OnTower("B", 2)


# ---- top 判定・掴める箱(§4.2) ----


def test_top_and_pickable() -> None:
    state = BoardState.from_board("LM//S")
    assert state.top_of("A") == "M1"
    assert state.top_of("B") is None
    assert state.top_of("C") == "S1"
    assert state.is_pickable("M1")
    assert not state.is_pickable("L1")  # 塔の下の箱
    assert state.is_pickable("S1")
    assert state.is_pickable("L2")  # 待機エリア
    with pytest.raises(ValueError):
        state.place_on_tower("L1", "B")  # top 以外は動かせない
    assert state.board_string() == "LM//S"


def test_place_in_staging_returns_to_size_column() -> None:
    state = BoardState.from_board("LMS//")
    loc = state.place_in_staging("S1")
    assert loc.slot in staging_slots_for("S")
    assert state.board_string() == "LM//"
    # 優先スロットが埋まっていれば同じ列の空きへ
    state.place_on_tower("M1", "B")  # LM// -> L/M/
    occupied = state.staging_occupancy()
    used_m = next(s for s in staging_slots_for("M") if s in occupied)
    loc2 = state.place_in_staging("M1", preferred=used_m)
    assert loc2.slot in staging_slots_for("M") and loc2.slot != used_m
    # 他サイズ列を指定しても自サイズ列に入る
    loc3 = state.place_in_staging("L1", preferred=8)
    assert loc3.slot in staging_slots_for("L")
    assert state.board_string() == "//"


def test_constructor_validates() -> None:
    locs = dict(BoardState.initial().locations())
    locs["L1"] = OnTower("A", 1)  # level 0 が無い
    with pytest.raises(ValueError):
        BoardState(locs)
    locs = dict(BoardState.initial().locations())
    locs["L1"] = InStaging(3)  # M 列
    with pytest.raises(ValueError):
        BoardState(locs)
    locs = dict(BoardState.initial().locations())
    locs["L1"] = InStaging(1)  # L2 と重複
    with pytest.raises(ValueError):
        BoardState(locs)
    with pytest.raises(ValueError):
        BoardState({"L1": InStaging(0)})


def test_unknown_box_or_tower_raises_value_error() -> None:
    state = BoardState.from_board("L//")
    with pytest.raises(ValueError):
        state.is_pickable("l1")
    with pytest.raises(ValueError):
        state.location("X9")
    with pytest.raises(ValueError):
        state.check_place("S1", "D")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        state.place_on_tower("S1", "D")  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        state.move("S1", OnTower("D", 0))  # type: ignore[arg-type]
    assert state.board_string() == "L//"
    assert state.location("S1") == InStaging(6)


def test_place_in_staging_prefers_origin_when_target_occupied() -> None:
    # L1 塔上、L2=slot0, L3=slot1。L2 を slot 2 へ動かし、埋まった slot 1 を指すと slot 2 に戻る
    state = BoardState.from_board("L//")
    state.move("L2", InStaging(2))  # L2 を slot 2 へ(slot 0 を空ける)
    loc = state.place_in_staging("L2", preferred=1)  # slot 1 は L3
    assert loc == InStaging(2)  # 若い slot 0 ではなく元の slot 2 に戻る
    loc = state.place_in_staging("L2", preferred=0)  # 空いていれば指定先
    assert loc == InStaging(0)


def test_move_rolls_back_on_inconsistency() -> None:
    state = BoardState.from_board("L//")
    with pytest.raises(ValueError):
        state.move("S1", OnTower("A", 0))  # level 0 が重複
    assert state.location("S1") == InStaging(6)
    state.move("S1", OnTower("A", 1))
    assert state.board_string() == "LS//"
