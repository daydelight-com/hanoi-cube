"""判定エンジン(契約: docs/contracts/game-core-api.md §2)。

事前計算テーブル(precompute.py)を引いて判定・得点・最短手順を返す純ロジック。
盤面の合法性は呼び出し側が保証する(不正盤面は board_index 経由で ValueError)。
"""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from typing import Literal

from pydantic import BaseModel

from app.core.board import box_count
from app.core.precompute import Move, PrecomputeTable


class Judgement(BaseModel):
    """1回の判定結果(game-core-api.md §2)。"""

    result: Literal["scored", "unclearable", "duplicate_same", "duplicate_mirror"]
    points: int
    min_moves: int | None
    canonical_key: str


def judge(
    board: str,
    judged_keys: AbstractSet[str],
    judged_boards: AbstractSet[str],
    table: PrecomputeTable,
) -> Judgement:
    """盤面を判定する(ルールブック§6)。

    - board: 合法盤面文字列(呼び出し側が legal を保証する)
    - judged_keys: このプレイで判定済みの canonical_key の集合
    - judged_boards: このプレイで判定済みの生盤面文字列の集合
      (scored / duplicate の盤面は呼び出し側が両集合に追加する)

    クリア不可 → unclearable。canonical_key が判定済みなら、生盤面も一致で
    duplicate_same、鏡像のみ一致で duplicate_mirror(いずれも0点)。
    それ以外は scored、得点 = 箱数 * 最短手数。
    """
    entry = table.entry(board)
    key = entry.canonical_key
    if not entry.clearable:
        return Judgement(result="unclearable", points=0, min_moves=None, canonical_key=key)
    if entry.min_moves is None:
        raise ValueError(f"corrupt table: clearable board {board!r} has no min_moves")
    if key in judged_keys:
        result: Literal["duplicate_same", "duplicate_mirror"] = (
            "duplicate_same" if board in judged_boards else "duplicate_mirror"
        )
        return Judgement(result=result, points=0, min_moves=entry.min_moves, canonical_key=key)
    points = box_count(board) * entry.min_moves
    return Judgement(result="scored", points=points, min_moves=entry.min_moves, canonical_key=key)


def score(board: str, table: PrecomputeTable) -> int:
    """得点 = 箱数 * 最短手数。クリア不可は 0。"""
    entry = table.entry(board)
    if not entry.clearable or entry.min_moves is None:
        return 0
    return box_count(board) * entry.min_moves


def min_path(board: str, table: PrecomputeTable) -> list[Move] | None:
    """最短クリア手順。クリア不可なら None。"""
    entry = table.entry(board)
    if entry.min_path is None:
        return None
    return list(entry.min_path)
