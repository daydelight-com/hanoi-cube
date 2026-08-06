"""実CVの幾何変換(app/cv/geometry.py)のテスト。

合成3Dシーン(cv_scene.py)を実際に pupil-apriltags へ通し、
コーナー順序の規約・自己キャリブレーション・箱位置解決の精度をピン留めする。
"""

from __future__ import annotations

import math

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
        p, _up_face, _yaw = geometry.box_estimate(
            d.corners.astype(np.float64),
            black,
            size,
            BOX_EDGE_MM[size],
            model,
            face=d.tag_id % 6 + 1,
        )
        estimates.setdefault(box_id, []).append(p)

    assert set(estimates) == set(truth)  # 全箱がいずれかのタグで見えている
    for box_id, ps in estimates.items():
        err = np.abs(np.mean(ps, axis=0) - truth[box_id])
        assert err.max() < 10.0, f"{box_id}: err={err}"


@pytest.mark.parametrize(
    ("up_face", "yaw_deg"),
    [
        (1, 0.0),  # 正立
        (6, 0.0),  # ひっくり返し(底面が上)
        (2, 0.0),  # 横倒し(面2が上)
        (3, 30.0),  # 横倒し+回転
        (1, 155.0),  # 正立で大きく回転(mod 90° では表せない向き)
    ],
)
def test_box_orientation_recovered(detector: Detector, up_face: int, yaw_deg: float) -> None:
    """どの面が上でも、見えている各タグから (up_face, ヨー) が復元できる。"""
    cam = make_camera()
    scene = Scene(
        boxes=[BoxPose(box_id="large-1", pos=(300.0, 200.0, 0.0), yaw_deg=yaw_deg, up_face=up_face)]
    )
    img, _ = render_scene(scene, cam)
    box_dets = [d for d in detector.detect(img) if d.tag_id < 200 and d.hamming <= 1]
    assert len(box_dets) >= 2  # 上面+側面が見えている
    mat_img, _ = render_scene(Scene(), cam)
    mat = {
        d.tag_id: d.corners.astype(np.float64) for d in detector.detect(mat_img) if d.tag_id >= 200
    }
    model = geometry.calibrate(mat, cam.image_size)
    for d in box_dets:
        _p, est_face, est_yaw = geometry.box_estimate(
            d.corners.astype(np.float64), 16.0, "large", 75.0, model, face=d.tag_id % 6 + 1
        )
        assert est_face == up_face, f"tag {d.tag_id}: up_face {est_face} != {up_face}"
        yaw_err = (math.degrees(est_yaw) - yaw_deg + 180.0) % 360.0 - 180.0
        assert abs(yaw_err) < 5.0, f"tag {d.tag_id}: yaw err {yaw_err:.1f}°"


def test_tilted_box_not_buried() -> None:
    """手で回している最中の軽い傾きで、鏡映側のIPPE解へ飛んで箱が地面に沈まない。

    側面タグを厳密に投影して box_estimate に通す(検出器なしの純幾何)。
    傾きノイズで側面を上面と誤認すると底面 z が約 -edge/2 になり、
    3D表示で箱が半分埋まって見える(実箱検証で発覚した回帰)。
    """
    cam = make_camera()
    model = geometry.CameraModel(k=cam.k, r_cam_from_mat=cam.r, t_cam_from_mat=cam.t)
    edge, black, inset = 75.0, 16.0, 75.0 / 2 - 12.0
    for pos in [(300.0, 200.0), (150.0, 280.0), (450.0, 80.0)]:
        for tilt_deg in (-20.0, -16.0, -12.0, -6.0, 0.0, 6.0, 12.0, 16.0, 20.0):
            for yaw_deg in range(0, 360, 20):
                yaw, tilt = math.radians(yaw_deg), math.radians(tilt_deg)
                rz = np.array(
                    [
                        [math.cos(yaw), -math.sin(yaw), 0.0],
                        [math.sin(yaw), math.cos(yaw), 0.0],
                        [0.0, 0.0, 1.0],
                    ]
                )
                rx = np.array(
                    [
                        [1.0, 0.0, 0.0],
                        [0.0, math.cos(tilt), -math.sin(tilt)],
                        [0.0, math.sin(tilt), math.cos(tilt)],
                    ]
                )
                r_box = rx @ rz  # 正立+手ブレ相当の傾き
                center = np.array([pos[0], pos[1], edge / 2])
                t_in_box = geometry.TAG_IN_BOX[2]
                u, v = r_box @ t_in_box[:, 0], r_box @ t_in_box[:, 1]
                tag_center = center + r_box @ np.array([inset, -edge / 2, inset])
                # 入射角が浅い(ほぼ真横〜裏向き)ケースは実検出ではデコード不能なので除外
                normal = r_box @ t_in_box[:, 2]
                to_cam = cam.position - tag_center
                if float(normal @ to_cam) / float(np.linalg.norm(to_cam)) < 0.25:
                    continue
                corners_px = cam.project(
                    np.array(
                        [
                            tag_center + u * (lx * black / 2) + v * (ly * black / 2)
                            for lx, ly in geometry.TAG_CORNER_LOCAL
                        ]
                    )
                )
                p, est_face, est_yaw = geometry.box_estimate(
                    corners_px, black, "large", edge, model, face=2
                )
                label = f"pos={pos} tilt={tilt_deg} yaw={yaw_deg}"
                assert p[2] > -20.0, f"{label}: 底面z={p[2]:.0f}mm(埋まり)"
                if abs(tilt_deg) <= 12.0:  # 大傾き(持ち替え中相当)は埋まり検査のみ
                    assert est_face == 1, f"{label}: up_face={est_face}"
                    yaw_err = (math.degrees(est_yaw) - yaw_deg + 180.0) % 360.0 - 180.0
                    assert abs(yaw_err) < 10.0, f"{label}: yaw_err={yaw_err:.0f}°"
