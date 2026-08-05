"""実CVの幾何変換(app/cv/geometry.py)のテスト。

合成3Dシーン(cv_scene.py)を実際に pupil-apriltags へ通し、
コーナー順序の規約・自己キャリブレーション・箱位置解決の精度をピン留めする。
"""

from __future__ import annotations

import numpy as np
import pytest
from app.cv import geometry
from app.cv.interface import BOX_EDGE_MM, BOX_IDS, BOX_SIZE_OF, BoxId
from pupil_apriltags import Detector

from tests.cv_scene import BoxPose, Scene, make_camera, render_scene, scene_from_layout


@pytest.fixture(scope="module")
def detector() -> Detector:
    # docs/cv_poc.md §4 で決定した本番初期値
    return Detector(
        families="tag36h11",
        nthreads=4,
        quad_decimate=2.0,
        quad_sigma=0.0,
        refine_edges=True,
        decode_sharpening=0.25,
    )


def test_homography_roundtrip() -> None:
    rng = np.random.default_rng(1)
    h_true = np.array([[1.2, 0.1, 30.0], [-0.05, 0.9, 200.0], [1e-4, -2e-4, 1.0]])
    src = rng.uniform(0, 500, (8, 2))
    src_h = np.hstack([src, np.ones((8, 1))])
    dst_h = (h_true @ src_h.T).T
    dst = dst_h[:, :2] / dst_h[:, 2:3]
    h = geometry.homography(src, dst)
    assert np.allclose(h, h_true / h_true[2, 2], atol=1e-6)


def test_estimate_focal_and_pose_exact() -> None:
    """厳密な合成カメラのマット平面ホモグラフィから K と姿勢を復元できる。"""
    cam = make_camera()
    rng = np.random.default_rng(2)
    pts_mm = rng.uniform([0, 0], [600, 400], (12, 2))
    pts3 = np.hstack([pts_mm, np.zeros((12, 1))])
    px = cam.project(pts3)
    h = geometry.homography(pts_mm, px)
    f = geometry.estimate_focal(h, cam.k[0, 2], cam.k[1, 2])
    assert f == pytest.approx(cam.k[0, 0], rel=0.01)
    r, t = geometry.pose_from_homography(h, cam.k)
    assert np.allclose(r, cam.r, atol=1e-3)
    assert np.allclose(t, cam.t, atol=1.0)


def test_detector_corner_order_convention(detector: Detector) -> None:
    """pupil-apriltags のコーナー順序が TAG_CORNER_LOCAL の想定と一致する。

    geometry.py のコーナー規約(左下→右下→右上→左上、タグ座標 x=右, y=上)の
    実測ピン留め。pupil-apriltags のバージョン更新時はこのテストで検知する。
    """
    cam = make_camera()
    img, placed = render_scene(Scene(), cam)
    dets = {d.tag_id: d for d in detector.detect(img)}
    assert sorted(dets) == [200, 201, 202, 203]
    for tag_id, placed_tag in placed.items():
        det_corners = dets[tag_id].corners
        # 順序どおりに比較(対応の入れ替わりがあれば大きくずれる)
        err = np.linalg.norm(det_corners - placed_tag.corners_px, axis=1)
        assert err.max() < 2.0, f"tag {tag_id} corner order mismatch: {err}"


def test_calibrate_recovers_camera(detector: Detector) -> None:
    cam = make_camera()
    img, _ = render_scene(Scene(), cam)
    mat = {d.tag_id: d.corners.astype(np.float64) for d in detector.detect(img) if d.tag_id >= 200}
    model = geometry.calibrate(mat, cam.image_size)
    assert model.focal == pytest.approx(cam.k[0, 0], rel=0.02)
    assert np.linalg.norm(model.cam_pos_mat - cam.position) < 15.0


def test_calibrate_requires_four_tags() -> None:
    cam = make_camera()
    img, _ = render_scene(Scene(hidden_tag_ids={203}), cam)
    det = Detector(families="tag36h11", nthreads=2)
    mat = {d.tag_id: d.corners.astype(np.float64) for d in det.detect(img) if d.tag_id >= 200}
    assert sorted(mat) == [200, 201, 202]
    with pytest.raises(ValueError):
        geometry.calibrate(mat, cam.image_size)


def test_box_bottom_center_accuracy(detector: Detector) -> None:
    """積んだ箱・回転した箱を含め、箱底面中心の推定誤差が10mm以内。"""
    cam = make_camera()
    stacks: dict[str, list[BoxId]] = {
        "A": ["large-1", "medium-1", "small-1"],
        "B": [],
        "C": ["large-2"],
    }
    scene = scene_from_layout(stacks, [])
    scene.boxes.append(BoxPose(box_id="medium-2", pos=(180.0, 80.0, 0.0)))
    scene.boxes.append(BoxPose(box_id="small-2", pos=(420.0, 80.0, 0.0), yaw_deg=25.0))
    img, _ = render_scene(scene, cam)
    accepted = [d for d in detector.detect(img) if d.hamming <= 1 and d.decision_margin >= 15]
    mat = {d.tag_id: d.corners.astype(np.float64) for d in accepted if d.tag_id >= 200}
    model = geometry.calibrate(mat, cam.image_size)

    truth = {b.box_id: np.array(b.pos, dtype=np.float64) for b in scene.boxes}
    estimates: dict[BoxId, list[np.ndarray]] = {}
    for d in accepted:
        if d.tag_id >= 200:
            continue
        box_id = BOX_IDS[d.tag_id // 6]
        size = BOX_SIZE_OF[box_id]
        black = 20.8 if size == "small" else 16.0
        p, _yaw = geometry.box_estimate(
            d.corners.astype(np.float64), black, size, BOX_EDGE_MM[size], model
        )
        estimates.setdefault(box_id, []).append(p)

    assert set(estimates) == set(truth)  # 全箱がいずれかのタグで見えている
    for box_id, ps in estimates.items():
        err = np.abs(np.mean(ps, axis=0) - truth[box_id])
        assert err.max() < 10.0, f"{box_id}: err={err}"
