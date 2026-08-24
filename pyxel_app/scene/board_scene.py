"""3D 盤面シーン(仕様書 §6.3): Mat / Box x9 / Highlight の Node ツリー。Pyxel(cube)に依存する。

```
BoardScene(Node)               camera, shading
├── MatNode                    マット平面 + 塔マーカー(A/B/C)+ 待機スロットマーカー
├── BoxNode x 9                transform, collider(tag="box", trigger), 指数平滑化で目標位置へ追従
└── HighlightNode              ドロップ候補の枠(緑/赤。描画のみ、collider なし)
```

盤面の真値は `BoardState`、操作は `input/pointer.PointerDriver` が持つ。このモジュールは
「所在 → 描画位置」「画面座標 → 箱 / 床面の点」の橋渡しだけを行い、ゲームロジックは持たない。
`bind(driver)` で結線し、`sync(dt)` を毎フレーム呼ぶと目標位置とハイライトが更新される。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import pyxel
from pyxel.cube import Camera, Collider, Mat4, Node, Shading, Vec3

from app.core.board import Size, Tower
from board_state import BOX_EDGE_MM, BOX_IDS, STAGING_SLOT_COUNT, TOWERS, size_of, slot_size
from input.pointer import PointerDriver
from scene import layout, picking
from scene.layout import DropTarget, TowerTarget
from scene.smoothing import POS_LAMBDA, SmoothedPosition
from scene.textures import Textures

Vec = tuple[float, float, float]

TAG_BOX: Final = "box"

# ---- 見た目 ----
# テクスチャ(scene/textures.py)が読めた場合はそれを貼り、無い環境では以下の単色に縮退する
BOX_COLORS: Final[dict[Size, int]] = {"L": 12, "M": 11, "S": 10}  # 青系 / 緑系 / 黄系(§4.1)
BOX_OUTLINE: Final = 1
MAT_COLOR: Final = 13
MAT_THICKNESS: Final = 0.06
TOWER_MARKER_COLOR: Final = 5
SLOT_MARKER_COLOR: Final = 6
LABEL_COLOR: Final = 7
HIGHLIGHT_OK: Final = 11  # 緑
HIGHLIGHT_NG: Final = 8  # 赤
CLEAR_COLOR: Final = 1

# カメラ(§4.1: 正面やや上から見下ろす)。320x240 / fov 60 でマット全体が収まる位置
CAMERA_EYE: Final[Vec] = (0.0, 3.3, 1.5)
CAMERA_TARGET: Final[Vec] = (0.0, 0.2, -0.1)
CAMERA_FOV: Final = 60.0
LIGHT_DIRECTION: Final[Vec] = (0.5, -1.5, -1.0)

# マット面からわずかに浮かせて Z ファイトを避ける(depth_offset(-1.0) は箱まで透けるので使わない)
MARKER_Y: Final = 0.02
# マットのアートワークはタイル分割して貼る。1 枚のポリゴンに貼るとテクスチャが
# アフィン補間(透視補正なし)され、奥行きのある視点で絵がせん断するため
MAT_GRID: Final = (8, 6)
MAT_IMAGE_Y: Final = 0.005  # 台座上面との Z ファイト回避(マーカー MARKER_Y より下)
TOWER_MARKER_SIZE_MM: Final = 90.0
SLOT_MARKER_MARGIN_MM: Final = 6.0
HIGHLIGHT_MARGIN_MM: Final = 10.0


def _v(p: Vec) -> Vec3:
    return Vec3(p[0], p[1], p[2])


class MatNode(Node):
    """マット平面と塔・スロットのマーカー。"""

    def __init__(self, image: pyxel.Image | None = None) -> None:
        super().__init__()
        self.image = image
        w, h = (layout.mm(v) for v in layout.MAT_SIZE_MM)
        self.size = Vec3(w, MAT_THICKNESS, h)
        self.transform = Mat4.from_translation(Vec3(0.0, -MAT_THICKNESS / 2, 0.0))
        marker = layout.mm(TOWER_MARKER_SIZE_MM)
        self.tower_markers: list[tuple[Tower, Vec3]] = [
            (t, _v(layout.tower_position(t))) for t in TOWERS
        ]
        self.marker_size = Vec3(marker, 0.0, marker)
        self.slot_markers: list[tuple[Vec3, Vec3]] = []
        for slot in range(STAGING_SLOT_COUNT):
            edge = layout.mm(BOX_EDGE_MM[slot_size(slot)] + SLOT_MARKER_MARGIN_MM)
            pos = _v(layout.staging_slot_position(slot))
            self.slot_markers.append((pos, Vec3(edge, 0.0, edge)))

    def on_draw(self) -> None:
        self.box(Mat4.IDENTITY, self.size, MAT_COLOR)
        # 以降は陰影なし: アートワークは印刷物なので陰影を掛けない(シェーディングの
        # ランプで白がパレット内の別系統の明色に置き換わり色転びする)。マーカーも同様
        self.shaded(False)
        if self.image is not None:
            self._draw_image_tiles(self.size.y / 2 + MAT_IMAGE_Y)
        # マット上面(ローカル y = 厚み/2)に描く
        top = self.size.y / 2 + MARKER_Y
        for tower, pos in self.tower_markers:
            at = Vec3(pos.x, top, pos.z)
            if self.image is None:  # アートワーク側に塔の枠があるため塗りは縮退時のみ
                self.box(Mat4.from_translation(at), self.marker_size, TOWER_MARKER_COLOR)
            label = Vec3(pos.x, top + 0.02, pos.z + self.marker_size.z / 2 + 0.12)
            self.text(label, tower, LABEL_COLOR)
        for pos, size in self.slot_markers:
            self.boxb(Mat4.from_translation(Vec3(pos.x, top, pos.z)), size, SLOT_MARKER_COLOR)

    def _draw_image_tiles(self, y: float) -> None:
        """アートワークを MAT_GRID のタイルに分けて上面に貼る(アフィンのせん断を抑える)。"""
        assert self.image is not None
        nx, nz = MAT_GRID
        tile_w = self.size.x / nx
        tile_d = self.size.z / nz
        for gz in range(nz):
            v0, v1 = gz / nz, (gz + 1) / nz
            cz = -self.size.z / 2 + (gz + 0.5) * tile_d  # gz=0 が奥(-z)= 画像の上端
            for gx in range(nx):
                u0, u1 = gx / nx, (gx + 1) / nx
                cx = -self.size.x / 2 + (gx + 0.5) * tile_w
                mat = Mat4.from_translation(Vec3(cx, y, cz)).rotate_x(-90.0)
                uvs = ((u0, v0), (u1, v0), (u0, v1), (u1, v1))
                self.plane(mat, self.image, uvs, tile_w, tile_d)


class BoxNode(Node):
    """箱 1 個。`target` を指数平滑化で追いかける。"""

    def __init__(self, box_id: str, position: Vec, image: pyxel.Image | None = None) -> None:
        super().__init__()
        self.box_id = box_id
        self.name = box_id
        self.edge = layout.box_edge(size_of(box_id))
        self.color = BOX_COLORS[size_of(box_id)]
        self.image = image
        self.size = Vec3(self.edge, self.edge, self.edge)
        self.collider = Collider(size=self.size, trigger=True, mass=0.0)
        self.tags = [TAG_BOX]
        self.smooth = SmoothedPosition(position, POS_LAMBDA)
        self._apply(position)

    @property
    def position(self) -> Vec:
        return self.smooth.current

    def set_target(self, position: Vec, *, snap: bool = False) -> None:
        if snap:
            self.smooth.snap(position)
        else:
            self.smooth.target = position

    def step(self, dt_sec: float) -> None:
        self._apply(self.smooth.step(dt_sec))

    def _apply(self, position: Vec) -> None:
        self.transform = Mat4.from_translation(_v(position))

    def on_draw(self) -> None:
        self.box(Mat4.IDENTITY, self.size, self.color if self.image is None else self.image)
        self.boxb(Mat4.IDENTITY, self.size, BOX_OUTLINE)


class HighlightNode(Node):
    """ドロップ候補の枠。`set(target, ok)` で表示、`clear()` で非表示。"""

    def __init__(self) -> None:
        super().__init__()
        self.target: DropTarget | None = None
        self.ok = True
        self.visible = False
        self._size = Vec3.ZERO

    def set(self, target: DropTarget | None, ok: bool | None, box_edge_mm: float) -> None:
        if target is None or ok is None:
            self.clear()
            return
        self.target, self.ok, self.visible = target, ok, True
        if isinstance(target, TowerTarget):
            pos = layout.tower_position(target.tower)
            edge = layout.mm(TOWER_MARKER_SIZE_MM + HIGHLIGHT_MARGIN_MM)
        else:
            pos = layout.staging_slot_position(target.slot)
            edge = layout.mm(box_edge_mm + HIGHLIGHT_MARGIN_MM)
        self.transform = Mat4.from_translation(Vec3(pos[0], MARKER_Y * 1.5, pos[2]))
        self._size = Vec3(edge, 0.0, edge)

    def clear(self) -> None:
        self.target = None
        self.visible = False

    def on_draw(self) -> None:
        color = HIGHLIGHT_OK if self.ok else HIGHLIGHT_NG
        self.shaded(False)
        inner = Vec3(self._size.x - 0.06, 0.0, self._size.z - 0.06)
        self.boxb(Mat4.IDENTITY, self._size, color)
        self.boxb(Mat4.IDENTITY, inner, color)


class BoardScene(Node):
    """盤面シーン。`PointerDriver.SceneQuery` を実装する(`pick_box` / `floor_point`)。"""

    def __init__(
        self,
        colors: Sequence[int],
        width: int,
        height: int,
        textures: Textures | None = None,
    ) -> None:
        super().__init__()
        self.viewport: picking.Viewport = (0.0, 0.0, float(width), float(height))
        self.textures = textures if textures is not None else Textures()
        self.shading = Shading(list(colors))
        self.shading.direction = _v(LIGHT_DIRECTION).normalize()
        self.camera = Camera()
        self.camera.clear_color = CLEAR_COLOR
        self.camera.fov = CAMERA_FOV
        self.camera.transform = Mat4.look_at(_v(CAMERA_EYE), _v(CAMERA_TARGET))
        self.mat = MatNode(self.textures.mat)
        self.add_child(self.mat)
        self.boxes: dict[str, BoxNode] = {}
        self.highlight = HighlightNode()
        self._driver: PointerDriver | None = None

    # ---- 初期化 / 同期 ----

    def bind(self, driver: PointerDriver) -> None:
        """盤面と結線し、箱ノードを現在の所在に置く(初回は即座に配置)。"""
        self._driver = driver
        for node in self.boxes.values():
            node.destroy()
        self.boxes = {}
        for box_id in BOX_IDS:
            image = self.textures.boxes.get(size_of(box_id))
            node = BoxNode(box_id, layout.box_center(driver.board, box_id), image)
            self.boxes[box_id] = node
            self.add_child(node)
        if self.highlight.parent is None:
            self.add_child(self.highlight)

    def sync(self, dt_sec: float) -> None:
        """所在 → 目標位置、ドラッグ中の箱 → 追従点、ハイライトの順に更新し 1 ステップ進める。"""
        driver = self._driver
        assert driver is not None, "bind() before sync()"
        dragging = driver.dragging_box
        lifted = driver.lifted_position
        for box_id, node in self.boxes.items():
            if box_id == dragging and lifted is not None:
                node.set_target(lifted, snap=True)
            else:
                node.set_target(layout.box_center(driver.board, box_id))
            node.step(dt_sec)
        edge_mm = BOX_EDGE_MM[size_of(dragging)] if dragging is not None else 0.0
        self.highlight.set(driver.target, driver.preview, edge_mm)
        self.update()

    # ---- SceneQuery ----

    def camera_spec(self) -> picking.CameraSpec:
        assert self.camera is not None
        return picking.CameraSpec.of(self.camera)

    def ray(self, sx: float, sy: float) -> picking.Ray:
        return picking.screen_to_ray(sx, sy, self.viewport, self.camera_spec())

    def pick_box(self, sx: float, sy: float) -> str | None:
        ray = self.ray(sx, sy)
        hit = self.raycast(_v(ray.origin), _v(ray.direction), hit_triggers=True, tags=[TAG_BOX])
        if hit is None:
            return None
        node = hit.node
        return node.box_id if isinstance(node, BoxNode) else None

    def floor_point(self, sx: float, sy: float) -> Vec | None:
        return picking.intersect_plane_y(self.ray(sx, sy))

    def project(self, point: Vec) -> tuple[float, float] | None:
        """ワールド点 → 画面座標(テスト・デバッグ用)。"""
        return picking.project_point(point, self.viewport, self.camera_spec())

    def draw_to(self, x: int, y: int, w: int, h: int) -> None:
        self.draw(x, y, w, h)


__all__ = [
    "TAG_BOX",
    "BoardScene",
    "BoxNode",
    "HighlightNode",
    "MatNode",
]
