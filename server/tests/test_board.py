"""盤面表現(contracts/board.md)のテスト。"""

import pytest
from app.core.board import (
    TOWER_STATES,
    board_from_index,
    board_index,
    box_count,
    canonical_key,
    format_board,
    is_legal_board,
    is_legal_tower,
    mirror_board,
    parse_board,
)


def test_tower_states_are_the_eight_legal_states() -> None:
    # ルールブック§3 の並び順(board.md §2)
    assert TOWER_STATES == ("", "S", "M", "L", "MS", "LS", "LM", "LMS")
    assert all(is_legal_tower(t) for t in TOWER_STATES)
    assert not is_legal_tower("SL")
    assert not is_legal_tower("LL")
    assert not is_legal_tower("LMSS")


def test_parse_and_format_roundtrip() -> None:
    assert parse_board("LMS//L") == ("LMS", "", "L")
    assert format_board(("LMS", "", "L")) == "LMS//L"
    assert parse_board("//") == ("", "", "")


@pytest.mark.parametrize("bad", ["", "LMS/L", "LMS//L/", "lms//L", "LMS/-/L", "LMX//L"])
def test_parse_rejects_invalid_format(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_board(bad)


def test_is_legal_board() -> None:
    assert is_legal_board("LMS//L")
    assert is_legal_board("//")
    assert not is_legal_board("SL//")  # 小の上に大
    assert not is_legal_board("LMS/-/L")  # プレースホルダ表記は不正(board.md §3)


def test_mirror_and_canonical_key() -> None:
    assert mirror_board("LMS//L") == "L//LMS"
    assert mirror_board("L//LMS") == "LMS//L"
    assert canonical_key("LMS//L") == "L//LMS"
    assert canonical_key("L//LMS") == "L//LMS"
    # 左右対称は自分自身が正準キー
    assert canonical_key("L/MS/L") == "L/MS/L"
    # ルールブック§6 の例: 鏡像は同一視
    assert canonical_key("LMS//") == canonical_key("//LMS")


def test_board_index_roundtrip_all_512() -> None:
    seen = set()
    for index in range(512):
        board = board_from_index(index)
        assert board_index(board) == index
        assert is_legal_board(board)
        seen.add(board)
    assert len(seen) == 512
    with pytest.raises(ValueError):
        board_from_index(512)
    with pytest.raises(ValueError):
        board_index("SL//")  # 形式は正しいが不正盤面


def test_box_count() -> None:
    assert box_count("//") == 0
    assert box_count("LMS//L") == 4
    assert box_count("LMS/LMS/LMS") == 9
