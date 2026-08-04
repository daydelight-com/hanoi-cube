"""事前計算テーブル(契約: docs/contracts/game-core-api.md §3)。

全512盤面についてクリア可否・最短手数・最短手順・鏡像・正準キーをBFSで計算し、
`data/precompute.json` に出力する。生成物はリポジトリにコミットする静的アセットで、
ローカル/クラウド(記録画面のシミュレーション再生)で共用する。

生成: `uv run python -m app.core.precompute`
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.board import (
    TOWER_NAMES,
    Size,
    Tower,
    board_from_index,
    board_index,
    canonical_key,
    mirror_board,
    parse_board,
)

DATA_PATH = Path(__file__).parent / "data" / "precompute.json"

# サイズの大小関係(移動先の一番上は動かす箱より真に大きいこと)
_SIZE_RANK = {"S": 1, "M": 2, "L": 3}

_Towers = tuple[str, str, str]


class Move(BaseModel):
    """1手の移動。JSON キーは "from"(pydantic alias。game-core-api.md §3)。"""

    model_config = ConfigDict(populate_by_name=True, frozen=True)

    size: Size
    from_: Tower = Field(alias="from")
    to: Tower


class BoardEntry(BaseModel):
    """1盤面分の事前計算結果(game-core-api.md §3 のスキーマ)。"""

    board: str
    index: int
    clearable: bool
    min_moves: int | None
    min_path: list[Move] | None
    mirror: str
    canonical_key: str


class PrecomputeTable(BaseModel):
    """全512盤面の事前計算テーブル(boards は board_index 順)。"""

    version: int
    boards: list[BoardEntry]

    @model_validator(mode="after")
    def _validate_boards_in_index_order(self) -> PrecomputeTable:
        # entry() は boards が board_index 順である前提のため、ロード時に保証する
        if len(self.boards) != 512:
            raise ValueError(f"expected 512 boards, got {len(self.boards)}")
        for i, entry in enumerate(self.boards):
            if entry.index != i or board_index(entry.board) != i:
                raise ValueError(f"boards[{i}] is out of order: {entry.board!r}")
        return self

    def entry(self, board: str) -> BoardEntry:
        """合法盤面文字列に対応するエントリ。不正盤面は ValueError。"""
        return self.boards[board_index(board)]


def _legal_moves(towers: _Towers) -> list[tuple[Move, _Towers]]:
    """現盤面から1手で到達できる (手, 次盤面) の一覧(ルールブック§4)。"""
    results: list[tuple[Move, _Towers]] = []
    for i, src in enumerate(towers):
        if not src:
            continue
        size = src[-1]
        for j, dst in enumerate(towers):
            if i == j or len(dst) == 3:
                continue
            if dst and _SIZE_RANK[dst[-1]] <= _SIZE_RANK[size]:
                continue
            nxt = list(towers)
            nxt[i] = src[:-1]
            nxt[j] = dst + size
            move = Move.model_validate({"size": size, "from": TOWER_NAMES[i], "to": TOWER_NAMES[j]})
            results.append((move, (nxt[0], nxt[1], nxt[2])))
    return results


def solve(board: str) -> tuple[int, list[Move]] | None:
    """初期盤面からのBFSで最短クリア手順を求める。クリア不可なら None。

    クリア条件(ルールブック§5): 枚数配置 (a,b,c) が (c,b,a) になり、かつ最終盤面 ≠ 初期盤面。
    条件2により、左右対称な枚数配置でも0手クリアは成立しない。
    """
    start = parse_board(board)
    goal_counts = tuple(len(t) for t in reversed(start))
    parent: dict[_Towers, tuple[_Towers, Move] | None] = {start: None}
    queue: deque[_Towers] = deque([start])
    while queue:
        current = queue.popleft()
        if current != start and tuple(len(t) for t in current) == goal_counts:
            path: list[Move] = []
            node = current
            while (step := parent[node]) is not None:
                node, move = step
                path.append(move)
            path.reverse()
            return len(path), path
        for move, nxt in _legal_moves(current):
            if nxt not in parent:
                parent[nxt] = (current, move)
                queue.append(nxt)
    return None


def build_table() -> PrecomputeTable:
    """全512盤面をBFSで解いてテーブルを構築する。"""
    entries: list[BoardEntry] = []
    for index in range(512):
        board = board_from_index(index)
        solved = solve(board)
        entries.append(
            BoardEntry(
                board=board,
                index=index,
                clearable=solved is not None,
                min_moves=solved[0] if solved else None,
                min_path=solved[1] if solved else None,
                mirror=mirror_board(board),
                canonical_key=canonical_key(board),
            )
        )
    return PrecomputeTable(version=1, boards=entries)


def load_table(path: Path = DATA_PATH) -> PrecomputeTable:
    """コミット済みの precompute.json を読み込む。"""
    return PrecomputeTable.model_validate_json(path.read_text(encoding="utf-8"))


def main() -> None:
    table = build_table()
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(table.model_dump(by_alias=True), ensure_ascii=False, indent=1)
    DATA_PATH.write_text(payload + "\n", encoding="utf-8")
    cleared = sum(1 for e in table.boards if e.clearable)
    print(f"wrote {DATA_PATH} ({cleared}/512 clearable)")


if __name__ == "__main__":
    main()
