"""scene.board_scene のテスト(pyxel がある環境のみ。描画はしない)。

cube の `Node` / `Collider` / `raycast` は `pyxel.init()` 無しで動くので、
実カメラでのピッキング(投影 → レイ → コライダー)とドラッグ結線を本物の Node ツリーで確かめる。
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

import pytest

from board_state import BOX_IDS, BoardState, InStaging, OnTower
from input.drag import DragController
from input.pointer import PointerDriver
from scene import layout
from scene.layout import StagingTarget, TowerTarget

if TYPE_CHECKING:
    from scene.board_scene import BoardScene

Vec = tuple[float, float, float]

HAS_PYXEL = importlib.util.find_spec("pyxel") is not None
pytestmark = pytest.mark.skipif(not HAS_PYXEL, reason="pyxel が未導入(macOS arm64 以外)")

WIDTH, HEIGHT = 320, 240
DT = 1 / 60


def make(board: str | None = None) -> tuple[BoardScene, PointerDriver]:
    from scene.board_scene import BoardScene

    state = BoardState.initial() if board is None else BoardState.from_board(board)
    scene = BoardScene(list(range(16)), WIDTH, HEIGHT)
    driver = PointerDriver(DragController(state), scene)
    scene.bind(driver)
    scene.sync(DT)
    return scene, driver


def screen_of(scene: BoardScene, point: Vec) -> tuple[float, float]:
    s = scene.project(point)
    assert s is not None
    return s


def test_scene_tree_matches_spec() -> None:
    from scene.board_scene import TAG_BOX, BoxNode, HighlightNode, MatNode

    scene, _ = make()
    kinds = [type(c) for c in scene.children]
    assert kinds.count(MatNode) == 1 and kinds.count(HighlightNode) == 1
    assert kinds.count(BoxNode) == 9
    assert len(scene.find_by_tags([TAG_BOX])) == 9
    assert scene.highlight.visible is False
    assert scene.camera is not None and scene.shading is not None
    for node in scene.boxes.values():
        assert node.collider is not None and node.collider.trigger


def test_mat_fits_in_viewport() -> None:
    scene, _ = make()
    w, h = layout.MAT_SIZE_MM
    for corner in ((0.0, 0.0), (w, 0.0), (0.0, h), (w, h)):
        sx, sy = screen_of(scene, layout.mat_to_world(*corner))
        assert 0 <= sx <= WIDTH and 0 <= sy <= HEIGHT, corner
    # 3 段積み(LMS、高さ 155mm)の上面も見える
    top = (0.0, layout.mm(155.0), layout.tower_position("B")[2])
    assert screen_of(scene, top)[1] > 0
    # 手前段の L 箱の上面(一番下に映る)も画面内
    lx, _, lz = layout.staging_slot_position(1)
    assert screen_of(scene, (lx, layout.box_edge("L"), lz + layout.box_edge("L") / 2))[1] < HEIGHT


def test_tower_bases_not_occluded_by_staging_boxes() -> None:
    """全箱が待機エリアにあるとき、各塔の床マーカー中心をクリックしても箱に当たらない(視線が遮られない)。"""
    scene, _ = make()
    for tower in ("A", "B", "C"):
        sx, sy = screen_of(scene, layout.tower_position(tower))
        assert scene.pick_box(sx, sy) is None, tower


def test_every_box_pickable_at_projected_center() -> None:
    scene, driver = make()
    for box_id in BOX_IDS:
        center = layout.box_center(driver.board, box_id)
        assert scene.pick_box(*screen_of(scene, center)) == box_id


def test_pick_returns_none_off_boxes_and_floor_point_is_on_mat() -> None:
    scene, _ = make()
    sx, sy = screen_of(scene, layout.tower_position("B"))
    assert scene.pick_box(sx, sy) is None
    point = scene.floor_point(sx, sy)
    assert point is not None
    assert point == pytest.approx(layout.tower_position("B"), abs=1e-4)
    # 画面上端はマットの奥端(z = -1.485)より遠くに落ちる
    far = scene.floor_point(160, 0)
    assert far is None or far[2] < -layout.mm(layout.MAT_SIZE_MM[1]) / 2


def test_stacked_tower_only_top_is_picked() -> None:
    scene, driver = make("LMS//")
    # 塔 A の L1 の側面の投影点を押しても、見えているのは L1 なので掴めない(top は S1)
    l_center = layout.box_center(driver.board, "L1")
    sx, sy = screen_of(scene, (l_center[0], l_center[1], l_center[2] + layout.box_edge("L") / 2))
    assert scene.pick_box(sx, sy) == "L1"
    assert driver.feed(sx, sy, True) is None and driver.dragging_box is None
    driver.feed(sx, sy, False)
    # S1 の中心は掴める
    s_center = layout.box_center(driver.board, "S1")
    sx, sy = screen_of(scene, s_center)
    driver.feed(sx, sy, True)
    assert driver.dragging_box == "S1"
    driver.feed(sx, sy, False)


def test_drag_and_drop_through_real_scene() -> None:
    scene, driver = make()
    # L1 を塔 A へ
    sx, sy = screen_of(scene, layout.box_center(driver.board, "L1"))
    driver.feed(sx, sy, True)
    scene.sync(DT)
    tx, ty = screen_of(scene, layout.tower_position("A"))
    driver.feed(tx, ty, True)
    scene.sync(DT)
    assert driver.target == TowerTarget("A") and driver.preview is True
    assert scene.highlight.visible and scene.highlight.ok
    # ドラッグ中の箱は持ち上がって追従点の真上
    lifted = scene.boxes["L1"].position
    assert lifted[1] == pytest.approx(layout.box_edge("L") * 1.5)
    assert (lifted[0], lifted[2]) == pytest.approx(layout.tower_position("A")[0::2], abs=1e-3)
    outcome = driver.feed(tx, ty, False)
    assert outcome is not None and outcome.placed
    assert driver.board.location("L1") == OnTower("A", 0)
    scene.sync(DT)
    assert not scene.highlight.visible
    # 指数平滑化で目標位置へ収束する(1 秒で吸着)
    target = layout.box_center(driver.board, "L1")
    assert scene.boxes["L1"].position != target
    for _ in range(60):
        scene.sync(DT)
    assert scene.boxes["L1"].position == target
    # 置いた L1 は塔上でも掴める(top)
    assert scene.pick_box(*screen_of(scene, target)) == "L1"


def test_illegal_drop_shows_red_and_returns() -> None:
    scene, driver = make("S//")
    sx, sy = screen_of(scene, layout.box_center(driver.board, "L1"))
    driver.feed(sx, sy, True)
    tx, ty = screen_of(scene, layout.tower_position("A"))
    driver.feed(tx, ty, True)
    scene.sync(DT)
    assert scene.highlight.visible and scene.highlight.ok is False
    outcome = driver.feed(tx, ty, False)
    assert outcome is not None and not outcome.placed
    assert driver.board.location("L1") == InStaging(0)
    for _ in range(60):
        scene.sync(DT)
    assert scene.boxes["L1"].position == layout.box_center(driver.board, "L1")


def test_staging_highlight_uses_box_size() -> None:
    scene, driver = make()
    sx, sy = screen_of(scene, layout.box_center(driver.board, "S2"))
    driver.feed(sx, sy, True)
    tx, ty = screen_of(scene, layout.staging_slot_position(0))
    driver.feed(tx, ty, True)
    scene.sync(DT)
    # L 列のスロット 0(L1 が使用中)を指しても、候補は S2 自身のスロット 7
    assert driver.target == StagingTarget(7) and scene.highlight.ok
    driver.feed(tx, ty, False)
    assert driver.board.location("S2") == InStaging(7)


def test_rebind_replaces_boxes() -> None:
    from scene.board_scene import BoxNode

    scene, _ = make()
    state = BoardState.from_board("L//")
    driver = PointerDriver(DragController(state), scene)
    scene.bind(driver)
    scene.sync(DT)
    assert sum(isinstance(c, BoxNode) for c in scene.children) == 9
    assert scene.boxes["L1"].position == layout.box_center(state, "L1")
