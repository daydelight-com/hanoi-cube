"""input.pointer のテスト: 押下/解放エッジ、ピッキング → ドラッグ → ドロップの結線。

偽シーンを使い Pyxel に依存しない。

偽シーンは「画面座標 (sx, sy) = 床面の点 (sx/100, 0, sy/100)」という真上から見た直交投影で、
箱は床面上の正方形フットプリント(一番上の箱が先に当たる)として扱う。
"""

from __future__ import annotations

from board_state import BOX_EDGE_MM, BoardState, InStaging, OnTower, RejectReason, size_of
from input.drag import DragController, DropResult
from input.pointer import PointerDriver
from scene import layout
from scene.layout import StagingTarget, TowerTarget

Vec = tuple[float, float, float]


class TopDownScene:
    """上から見た 2D 当たり判定の偽シーン。"""

    def __init__(self, board: BoardState) -> None:
        self.board = board
        self.floor_hits = True  # False にするとレイが床を外れる状況を再現

    def floor_point(self, sx: float, sy: float) -> Vec | None:
        return (sx / 100.0, 0.0, sy / 100.0) if self.floor_hits else None

    def pick_box(self, sx: float, sy: float) -> str | None:
        point = (sx / 100.0, 0.0, sy / 100.0)
        best: tuple[float, str] | None = None
        for box_id in self.board:
            cx, cy, cz = layout.box_center(self.board, box_id)
            half = layout.mm(BOX_EDGE_MM[size_of(box_id)]) / 2
            inside = abs(point[0] - cx) <= half and abs(point[2] - cz) <= half
            if inside and (best is None or cy > best[0]):  # 高い(上にある)箱を優先
                best = (cy, box_id)
        return None if best is None else best[1]


def screen_of(point: Vec) -> tuple[float, float]:
    return (point[0] * 100.0, point[2] * 100.0)


def make(board: str | None = None) -> tuple[PointerDriver, TopDownScene]:
    state = BoardState.initial() if board is None else BoardState.from_board(board)
    scene = TopDownScene(state)
    return PointerDriver(DragController(state), scene), scene


def drag_to(driver: PointerDriver, box_id: str, dest: Vec) -> None:
    """box_id の中心を押し、dest(床面)へ動かして離す(3 フレーム)。"""
    sx, sy = screen_of(layout.box_center(driver.board, box_id))
    assert driver.feed(sx, sy, True) is None
    dx, dy = screen_of(dest)
    assert driver.feed(dx, dy, True) is None
    driver.feed(dx, dy, False)


# ---- エッジ検出 ----


def test_press_edge_only_once_and_release_returns_outcome() -> None:
    driver, _ = make()
    sx, sy = screen_of(layout.box_center(driver.board, "L1"))
    assert driver.feed(sx, sy, False) is None  # 押していない
    assert driver.feed(sx, sy, True) is None  # 押下エッジ → Dragging
    assert driver.dragging_box == "L1"
    assert driver.feed(sx, sy, True) is None  # 押しっぱなし → move
    assert driver.dragging_box == "L1"
    outcome = driver.feed(sx, sy, False)  # 解放エッジ
    assert outcome is not None and outcome.placed
    assert driver.dragging_box is None
    assert driver.feed(sx, sy, False) is None  # 解放後の無操作


def test_press_on_empty_space_does_nothing() -> None:
    driver, _ = make()
    assert driver.feed(0.0, 0.0, True) is None
    assert driver.dragging_box is None
    assert driver.target is None and driver.preview is None
    assert driver.feed(0.0, 0.0, False) is None


# ---- ピッキング(§4.2) ----


def test_only_top_of_tower_is_grabbable() -> None:
    driver, _ = make("LMS//")
    # L1 は塔 A の一番下。真上からは S1 が当たるので S1 が掴まれる
    sx, sy = screen_of(layout.box_center(driver.board, "L1"))
    driver.feed(sx, sy, True)
    assert driver.dragging_box == "S1"
    driver.feed(sx, sy, False)
    # 偽シーンが L1 を返したとしても(別経路)掴めない
    assert driver.drag.press("L1") is False
    assert driver.drag.press("M1") is False


def test_all_staging_boxes_grabbable() -> None:
    driver, _ = make()
    for box_id in driver.board:
        sx, sy = screen_of(layout.box_center(driver.board, box_id))
        driver.feed(sx, sy, True)
        assert driver.dragging_box == box_id
        driver.feed(sx, sy, False)


# ---- ドラッグ中の追従・ハイライト ----


def test_lifted_position_follows_floor_point_and_keeps_last_when_ray_misses() -> None:
    driver, scene = make()
    sx, sy = screen_of(layout.box_center(driver.board, "M1"))
    driver.feed(sx, sy, True)
    driver.feed(50.0, -20.0, True)
    lifted = driver.lifted_position
    assert lifted is not None
    assert lifted == (0.5, layout.box_edge("M") * 1.5, -0.2)
    # レイが床を外れたフレームは直前の追従点を保持する
    scene.floor_hits = False
    driver.feed(999.0, 999.0, True)
    assert driver.lifted_position == lifted
    scene.floor_hits = True
    driver.feed(sx, sy, False)
    assert driver.lifted_position is None


def test_press_when_ray_misses_floor_uses_box_footprint() -> None:
    driver, scene = make()
    sx, sy = screen_of(layout.box_center(driver.board, "S1"))
    scene.floor_hits = False
    driver.feed(sx, sy, True)
    assert driver.dragging_box == "S1"
    cx, _, cz = layout.box_center(driver.board, "S1")
    lifted = driver.lifted_position
    assert lifted is not None and (lifted[0], lifted[2]) == (cx, cz)
    assert driver.target == StagingTarget(6)


def test_preview_green_red_none() -> None:
    driver, _ = make("M//")
    # L1 を掴み、塔 A(M の上 → 赤)、塔 B(空 → 緑)、塔の外(なし)へ動かす
    sx, sy = screen_of(layout.box_center(driver.board, "L1"))
    driver.feed(sx, sy, True)
    driver.feed(*screen_of(layout.tower_position("A")), True)
    assert driver.target == TowerTarget("A") and driver.preview is False
    driver.feed(*screen_of(layout.tower_position("B")), True)
    assert driver.target == TowerTarget("B") and driver.preview is True
    driver.feed(*screen_of((5.0, 0.0, 5.0)), True)
    assert driver.target is None and driver.preview is None
    # 待機エリアは常に緑。他サイズの列を指しても候補は自サイズ列の空き(L1 の元スロット 0)になる
    driver.feed(*screen_of(layout.staging_slot_position(7)), True)
    assert driver.target == StagingTarget(0) and driver.preview is True
    driver.feed(*screen_of((5.0, 0.0, 5.0)), False)


# ---- ドロップ(§4.4 / §4.5) ----


def test_legal_drop_updates_board() -> None:
    driver, _ = make()
    drag_to(driver, "L1", layout.tower_position("A"))
    assert driver.board.location("L1") == OnTower("A", 0)
    drag_to(driver, "M1", layout.tower_position("A"))
    drag_to(driver, "S1", layout.tower_position("A"))
    assert driver.board.board_string() == "LMS//"
    assert driver.target is None and driver.preview is None


def test_illegal_drop_returns_box_with_fail_outcome() -> None:
    driver, _ = make("S//")
    sx, sy = screen_of(layout.box_center(driver.board, "L1"))
    driver.feed(sx, sy, True)
    dx, dy = screen_of(layout.tower_position("A"))
    outcome = driver.feed(dx, dy, False)
    assert outcome is not None
    assert outcome.result is DropResult.RETURNED_ILLEGAL
    assert outcome.reason is RejectReason.LARGER_ON_SMALLER
    assert driver.board.location("L1") == InStaging(0)
    assert driver.board.board_string() == "S//"


def test_out_of_range_drop_returns_box() -> None:
    driver, _ = make()
    sx, sy = screen_of(layout.box_center(driver.board, "M2"))
    driver.feed(sx, sy, True)
    outcome = driver.feed(*screen_of((3.0, 0.0, 3.0)), False)
    assert outcome is not None and outcome.result is DropResult.RETURNED_OUT_OF_RANGE
    assert driver.board.location("M2") == InStaging(4)


def test_release_outside_window_cancels() -> None:
    driver, _ = make()
    sx, sy = screen_of(layout.box_center(driver.board, "S3"))
    driver.feed(sx, sy, True)
    driver.feed(*screen_of(layout.tower_position("C")), True)
    assert driver.preview is True
    outcome = driver.feed(-10.0, -10.0, False, inside=False)
    assert outcome is not None and outcome.result is DropResult.RETURNED_OUT_OF_RANGE
    assert driver.board.location("S3") == InStaging(8)
    assert driver.dragging_box is None


def test_staging_drop_goes_to_own_column() -> None:
    driver, _ = make("LMS//")
    # 塔 A の top(S1)を M 列のスロット 3 へ落とす → S 列の空き(S2, S3 が 6, 7 にいるので 8)
    sx, sy = screen_of(layout.box_center(driver.board, "S1"))
    driver.feed(sx, sy, True)
    driver.feed(*screen_of(layout.staging_slot_position(3)), True)
    assert driver.target == StagingTarget(8)  # ハイライトは実際に収まるスロット
    driver.feed(*screen_of(layout.staging_slot_position(3)), False)
    assert driver.board.location("S1") == InStaging(8)
    assert driver.board.board_string() == "LM//"


def test_round_trip_tower_to_staging_and_back() -> None:
    driver, _ = make()
    drag_to(driver, "L1", layout.tower_position("B"))
    # 埋まっているスロット 2(L3)へ落とす → L 列の空き(自分が空けたスロット 0)へ
    drag_to(driver, "L1", layout.staging_slot_position(2))
    assert driver.board.location("L1") == InStaging(0)
    assert driver.board.location("L3") == InStaging(2)
    drag_to(driver, "L1", layout.tower_position("C"))
    assert driver.board.board_string() == "//L"
