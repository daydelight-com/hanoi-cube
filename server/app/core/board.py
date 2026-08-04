"""盤面表現ユーティリティ(契約: docs/contracts/board.md)。"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

Size = Literal["L", "M", "S"]
Tower = Literal["A", "B", "C"]

TOWER_NAMES: tuple[Tower, Tower, Tower] = ("A", "B", "C")

# 塔状態インデックス 0〜7(board.md §2)
TOWER_STATES: tuple[str, ...] = ("", "S", "M", "L", "MS", "LS", "LM", "LMS")

_TOWER_INDEX: dict[str, int] = {state: i for i, state in enumerate(TOWER_STATES)}
_BOARD_RE = re.compile(r"^[LMS]*/[LMS]*/[LMS]*$")


def is_legal_tower(tower: str) -> bool:
    """塔文字列が合法な8状態のいずれかであるか。"""
    return tower in _TOWER_INDEX


def parse_board(board: str) -> tuple[str, str, str]:
    """盤面文字列を (A, B, C) の塔文字列に分解する。形式不正は ValueError。"""
    if not _BOARD_RE.match(board):
        raise ValueError(f"invalid board string: {board!r}")
    a, b, c = board.split("/")
    return a, b, c


def format_board(towers: Sequence[str]) -> str:
    """塔文字列3つを盤面文字列に連結する。"""
    if len(towers) != 3:
        raise ValueError(f"expected 3 towers, got {len(towers)}")
    return "/".join(towers)


def is_legal_board(board: str) -> bool:
    """盤面文字列が形式・配置ルールともに合法か。"""
    try:
        towers = parse_board(board)
    except ValueError:
        return False
    return all(is_legal_tower(t) for t in towers)


def mirror_board(board: str) -> str:
    """鏡像盤面(A塔とC塔の入れ替え)。"""
    a, b, c = parse_board(board)
    return format_board((c, b, a))


def canonical_key(board: str) -> str:
    """鏡像同一視の正準キー: 盤面文字列と鏡像の辞書順で小さい方。"""
    return min(board, mirror_board(board))


def board_index(board: str) -> int:
    """盤面インデックス 0〜511(board.md §4)。不正盤面は ValueError。"""
    a, b, c = parse_board(board)
    try:
        return _TOWER_INDEX[a] * 64 + _TOWER_INDEX[b] * 8 + _TOWER_INDEX[c]
    except KeyError as e:
        raise ValueError(f"illegal tower in board {board!r}") from e


def board_from_index(index: int) -> str:
    """盤面インデックスから盤面文字列を復元する。"""
    if not 0 <= index < 512:
        raise ValueError(f"board index out of range: {index}")
    return format_board(
        (TOWER_STATES[index // 64], TOWER_STATES[index // 8 % 8], TOWER_STATES[index % 8])
    )


def box_count(board: str) -> int:
    """盤面上の箱の総数(得点 = box_count * 最短手数 の係数)。"""
    a, b, c = parse_board(board)
    return len(a) + len(b) + len(c)
