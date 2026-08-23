"""scene.picking のテスト: 既知のカメラ行列で中央・四隅、平面交点、cube の Mat4 との一致。"""

from __future__ import annotations

import importlib.util
import math

import pytest

from scene.picking import (
    CameraSpec,
    Ray,
    intersect_plane_y,
    invert,
    look_at,
    matrix_rows,
    project_point,
    screen_to_ndc,
    screen_to_ray,
    transform_point,
)

VIEWPORT = (0.0, 0.0, 320.0, 240.0)
IDENTITY = ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))
EYE = (0.0, 3.0, 4.0)
CAMERA = CameraSpec(look_at(EYE, (0.0, 0.0, 0.0)), fov_deg=60.0, near=0.1)


def test_screen_to_ndc_center_and_corners() -> None:
    assert screen_to_ndc(160, 120, VIEWPORT) == (0.0, 0.0)
    assert screen_to_ndc(0, 0, VIEWPORT) == (-1.0, 1.0)
    assert screen_to_ndc(320, 240, VIEWPORT) == (1.0, -1.0)
    # オフセット付きビューポート
    assert screen_to_ndc(10 + 50, 20 + 25, (10, 20, 100, 50)) == (0.0, 0.0)
    with pytest.raises(ValueError):
        screen_to_ndc(0, 0, (0, 0, 0, 10))


def test_identity_camera_center_ray_looks_down_minus_z() -> None:
    ray = screen_to_ray(160, 120, VIEWPORT, CameraSpec(IDENTITY))
    assert ray.origin == (0.0, 0.0, 0.0)
    assert ray.direction == pytest.approx((0.0, 0.0, -1.0))


def test_identity_camera_corners_hit_frustum_edges() -> None:
    """四隅のレイは視錐台の端: 縦 ±tan(fov/2)、横 ±tan(fov/2)*aspect。"""
    t = math.tan(math.radians(30.0))
    aspect = 320 / 240
    cam = CameraSpec(IDENTITY, fov_deg=60.0)
    expectations = {
        (0, 0): (-t * aspect, t, -1.0),  # 左上
        (320, 0): (t * aspect, t, -1.0),  # 右上
        (0, 240): (-t * aspect, -t, -1.0),  # 左下
        (320, 240): (t * aspect, -t, -1.0),  # 右下
    }
    for (sx, sy), expected in expectations.items():
        ray = screen_to_ray(sx, sy, VIEWPORT, cam)
        n = math.sqrt(sum(v * v for v in expected))
        assert ray.direction == pytest.approx(tuple(v / n for v in expected)), (sx, sy)
        assert math.isclose(math.sqrt(sum(v * v for v in ray.direction)), 1.0)


def test_look_at_center_ray_points_to_target() -> None:
    ray = screen_to_ray(160, 120, VIEWPORT, CAMERA)
    assert ray.origin == pytest.approx(EYE)
    expected = (-EYE[0], -EYE[1], -EYE[2])
    n = math.sqrt(sum(v * v for v in expected))
    assert ray.direction == pytest.approx(tuple(v / n for v in expected))
    # 中央レイとマット平面の交点は原点
    assert intersect_plane_y(ray) == pytest.approx((0.0, 0.0, 0.0), abs=1e-9)


def test_project_roundtrip_center_and_corners() -> None:
    """screen → ray → 平面交点 → project が元の画面座標に戻る。"""
    for sx, sy in ((160, 120), (0, 0), (320, 0), (0, 240), (320, 240), (37, 200)):
        ray = screen_to_ray(sx, sy, VIEWPORT, CAMERA)
        hit = intersect_plane_y(ray)
        assert hit is not None, (sx, sy)
        assert hit[1] == pytest.approx(0.0, abs=1e-9)
        assert project_point(hit, VIEWPORT, CAMERA) == pytest.approx((sx, sy), abs=1e-6)


def test_corner_rays_diverge_symmetrically() -> None:
    left = screen_to_ray(0, 120, VIEWPORT, CAMERA)
    right = screen_to_ray(320, 120, VIEWPORT, CAMERA)
    assert left.direction[0] == pytest.approx(-right.direction[0])
    assert left.direction[1] == pytest.approx(right.direction[1])
    top = intersect_plane_y(screen_to_ray(160, 0, VIEWPORT, CAMERA))
    bottom = intersect_plane_y(screen_to_ray(160, 239, VIEWPORT, CAMERA))
    assert top is not None and bottom is not None
    assert top[2] < 0 < bottom[2]  # 画面上側は奥(-z)、下側は手前(+z)


def test_intersect_plane_parallel_and_behind() -> None:
    assert intersect_plane_y(Ray((0.0, 1.0, 0.0), (1.0, 0.0, 0.0))) is None
    assert intersect_plane_y(Ray((0.0, 1.0, 0.0), (0.0, 1.0, 0.0))) is None  # 上向き
    down = Ray((0.0, 1.0, 0.0), (0.0, -1.0, 0.0))
    assert intersect_plane_y(down) == pytest.approx((0.0, 0.0, 0.0))
    assert intersect_plane_y(down, plane_y=0.5) == pytest.approx((0.0, 0.5, 0.0))


def test_invert_and_transform() -> None:
    m = look_at((1.0, 2.0, 3.0), (0.0, 0.5, 0.0))
    inv = invert(m)
    p = (0.3, -0.7, 1.1)
    assert transform_point(inv, transform_point(m, p)) == pytest.approx(p)
    with pytest.raises(ValueError):
        invert(((0.0,) * 4,) * 4)


def test_matrix_rows_accepts_nested_sequences() -> None:
    assert matrix_rows([list(r) for r in IDENTITY]) == IDENTITY
    with pytest.raises(ValueError):
        matrix_rows([[1.0, 2.0]])


def test_project_behind_camera_is_none() -> None:
    assert project_point((0.0, 0.0, 1.0), VIEWPORT, CameraSpec(IDENTITY)) is None
    assert project_point((0.0, 0.0, 0.0), VIEWPORT, CameraSpec(IDENTITY)) is None
    # near より手前でも前方なら投影する(cube の world_to_screen と同じ)
    assert project_point((0.0, 0.0, -0.05), VIEWPORT, CameraSpec(IDENTITY)) == (160.0, 120.0)


# ---- cube 実装との一致(pyxel が入っている環境のみ) ----


@pytest.mark.skipif(importlib.util.find_spec("pyxel") is None, reason="pyxel (cube) not installed")
def test_matches_cube_mat4() -> None:
    from pyxel.cube import Camera, Mat4, Vec3

    cam = Camera()
    cam.transform = Mat4.look_at(Vec3(*EYE), Vec3.ZERO)
    spec = CameraSpec.of(cam)
    assert spec.fov_deg == 60.0 and spec.near == pytest.approx(0.1)
    # 行列要素が純 Python 版と一致(f32 精度)
    for r in range(4):
        for c in range(4):
            expected = CAMERA.camera_to_world[r][c]
            assert spec.camera_to_world[r][c] == pytest.approx(expected, abs=1e-6)
    # Mat4 * Vec3 と transform_point が一致
    v = Vec3(0.3, -0.7, 1.1)
    w = cam.transform * v
    mine_p = transform_point(spec.camera_to_world, (0.3, -0.7, 1.1))
    assert mine_p == pytest.approx((w.x, w.y, w.z), abs=1e-6)
    # 逆行列も一致
    inv = matrix_rows(cam.transform.inverse())
    mine = invert(spec.camera_to_world)
    for r in range(4):
        for c in range(4):
            assert inv[r][c] == pytest.approx(mine[r][c], abs=1e-5)
