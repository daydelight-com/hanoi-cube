"""実CVテスト用の合成3Dシーンレンダラ。

マット(四隅タグ付き)と箱(6面タグ付き)を既知のカメラで透視投影レンダリングし、
検出器〜幾何〜盤面構成のパイプライン全体を実カメラなしで検証する。
仕様§2.2の幾何(俯瞰30〜45°・1080p級)を模す。タグ画像は
scripts/apriltag_imgs/tag36h11 の公式ビットマップを使う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np
import numpy.typing as npt
from app.cv.interface import BOX_EDGE_MM, BOX_IDS, BOX_SIZE_OF, BoxId
from app.cv.layout import (
    MAT_SIZE_MM,
    MAT_TAG_BLACK_MM,
    MAT_TAG_CENTERS_MM,
    STAGING_Y_MM,
    STICKER_HALF_MM,
    TOWER_X_MM,
    TOWER_Y_MM,
)
from app.cv.tag_master import TagMaster, TagSpec

Arr = npt.NDArray[np.float64]

REPO_ROOT = Path(__file__).resolve().parents[2]
TAG_DIR = REPO_ROOT / "scripts" / "apriltag_imgs" / "tag36h11"

# tag36h11 公式画像: 10x10セル(黒枠正方形8x8 + 白余白1セル)
CELLS = 10
BLACK_CELLS = 8
UPSCALE = 24  # 1セル→24px に拡大してから射影(エイリアス低減)

# 黒枠半辺=1 とするタグ座標系(x=右, y=上)のコーナー順(geometry.TAG_CORNER_LOCAL と同義)
CORNER_LOCAL: Arr = np.array([[-1.0, -1.0], [1.0, -1.0], [1.0, 1.0], [-1.0, 1.0]], dtype=np.float64)


@lru_cache(maxsize=64)
def _tag_image(tag_id: int) -> npt.NDArray[np.uint8]:
    path = TAG_DIR / f"tag36_11_{tag_id:05d}.png"
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    assert img is not None and img.shape == (CELLS, CELLS), path
    up = cv2.resize(img, (CELLS * UPSCALE, CELLS * UPSCALE), interpolation=cv2.INTER_NEAREST)
    return np.asarray(up, dtype=np.uint8)


@dataclass(frozen=True)
class SceneCamera:
    """既知カメラ(検証用の正解値)。X_cam = R @ X_mat + t。"""

    k: Arr
    r: Arr
    t: Arr
    image_size: tuple[int, int]

    def project(self, points_mat: Arr) -> Arr:
        """マット座標(N,3)→画像px(N,2)。"""
        p_cam = (self.r @ points_mat.T).T + self.t
        uvw = (self.k @ p_cam.T).T
        result: Arr = uvw[:, :2] / uvw[:, 2:3]
        return result

    @property
    def position(self) -> Arr:
        pos: Arr = -self.r.T @ self.t
        return pos


def make_camera(
    *,
    focal: float = 2300.0,
    image_size: tuple[int, int] = (1920, 1080),
    position: tuple[float, float, float] = (300.0, -500.0, 600.0),
    target: tuple[float, float, float] = (300.0, 200.0, 0.0),
) -> SceneCamera:
    """マット手前上方からの俯瞰カメラ(仕様§2.2)。

    既定値は本番幾何相当: 1080p・マット中心で約2.5px/mm・俯瞰角約40°。
    """
    pos = np.array(position, dtype=np.float64)
    z_c = np.array(target, dtype=np.float64) - pos
    z_c /= np.linalg.norm(z_c)
    up = np.array([0.0, 0.0, 1.0])
    x_c = np.cross(z_c, up)
    x_c /= np.linalg.norm(x_c)
    y_c = np.cross(z_c, x_c)
    r = np.vstack([x_c, y_c, z_c])
    t = -r @ pos
    w, h = image_size
    k = np.array([[focal, 0.0, w / 2.0], [0.0, focal, h / 2.0], [0.0, 0.0, 1.0]], dtype=np.float64)
    return SceneCamera(k=k, r=r, t=t, image_size=image_size)


@dataclass(frozen=True)
class PlacedTag:
    """レンダリングした1タグの正解値。"""

    tag_id: int
    corners_mat: Arr  # (4,3) CORNER_LOCAL 順のマット座標
    corners_px: Arr  # (4,2) 投影後


@dataclass
class BoxPose:
    """シーンに置く箱。底面中心 (x, y, z) と鉛直軸まわりの回転(度)。"""

    box_id: BoxId
    pos: tuple[float, float, float]
    yaw_deg: float = 0.0


@dataclass
class Scene:
    boxes: list[BoxPose] = field(default_factory=list)
    hidden_tag_ids: set[int] = field(default_factory=set)  # 遮蔽シミュレーション


def _paste_tag(
    canvas: npt.NDArray[np.uint8],
    camera: SceneCamera,
    tag_id: int,
    corners_mat: Arr,
    sticker_margin_mm: float,
    black_mm: float,
) -> PlacedTag:
    """タグ(白シール背景ごと)を射影して canvas に貼る。corners_mat は CORNER_LOCAL 順。"""
    corners_px = camera.project(corners_mat)

    # シール白地(タグ白余白セル+印刷余白)を先に塗る
    center = corners_mat.mean(axis=0)
    sticker_scale = (black_mm / 2.0 + black_mm / BLACK_CELLS + sticker_margin_mm) / (black_mm / 2.0)
    sticker_mat = center + (corners_mat - center) * sticker_scale
    sticker_px = camera.project(sticker_mat).astype(np.int32)
    cv2.fillConvexPoly(canvas, sticker_px, 255)

    # 公式画像の黒枠コーナー(px, y下向き)→ CORNER_LOCAL 対応
    s = UPSCALE
    src = np.array(
        [
            [1 * s, 9 * s],  # (-1,-1) 左下
            [9 * s, 9 * s],  # (+1,-1) 右下
            [9 * s, 1 * s],  # (+1,+1) 右上
            [1 * s, 1 * s],  # (-1,+1) 左上
        ],
        dtype=np.float32,
    )
    m = cv2.getPerspectiveTransform(src, corners_px.astype(np.float32))
    tag_img = _tag_image(tag_id)
    warped = cv2.warpPerspective(
        tag_img,
        m,
        (canvas.shape[1], canvas.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    mask = cv2.warpPerspective(
        np.full(tag_img.shape, 255, np.uint8),
        m,
        (canvas.shape[1], canvas.shape[0]),
        flags=cv2.INTER_NEAREST,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=0,
    )
    np.copyto(canvas, warped, where=mask > 127)
    return PlacedTag(tag_id=tag_id, corners_mat=corners_mat, corners_px=corners_px)


def render_scene(
    scene: Scene, camera: SceneCamera | None = None
) -> tuple[npt.NDArray[np.uint8], dict[int, PlacedTag]]:
    """シーンをレンダリングし、(グレースケール画像, 描画したタグの正解値) を返す。"""
    camera = camera or make_camera()
    w, h = camera.image_size
    canvas = np.full((h, w), 190, np.uint8)

    # マット面
    mw, mh = MAT_SIZE_MM
    mat_rect = np.array([[0.0, 0.0, 0.0], [mw, 0.0, 0.0], [mw, mh, 0.0], [0.0, mh, 0.0]])
    cv2.fillConvexPoly(canvas, camera.project(mat_rect).astype(np.int32), 225)

    placed: dict[int, PlacedTag] = {}

    # マット四隅タグ(z=0、タグ上=+y向きに印刷)
    for tag_id, (cx, cy) in MAT_TAG_CENTERS_MM.items():
        if tag_id in scene.hidden_tag_ids:
            continue
        half = MAT_TAG_BLACK_MM / 2.0
        corners = np.array([[cx + lx * half, cy + ly * half, 0.0] for lx, ly in CORNER_LOCAL])
        placed[tag_id] = _paste_tag(canvas, camera, tag_id, corners, 2.0, MAT_TAG_BLACK_MM)

    # 箱(カメラから遠い順に描画)
    cam_pos = camera.position
    for box in sorted(
        scene.boxes,
        key=lambda b: -float(np.linalg.norm(np.array(b.pos, dtype=np.float64) - cam_pos)),
    ):
        _render_box(canvas, camera, box, scene.hidden_tag_ids, placed)

    return canvas, placed


def _render_box(
    canvas: npt.NDArray[np.uint8],
    camera: SceneCamera,
    box: BoxPose,
    hidden: set[int],
    placed: dict[int, PlacedTag],
) -> None:
    size = BOX_SIZE_OF[box.box_id]
    edge = BOX_EDGE_MM[size]
    black_mm = 20.8 if size == "small" else 16.0
    box_index = BOX_IDS.index(box.box_id)
    yaw = np.deg2rad(box.yaw_deg)
    rot = np.array(
        [
            [np.cos(yaw), -np.sin(yaw), 0.0],
            [np.sin(yaw), np.cos(yaw), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    center = np.array(box.pos, dtype=np.float64) + np.array([0.0, 0.0, edge / 2.0])

    # 面 1..4=側面(+y,+x,-y,-x)、5=上面。面座標系: normal(外向き), u(右), v(上)
    ez = np.array([0.0, 0.0, 1.0])
    faces: list[tuple[int, Arr, Arr, Arr]] = []
    side_normals = [
        np.array([0.0, 1.0, 0.0]),
        np.array([1.0, 0.0, 0.0]),
        np.array([0.0, -1.0, 0.0]),
        np.array([-1.0, 0.0, 0.0]),
    ]
    for i, n_local in enumerate(side_normals):
        n = rot @ n_local
        u = np.cross(ez, n)  # 面を正面に見て右向き
        faces.append((i + 1, n, u, ez))
    faces.append((5, ez, rot @ np.array([1.0, 0.0, 0.0]), rot @ np.array([0.0, 1.0, 0.0])))

    cam_pos = camera.position
    for face_idx, n, u, v in faces:
        face_center = center + n * (edge / 2.0)
        if float(np.dot(n, cam_pos - face_center)) <= 0.05:
            continue
        # 面の塗り
        quad = np.array(
            [
                face_center + (u * su + v * sv) * (edge / 2.0)
                for su, sv in [(-1, -1), (1, -1), (1, 1), (-1, 1)]
            ]
        )
        cv2.fillConvexPoly(canvas, camera.project(quad).astype(np.int32), 170)

        tag_id = box_index * 6 + (face_idx - 1)
        if tag_id in hidden:
            continue
        # タグ中心: 大・中は右上隅(隅から12mm)、小は面中央
        if size == "small":
            tag_center = face_center
        else:
            inset = edge / 2.0 - STICKER_HALF_MM
            tag_center = face_center + u * inset + v * inset
        half = black_mm / 2.0
        corners = np.array(
            [tag_center + u * (lx * half) + v * (ly * half) for lx, ly in CORNER_LOCAL]
        )
        placed[tag_id] = _paste_tag(canvas, camera, tag_id, corners, 2.0, black_mm)


# ---- 論理盤面 → シーン配置(通しプレイ動画の生成に使う) ----

# 待機エリアの箱位置(箱ごとに固定スロット)。モックのピッチ60mmでは大箱(75mm)が
# 物理的に重なるため、サイズを考慮した重なりのない配置にする。マット幅600mmに収まる
STAGING_SLOT_X_MM: dict[BoxId, float] = {
    "large-1": 50.0,
    "large-2": 130.0,
    "large-3": 210.0,
    "medium-1": 285.0,
    "medium-2": 345.0,
    "medium-3": 405.0,
    "small-1": 465.0,
    "small-2": 510.0,
    "small-3": 555.0,
}


def staging_pos(box_id: BoxId) -> tuple[float, float, float]:
    return (STAGING_SLOT_X_MM[box_id], STAGING_Y_MM, 0.0)


def scene_from_layout(
    stacks: dict[str, list[BoxId]],
    staging: list[BoxId],
    held: BoxId | None = None,
    held_pos: tuple[float, float, float] = (300.0, 180.0, 120.0),
) -> Scene:
    """論理盤面をシーンに落とす。待機箱は STAGING_SLOT_X_MM の固定スロットに置く。"""
    boxes: list[BoxPose] = []
    for tower, stack in stacks.items():
        z = 0.0
        for box_id in stack:
            boxes.append(BoxPose(box_id=box_id, pos=(TOWER_X_MM[tower], TOWER_Y_MM, z)))
            z += BOX_EDGE_MM[BOX_SIZE_OF[box_id]]
    for box_id in staging:
        boxes.append(BoxPose(box_id=box_id, pos=staging_pos(box_id)))
    if held is not None:
        boxes.append(BoxPose(box_id=held, pos=held_pos))
    return Scene(boxes=boxes)


# ---- タグマスタ(レンダラのID体系 = 本番の tag_master.json と同一規則) ----


def _black_mm_of(size: str) -> float:
    return 20.8 if size == "small" else 16.0


def synthetic_tag_master() -> TagMaster:
    """レンダラと同じID体系(id = box_index*6 + face-1)のタグマスタを合成する。

    テストを output/tag_master.json(gitignore下)の生成状態に依存させないため。
    """
    tags: dict[int, TagSpec] = {}
    for i, box_id in enumerate(BOX_IDS):
        size = BOX_SIZE_OF[box_id]
        for face in range(1, 7):
            tag_id = i * 6 + face - 1
            tags[tag_id] = TagSpec(
                tag_id=tag_id,
                box_id=box_id,
                size=size,
                face=face,
                black_mm=_black_mm_of(size),
            )
    return TagMaster(box_tags=tags)


def synthetic_tag_master_json() -> dict[str, object]:
    """load_tag_master() が読める形のJSON(ワーカープロセスへ渡すファイル用)。"""
    return {
        "box_tags": [
            {
                "id": spec.tag_id,
                "box": spec.box_id,
                "size": spec.size,
                "face": spec.face,
                "black_mm": spec.black_mm,
            }
            for spec in synthetic_tag_master().box_tags.values()
        ]
    }
