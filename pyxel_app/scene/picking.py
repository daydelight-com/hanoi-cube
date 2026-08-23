"""画面座標 → レイ、マット平面(y=0)との交点(仕様書 §4.3 / §4.4)。Pyxel に依存しない。

cube の `Camera` には画面→レイの API が無いので自前で計算する。規約は cube `raster.rs` に合わせる。

- `Camera.transform` はカメラ→ワールド行列(行優先、列ベクトル `M * v`)。ビュー行列はその逆行列
- 透視投影: `fov` は縦の画角(度)、`aspect = vp_w / vp_h`、カメラは -Z を向く(`Mat4.look_at`)
- スクリーン: `sx = vp_x + (ndc_x + 1) / 2 * vp_w`、`sy = vp_y + (1 - (ndc_y + 1) / 2) * vp_h`
  (画面の上が NDC の +y)

行列は `Mat4` でも 4x4 の入れ子シーケンスでもよい(`matrix_rows()` で正規化する)。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

Vec = tuple[float, float, float]
Matrix = tuple[tuple[float, float, float, float], ...]
Viewport = tuple[float, float, float, float]  # (x, y, w, h) ピクセル


class CameraLike(Protocol):
    """cube の `Camera` 相当(`transform` / `fov` / `near`)。"""

    @property
    def transform(self) -> SupportsMatrixIndex: ...
    @property
    def fov(self) -> float: ...
    @property
    def near(self) -> float: ...


class SupportsMatrixIndex(Protocol):
    """`mat[(row, col)]` で要素を読める行列(cube の `Mat4` が該当)。"""

    def __getitem__(self, key: tuple[int, int]) -> float: ...


def matrix_rows(mat: SupportsMatrixIndex | Sequence[Sequence[float]]) -> Matrix:
    """行列を 4x4 のタプルに正規化する。"""
    if isinstance(mat, Sequence):
        rows = tuple(tuple(float(v) for v in row) for row in mat)
    else:
        rows = tuple(tuple(float(mat[(r, c)]) for c in range(4)) for r in range(4))
    if len(rows) != 4 or any(len(r) != 4 for r in rows):
        raise ValueError("matrix must be 4x4")
    return rows  # type: ignore[return-value]


@dataclass(frozen=True)
class Ray:
    origin: Vec
    direction: Vec  # 単位ベクトル

    def at(self, t: float) -> Vec:
        o, d = self.origin, self.direction
        return (o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t)


@dataclass(frozen=True)
class CameraSpec:
    """レイ計算に必要なカメラ情報(`Camera` から写す)。"""

    camera_to_world: Matrix
    fov_deg: float = 60.0
    near: float = 0.1

    @classmethod
    def of(cls, camera: CameraLike) -> CameraSpec:
        """cube の `Camera` から生成する(`transform` / `fov` / `near` 属性を読む)。"""
        return cls(matrix_rows(camera.transform), float(camera.fov), float(camera.near))


def transform_point(m: Matrix, p: Vec) -> Vec:
    """`M * (p, 1)` の xyz(w=1 前提)。"""
    return tuple(m[r][0] * p[0] + m[r][1] * p[1] + m[r][2] * p[2] + m[r][3] for r in range(3))  # type: ignore[return-value]


def transform_dir(m: Matrix, d: Vec) -> Vec:
    """`M * (d, 0)` の xyz(平行移動を無視)。"""
    return tuple(m[r][0] * d[0] + m[r][1] * d[1] + m[r][2] * d[2] for r in range(3))  # type: ignore[return-value]


def normalize(v: Vec) -> Vec:
    n = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if n == 0.0:
        raise ValueError("zero vector")
    return (v[0] / n, v[1] / n, v[2] / n)


def screen_to_ndc(sx: float, sy: float, viewport: Viewport) -> tuple[float, float]:
    """ビューポート内ピクセル → NDC(-1..1、上が +y)。"""
    vx, vy, vw, vh = viewport
    if vw <= 0 or vh <= 0:
        raise ValueError("viewport must have positive size")
    return ((sx - vx) / vw * 2.0 - 1.0, 1.0 - (sy - vy) / vh * 2.0)


def screen_to_ray(sx: float, sy: float, viewport: Viewport, camera: CameraSpec) -> Ray:
    """画面座標(ピクセル)→ ワールド空間のレイ(透視投影)。origin はカメラ位置。"""
    ndc_x, ndc_y = screen_to_ndc(sx, sy, viewport)
    aspect = viewport[2] / viewport[3]
    t = math.tan(math.radians(camera.fov_deg) * 0.5)
    local_dir: Vec = (ndc_x * t * aspect, ndc_y * t, -1.0)
    m = camera.camera_to_world
    origin = transform_point(m, (0.0, 0.0, 0.0))
    direction = normalize(transform_dir(m, local_dir))
    return Ray(origin, direction)


def intersect_plane_y(ray: Ray, plane_y: float = 0.0) -> Vec | None:
    """レイと水平面 y=plane_y の交点。平行・後方(t<=0)なら None。"""
    dy = ray.direction[1]
    if abs(dy) < 1e-9:
        return None
    t = (plane_y - ray.origin[1]) / dy
    if t <= 0.0:
        return None
    return ray.at(t)


def invert(m: Matrix) -> Matrix:
    """4x4 の逆行列(ガウス・ジョルダン)。特異なら ValueError。"""
    n = 4
    a = [list(m[r]) + [1.0 if r == c else 0.0 for c in range(n)] for r in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[pivot][col]) < 1e-12:
            raise ValueError("singular matrix")
        a[col], a[pivot] = a[pivot], a[col]
        p = a[col][col]
        a[col] = [v / p for v in a[col]]
        for r in range(n):
            if r != col and a[r][col] != 0.0:
                f = a[r][col]
                a[r] = [rv - f * cv for rv, cv in zip(a[r], a[col], strict=True)]
    return matrix_rows([row[n:] for row in a])


def project_point(p: Vec, viewport: Viewport, camera: CameraSpec) -> tuple[float, float] | None:
    """ワールド点 → 画面座標(ピクセル)。カメラ平面より後方(cz >= 0)なら None。検証・デバッグ用。

    cube の `world_to_screen` と同じく near より手前でも投影する(near クリップは描画側の責務)。
    """
    view = invert(camera.camera_to_world)
    cx, cy, cz = transform_point(view, p)
    if -cz <= 0.0:
        return None
    aspect = viewport[2] / viewport[3]
    f = 1.0 / math.tan(math.radians(camera.fov_deg) * 0.5)
    ndc_x = (f / aspect) * cx / -cz
    ndc_y = f * cy / -cz
    vx, vy, vw, vh = viewport
    return (vx + (ndc_x + 1.0) * 0.5 * vw, vy + (1.0 - (ndc_y + 1.0) * 0.5) * vh)


def look_at(eye: Vec, target: Vec, up: Vec = (0.0, 1.0, 0.0)) -> Matrix:
    """cube の `Mat4.look_at` と同じカメラ→ワールド行列(右手系、forward = -Z)。純 Python 版。"""
    f = normalize((target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]))
    s = _cross(f, up)
    if s[0] ** 2 + s[1] ** 2 + s[2] ** 2 < 1e-12:
        alt: Vec = (0.0, 0.0, 1.0) if abs(f[1]) > 0.9 else (0.0, 1.0, 0.0)
        s = _cross(f, alt)
    s = normalize(s)
    u = _cross(s, f)
    return (
        (s[0], u[0], -f[0], eye[0]),
        (s[1], u[1], -f[1], eye[1]),
        (s[2], u[2], -f[2], eye[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
