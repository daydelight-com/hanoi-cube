"""判定エンジン(contracts/game-core-api.md §2)のテスト。

ルールブック§5・§6 の例をテストケース化する:
- LMS/LM/L はクリア可能で最短3手(§5 クリア手順の例)
- L/MS/L は 24点(4箱 * 6手。得点ランキング1位)
- LMS/MS/L はクリア不可(§5 クリア不可の例)
- 対称枚数配置の0手クリア禁止(§5 条件2)
- 同一盤面の再判定は duplicate_same、鏡像は duplicate_mirror(§6)
"""

import pytest
from app.core.board import canonical_key
from app.core.engine import judge, min_path, score
from app.core.precompute import PrecomputeTable, load_table

EMPTY: frozenset[str] = frozenset()


@pytest.fixture(scope="module")
def table() -> PrecomputeTable:
    return load_table()


def test_rulebook_example_is_min_3_moves(table: PrecomputeTable) -> None:
    # §5: A:[大,中,小] B:[大,中] C:[大] は最短3手
    result = judge("LMS/LM/L", EMPTY, EMPTY, table)
    assert result.result == "scored"
    assert result.min_moves == 3
    assert result.points == 6 * 3
    assert result.canonical_key == canonical_key("LMS/LM/L")


def test_top_scoring_board_is_30_points(table: PrecomputeTable) -> None:
    # ランキング1位: [大]/[大,中,小]/[中] = 5箱 * 6手 = 30点
    result = judge("L/LMS/M", EMPTY, EMPTY, table)
    assert result.result == "scored"
    assert result.points == 30
    assert result.min_moves == 6
    assert score("L/LMS/M", table) == 30


def test_rulebook_unclearable_example(table: PrecomputeTable) -> None:
    # §5: A:[大,中,小] B:[中,小] C:[大] はクリア不可
    result = judge("LMS/MS/L", EMPTY, EMPTY, table)
    assert result.result == "unclearable"
    assert result.points == 0
    assert result.min_moves is None
    assert score("LMS/MS/L", table) == 0
    assert min_path("LMS/MS/L", table) is None


def test_symmetric_placement_needs_actual_box_movement(table: PrecomputeTable) -> None:
    # §5 条件2: 左右対称な枚数配置でも0手クリアは不可。ただし同サイズの箱を塔間で
    # 入れ替えれば「箱が別の塔にある」を満たすため、実際に動かせばクリアになる
    result = judge("LMS//LMS", EMPTY, EMPTY, table)
    assert result.result == "scored"
    assert result.min_moves == 3
    assert result.points == 6 * 3


def test_frozen_board_is_unclearable(table: PrecomputeTable) -> None:
    # 3塔とも最上段が小・空塔なしで合法手が1手も無い → クリア不可(§4)
    result = judge("LMS/MS/LMS", EMPTY, EMPTY, table)
    assert result.result == "unclearable"
    assert result.points == 0
    assert result.min_moves is None


def test_mirror_duplicate_and_same_duplicate(table: PrecomputeTable) -> None:
    # LMS// を判定して得点(3箱 * 7手 = 21点)
    first = judge("LMS//", EMPTY, EMPTY, table)
    assert first.result == "scored"
    assert first.points == 21

    # 呼び出し側と同じく canonical_key と生盤面文字列の両方を記録する
    judged_keys = {first.canonical_key}
    judged_boards = {"LMS//"}

    mirrored = judge("//LMS", judged_keys, judged_boards, table)
    assert mirrored.result == "duplicate_mirror"
    assert mirrored.points == 0
    assert mirrored.min_moves == 7
    assert mirrored.canonical_key == first.canonical_key

    again = judge("LMS//", judged_keys, judged_boards, table)
    assert again.result == "duplicate_same"
    assert again.points == 0
    assert again.min_moves == 7


def test_unclearable_takes_precedence_over_duplicate(table: PrecomputeTable) -> None:
    # 判定順序(契約§2)はクリア不可が先。判定済み集合に入っていても unclearable
    board = "LMS/MS/L"
    result = judge(board, {canonical_key(board)}, {board}, table)
    assert result.result == "unclearable"


def test_min_path_matches_min_moves_and_score(table: PrecomputeTable) -> None:
    path = min_path("LMS/LM/L", table)
    assert path is not None
    assert len(path) == 3
    # Move の JSON 表現はキー "from"(pydantic alias)
    assert set(path[0].model_dump(by_alias=True)) == {"size", "from", "to"}

    seven = min_path("LMS//", table)
    assert seven is not None
    assert len(seven) == 7
    assert score("LMS//", table) == 21


def test_judge_rejects_malformed_board(table: PrecomputeTable) -> None:
    with pytest.raises(ValueError):
        judge("LMS/-/L", EMPTY, EMPTY, table)
