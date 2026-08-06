"""事前計算テーブル(contracts/game-core-api.md §3)のテスト。

DoDの核: 独立実装の総当たりBFSとの照合で512盤面全一致。
検算値(ルールブック§7 / game-core-api.md §4): クリア可能304/512、鏡像同一視で
166クラス、最短手数の最大は7手(LMS//)、総得点プール1556点。
score_ranking.md の全166クラスとも照合する。
"""

import json
import re
from collections import deque
from functools import cache
from pathlib import Path

import pytest
from app.core.board import (
    board_from_index,
    board_index,
    box_count,
    canonical_key,
    mirror_board,
)
from app.core.precompute import DATA_PATH, PrecomputeTable, build_table, load_table

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def table() -> PrecomputeTable:
    return load_table()


# ---------------------------------------------------------------------------
# 独立実装のBFS(実装本体とは別方針: 早期終了なしの全点距離 + 目標状態の列挙)
# ---------------------------------------------------------------------------

_ORDER = "SML"  # 小 < 中 < 大

# 個体を区別した状態: 各塔が (箱ラベル, ...)。ラベルは "L#0" 形式でサイズ+通し番号
_State = tuple[tuple[str, ...], ...]


def _independent_labelled(board: str) -> _State:
    """本体とは逆順(C塔から)に通し番号を振る。個体の割り当て方が結果に影響しない確認も兼ねる。"""
    towers = board.split("/")
    counter = 0
    labelled: list[tuple[str, ...]] = []
    for tower in reversed(towers):
        boxes = []
        for disk in reversed(tower):
            boxes.append(f"{disk}#{counter}")
            counter += 1
        labelled.append(tuple(reversed(boxes)))
    return tuple(reversed(labelled))


def _independent_neighbors(state: _State) -> list[_State]:
    towers = list(state)
    result = []
    for src in range(3):
        if not towers[src]:
            continue
        box = towers[src][-1]
        for dst in range(3):
            if dst == src or len(towers[dst]) >= 3:
                continue
            if towers[dst] and _ORDER.index(towers[dst][-1][0]) <= _ORDER.index(box[0]):
                continue
            moved = towers.copy()
            moved[src] = moved[src][:-1]
            moved[dst] = (*moved[dst], box)
            result.append(tuple(moved))
    return result


def _counts(board: str) -> tuple[int, ...]:
    return tuple(len(t) for t in board.split("/"))


@cache
def _independent_min_moves(board: str) -> int | None:
    """全点距離を計算してから目標状態(枚数反転かつ箱が初期と別の塔にある)の最小距離を取る。"""
    start = _independent_labelled(board)
    distances = {start: 0}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for nxt in _independent_neighbors(current):
            if nxt not in distances:
                distances[nxt] = distances[current] + 1
                queue.append(nxt)
    goal_counts = _counts(board)[::-1]
    home = {box: i for i, tower in enumerate(start) for box in tower}
    goals = [
        state
        for state in distances
        if tuple(len(t) for t in state) == goal_counts
        and any(home[box] != i for i, tower in enumerate(state) for box in tower)
    ]
    return min((distances[g] for g in goals), default=None)


# ---------------------------------------------------------------------------
# DoDの核: 512盤面全一致
# ---------------------------------------------------------------------------


def test_all_512_boards_match_independent_bfs(table: PrecomputeTable) -> None:
    for entry in table.boards:
        expected = _independent_min_moves(entry.board)
        assert entry.clearable == (expected is not None), entry.board
        assert entry.min_moves == expected, entry.board


def test_committed_json_matches_regeneration(table: PrecomputeTable) -> None:
    # コミット済みJSONが precompute.py の再生成結果とドリフトしていないこと
    assert table == build_table()


# ---------------------------------------------------------------------------
# 検算値
# ---------------------------------------------------------------------------


def test_reference_totals(table: PrecomputeTable) -> None:
    clearable = [e for e in table.boards if e.clearable]
    assert len(clearable) == 304

    keys = {e.canonical_key for e in clearable}
    assert len(keys) == 166

    max_moves = max(e.min_moves for e in clearable if e.min_moves is not None)
    assert max_moves == 7
    assert {e.board for e in clearable if e.min_moves == 7} == {"LMS//", "//LMS"}

    # 総得点プール(鏡像同一視。canonical_key は自身も盤面文字列)
    pool = 0
    for key in keys:
        entry = table.entry(key)
        assert entry.min_moves is not None
        pool += box_count(key) * entry.min_moves
    assert pool == 1556


def test_no_zero_move_clear(table: PrecomputeTable) -> None:
    # クリア条件2「箱が初期と別の塔にある」により0手クリアは存在しない(ルールブック§5)
    for entry in table.boards:
        if entry.clearable:
            assert entry.min_moves is not None and entry.min_moves >= 1
            assert entry.min_path is not None and len(entry.min_path) >= 1


def test_same_size_swap_counts_as_clear(table: PrecomputeTable) -> None:
    # クリア条件2は箱の個体で見る(ルールブック§5)。同サイズの箱を塔間で入れ替えると
    # 盤面文字列は初期と同一のままだが、箱は動いているのでクリアが成立する
    for board, moves in (("LMS/LM/LMS", 3), ("LMS//LMS", 3), ("S//S", 3), ("L/LMS/M", 6)):
        entry = table.entry(board)
        assert entry.clearable, board
        assert entry.min_moves == moves, board


def test_frozen_and_immobile_boards_are_unclearable(table: PrecomputeTable) -> None:
    # 合法手が尽きる盤面、および枚数条件を保ったまま箱を動かせない盤面はクリア不可
    for board in (
        "LMS/MS/LMS",  # 3塔とも最上段が小・空塔なし → 合法手が1手も無い
        "LMS/LS/LMS",
        "S/S/S",
        "/LMS/",  # 枚数 (0,3,0) を保てるのは初期状態そのものだけ
        "//",
    ):
        entry = table.entry(board)
        assert not entry.clearable, board
        assert entry.min_moves is None and entry.min_path is None


# ---------------------------------------------------------------------------
# スキーマと整合性
# ---------------------------------------------------------------------------


def test_entries_are_in_board_index_order(table: PrecomputeTable) -> None:
    assert table.version == 1
    assert len(table.boards) == 512
    for i, entry in enumerate(table.boards):
        assert entry.index == i
        assert entry.board == board_from_index(i)
        assert board_index(entry.board) == i
        assert entry.mirror == mirror_board(entry.board)
        assert entry.canonical_key == canonical_key(entry.board)


def test_mirror_boards_share_clearability_and_min_moves(table: PrecomputeTable) -> None:
    for entry in table.boards:
        mirrored = table.entry(entry.mirror)
        assert entry.clearable == mirrored.clearable
        assert entry.min_moves == mirrored.min_moves


def test_min_paths_are_legal_and_reach_goal(table: PrecomputeTable) -> None:
    for entry in table.boards:
        if not entry.clearable:
            continue
        assert entry.min_path is not None
        assert len(entry.min_path) == entry.min_moves
        start = _independent_labelled(entry.board)
        towers = dict(zip("ABC", start, strict=True))
        home = {box: name for name, tower in towers.items() for box in tower}
        for move in entry.min_path:
            # 移動元の一番上が move.size で、移動先は空か真に大きい箱(§4)
            assert towers[move.from_], (entry.board, move)
            assert towers[move.from_][-1][0] == move.size
            dst = towers[move.to]
            assert len(dst) < 3
            if dst:
                assert _ORDER.index(dst[-1][0]) > _ORDER.index(move.size)
            towers[move.to] = (*dst, towers[move.from_][-1])
            towers[move.from_] = towers[move.from_][:-1]
        # クリア条件(§5): 枚数が左右反転し、かつ箱が1個以上は初期と別の塔にある
        final = "/".join("".join(b[0] for b in towers[t]) for t in "ABC")
        assert _counts(final) == _counts(entry.board)[::-1]
        assert any(home[box] != name for name, tower in towers.items() for box in tower)


def test_table_rejects_out_of_order_or_truncated_boards(table: PrecomputeTable) -> None:
    # entry() は index 順を前提とするため、崩れたテーブルはロード時に拒否される
    dumped = table.model_dump(by_alias=True)
    truncated = {"version": 1, "boards": dumped["boards"][:511]}
    with pytest.raises(ValueError):
        PrecomputeTable.model_validate(truncated)

    boards = list(dumped["boards"])
    boards[0], boards[1] = boards[1], boards[0]
    with pytest.raises(ValueError):
        PrecomputeTable.model_validate({"version": 1, "boards": boards})


def test_moves_are_frozen(table: PrecomputeTable) -> None:
    # min_path が返す Move を書き換えてもテーブルが壊れないよう不変にしている
    entry = table.entry("LMS//L")
    assert entry.min_path is not None
    with pytest.raises(ValueError):
        entry.min_path[0].to = "A"


def test_json_move_uses_from_alias() -> None:
    raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    entry = raw["boards"][board_index("LMS//L")]
    assert entry["board"] == "LMS//L"
    assert entry["min_moves"] == 3
    first_move = entry["min_path"][0]
    assert set(first_move) == {"size", "from", "to"}


# ---------------------------------------------------------------------------
# score_ranking.md(全166クラス)との照合
# ---------------------------------------------------------------------------

_KANJI_TO_CHAR = {"大": "L", "中": "M", "小": "S"}


def _tower_from_kanji(cell: str) -> str:
    if cell == "－":  # noqa: RUF001 -- score_ranking.md の空塔表記(全角ハイフン)
        return ""
    return "".join(_KANJI_TO_CHAR[part] for part in cell.split(","))


def _ranking_rows() -> list[tuple[int, int, int, str]]:
    """(得点, 円盤数, 最短手数, 盤面文字列) を score_ranking.md から読む。"""
    text = (REPO_ROOT / "docs" / "game" / "score_ranking.md").read_text(encoding="utf-8")
    rows = []
    pattern = re.compile(
        r"^\| (\d+) \| (\d+) \| (\d+) \| (\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$"
    )
    for line in text.splitlines():
        match = pattern.match(line)
        if not match:
            continue
        _, points, boxes, moves, a, b, c = match.groups()[:7]
        board = "/".join(_tower_from_kanji(t.strip()) for t in (a, b, c))
        rows.append((int(points), int(boxes), int(moves), board))
    return rows


def test_score_ranking_document_matches_table(table: PrecomputeTable) -> None:
    rows = _ranking_rows()
    assert len(rows) == 166

    seen_keys = set()
    for points, boxes, moves, board in rows:
        entry = table.entry(board)
        assert entry.clearable, board
        assert entry.min_moves == moves, board
        assert box_count(board) == boxes, board
        assert boxes * moves == points, board
        seen_keys.add(entry.canonical_key)

    # 代表166行の正準キー集合 = テーブル上のクリア可能クラス全体
    clearable_keys = {e.canonical_key for e in table.boards if e.clearable}
    assert seen_keys == clearable_keys
