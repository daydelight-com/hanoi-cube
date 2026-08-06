"""FramePipeline(検出→キャリブレーション→幾何→盤面構成)の統合テスト。

合成3Dシーンを実検出器(pupil-apriltags)へ通し、パイプライン全体の振る舞いを
検証する。静止シーンは検出結果が不変のためシーン単位で検出をキャッシュし、
同じ検出結果を時刻を進めながら流す(検出自体の精度は test_cv_geometry.py で担保)。
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from app.cv.detector import TagDetection, TagDetector
from app.cv.interface import BOX_IDS, CvBoardUpdate, CvFrame, CvMessage
from app.cv.layout import MAT_TAG_BLACK_MM, MAT_TAG_CENTERS_MM
from app.cv.pipeline import CALIBRATION_REFRESH_MS, FramePipeline, _mean_yaw
from app.cv.tracker import LOST_HOLD_MS, STABLE_MS

from tests.cv_scene import (
    BoxPose,
    Scene,
    SceneCamera,
    make_camera,
    render_scene,
    scene_from_layout,
    synthetic_tag_master,
)

DT = 33
STABLE_REPEAT = STABLE_MS // DT + 2


def all_staging_scene() -> Scene:
    return scene_from_layout({"A": [], "B": [], "C": []}, list(BOX_IDS))


class PipeDriver:
    """シーン→検出(キャッシュ)→パイプラインを時刻を進めながら流すヘルパー。"""

    def __init__(
        self, *, expected_camera_side: str | None = None, camera: SceneCamera | None = None
    ) -> None:
        master = synthetic_tag_master()
        self.detector = TagDetector(master)
        self.pipeline = FramePipeline(master, expected_camera_side=expected_camera_side)
        self.camera = camera or make_camera()
        self.now = 0
        self._cache: dict[str, list[TagDetection]] = {}

    def feed(self, key: str, scene: Scene, *, repeat: int = 1) -> list[CvMessage]:
        if key not in self._cache:
            img, _ = render_scene(scene, self.camera)
            self._cache[key] = self.detector.detect(img)
        detections = self._cache[key]
        messages: list[CvMessage] = []
        for _ in range(repeat):
            self.now += DT
            messages += self.pipeline.process(detections, self.now, self.camera.image_size)
        return messages


def boards(messages: list[CvMessage]) -> list[CvBoardUpdate]:
    return [m for m in messages if isinstance(m, CvBoardUpdate)]


def frames(messages: list[CvMessage]) -> list[CvFrame]:
    return [m for m in messages if isinstance(m, CvFrame)]


@pytest.fixture
def d() -> PipeDriver:
    return PipeDriver()


def test_staging_boxes_occlude_front_corner_but_calibration_accumulates(d: PipeDriver) -> None:
    """全箱待機ではマット手前隅タグが遮蔽される。四隅の観測を跨いで蓄積して
    キャリブレーションできること(起動時=全箱待機で詰まない)。"""
    staging = all_staging_scene()
    messages = d.feed("staging", staging, repeat=5)
    # 前提の確認: このシーンでは四隅が同時には見えない(左手前が大箱に遮蔽される)
    assert frames(messages)[-1].mat_corners_detected < 4
    assert not d.pipeline.calibrated
    assert not boards(messages)

    # 空マットのフレームが一度でも入れば(起動時セルフチェック相当)四隅がそろう
    d.feed("empty", Scene(), repeat=2)
    assert d.pipeline.calibrated

    # 以後は全箱待機でも(蓄積した左手前隅を使い)盤面が確定する
    updates = boards(d.feed("staging", staging, repeat=STABLE_REPEAT))
    assert len(updates) == 1
    assert updates[0].board == "//"
    assert updates[0].legal
    assert updates[0].staging_box_ids == list(BOX_IDS)


def test_move_confirms_and_occlusion_holds(d: PipeDriver) -> None:
    d.feed("empty", Scene(), repeat=2)
    staging = all_staging_scene()
    assert boards(d.feed("staging", staging, repeat=STABLE_REPEAT))

    # large-1 を塔Aへ(残りは待機のまま)
    moved = scene_from_layout(
        {"A": ["large-1"], "B": [], "C": []}, [b for b in BOX_IDS if b != "large-1"]
    )
    updates = boards(d.feed("moved", moved, repeat=STABLE_REPEAT))
    assert [u.board for u in updates] == ["L//"]

    # 塔Aの large-1 が完全遮蔽(2秒未満)されても盤面は変わらない
    occluded = Scene(
        boxes=moved.boxes,
        hidden_tag_ids={i for i in range(6)},  # large-1 の6面
    )
    messages = d.feed("occluded", occluded, repeat=LOST_HOLD_MS // DT - 5)
    assert not boards(messages)
    assert not [b for f in frames(messages) for b in f.boxes if b.box_id == "large-1" and b.visible]

    # 遮蔽が解ければそのまま(盤面イベントなし)
    assert not boards(d.feed("moved", moved, repeat=STABLE_REPEAT))


def test_violation_reported_and_survives_overhang_occlusion(d: PipeDriver) -> None:
    """「小の上に大」は下の小箱がオーバーハングでほぼ完全に隠れる。
    確定済みの箱の構造遮蔽保持(仕様§4.2)により、違反検出が2秒で崩れないこと。"""
    d.feed("empty", Scene(), repeat=2)
    # まず小箱を塔Cに置いて確定させる
    small_only = Scene(boxes=[BoxPose(box_id="small-2", pos=(450.0, 280.0, 0.0))])
    assert [u.board for u in boards(d.feed("small", small_only, repeat=STABLE_REPEAT))] == ["//S"]

    # その上に大箱を載せる(小箱のタグはレンダリング上も実際に見えなくなる)
    stacked = Scene(
        boxes=[
            BoxPose(box_id="small-2", pos=(450.0, 280.0, 0.0)),
            BoxPose(box_id="large-2", pos=(450.0, 280.0, 30.0)),
        ]
    )
    updates = boards(d.feed("stacked", stacked, repeat=STABLE_REPEAT))
    assert len(updates) == 1
    up = updates[0]
    assert not up.legal
    assert up.towers == ("", "", "SL")
    assert [(v.tower, v.type) for v in up.violations] == [("C", "size_order")]

    # ロスト保持(2秒)を超えても、大箱に覆われている限り違反状態を保持する
    long_frames = (LOST_HOLD_MS * 2) // DT
    assert not boards(d.feed("stacked", stacked, repeat=long_frames))
    assert d.pipeline.tracker.last_board is not None
    assert d.pipeline.tracker.last_board.towers == ("", "", "SL")

    # 大箱を取り除くと小箱が再び見え、大箱のロスト保持(2秒)が切れた後に
    # 盤面が「小のみ」へ戻る
    updates = boards(d.feed("small", small_only, repeat=LOST_HOLD_MS // DT + STABLE_REPEAT + 2))
    assert [u.board for u in updates] == ["//S"]


def test_frames_stream_positions_within_tolerance(d: PipeDriver) -> None:
    """CvFrame の位置がシーンの正解に十分近い(3D表示品質の下限確認)。"""
    d.feed("empty", Scene(), repeat=2)
    scene = Scene(
        boxes=[
            BoxPose(box_id="large-1", pos=(150.0, 280.0, 0.0)),
            BoxPose(box_id="medium-1", pos=(150.0, 280.0, 75.0)),
        ]
    )
    frame = frames(d.feed("two", scene, repeat=1))[0]
    truth = {b.box_id: np.array(b.pos) for b in scene.boxes}
    for box in frame.boxes:
        if box.box_id in truth:
            assert np.abs(np.array(box.pos_mm) - truth[box.box_id]).max() < 10.0
            assert box.visible


def test_calibration_rejects_mixed_stale_observations(d: PipeDriver) -> None:
    """カメラ微動+遮蔽で新旧コーナー観測が混ざった場合、再投影誤差で棄却して
    前回のキャリブレーションを維持し、全隅が新しく見えたら追従する。"""
    d.feed("empty", Scene(), repeat=2)
    cam_a = d.pipeline._camera
    assert cam_a is not None

    # カメラが30mmずれ、左手前隅(203)は遮蔽されて古い観測が残る
    cam_b = make_camera(position=(330.0, -500.0, 600.0))
    img_hidden, _ = render_scene(Scene(hidden_tag_ids={203}), cam_b)
    dets_hidden = d.detector.detect(img_hidden)
    d.now += CALIBRATION_REFRESH_MS + DT
    d.pipeline.process(dets_hidden, d.now, cam_b.image_size)
    assert d.pipeline._camera is cam_a  # 新旧混在は棄却され、前回の推定を維持

    # 全隅が新カメラで見えれば追従する
    img_full, _ = render_scene(Scene(), cam_b)
    dets_full = d.detector.detect(img_full)
    d.now += CALIBRATION_REFRESH_MS + DT
    d.pipeline.process(dets_full, d.now, cam_b.image_size)
    camera = d.pipeline._camera
    assert camera is not None and camera is not cam_a
    assert np.linalg.norm(camera.cam_pos_mat - np.array([330.0, -500.0, 600.0])) < 15.0


def test_mean_yaw_circular_and_degenerate() -> None:
    """ヨー円環平均: ±π境界で正しく平均し、打ち消し合う縮退では先頭値へフォールバック。"""
    deg = np.radians
    assert _mean_yaw([deg(10.0)]) == pytest.approx(deg(10.0))
    assert _mean_yaw([deg(170.0), deg(-170.0)]) == pytest.approx(deg(180.0), abs=1e-9)
    # 縮退(和がほぼゼロ): 丸め誤差由来の任意角ではなく先頭の観測値を返す
    assert _mean_yaw([deg(0.0), deg(180.0)]) == deg(0.0)
    assert _mean_yaw([deg(0.0), deg(120.0), deg(240.0)]) == deg(0.0)


def test_yaw_estimated_from_rotated_box(d: PipeDriver) -> None:
    """回転して置かれた箱のヨーが CvFrame の quat に反映される。"""
    d.feed("empty", Scene(), repeat=2)
    scene = Scene(
        boxes=[
            BoxPose(box_id="small-2", pos=(450.0, 280.0, 0.0), yaw_deg=25.0),
            BoxPose(box_id="large-1", pos=(150.0, 280.0, 0.0)),
        ]
    )
    frame = frames(d.feed("rotated", scene, repeat=2))[-1]

    def yaw_deg(box_id: str) -> float:
        box = next(b for b in frame.boxes if b.box_id == box_id)
        qz, qw = box.quat[2], box.quat[3]
        return float(np.degrees(2 * np.arctan2(qz, qw)))

    assert yaw_deg("small-2") == pytest.approx(25.0, abs=3.0)
    assert yaw_deg("large-1") == pytest.approx(0.0, abs=3.0)


def test_flipped_box_quat_shows_bottom_face_up(d: PipeDriver) -> None:
    """ひっくり返した箱(面6が上)の quat が実際の姿勢を表す(表示コンセプト: 実箱と同じ見え方)。"""
    d.feed("empty", Scene(), repeat=2)
    scene = Scene(boxes=[BoxPose(box_id="large-1", pos=(150.0, 280.0, 0.0), up_face=6)])
    frame = frames(d.feed("flipped", scene, repeat=2))[-1]
    box = next(b for b in frame.boxes if b.box_id == "large-1")
    # quat で箱ローカル -z(面6の法線)がマット +z を向く
    x, y, _z, _w = box.quat
    # 回転行列の第3成分(箱+z軸のマットz座標)。面6が上なら -1 に近い
    up_z = 1 - 2 * (x * x + y * y)
    assert up_z == pytest.approx(-1.0, abs=0.05)


def test_calibration_persistence_roundtrip(d: PipeDriver) -> None:
    """保存したキャリブレーションを復元すれば、四隅を一度も見せずに盤面が確定する
    (小さいマットでは箱に隠れて四隅がそろいにくいため。カメラ・マット固定の前提)。"""
    d.feed("empty", Scene(), repeat=2)
    data = json.loads(json.dumps(d.pipeline.export_calibration()))  # JSON経由を模す

    d2 = PipeDriver()
    d2.pipeline.restore_calibration(data)
    assert d2.pipeline.calibrated
    assert not d2.pipeline.has_fresh_calibration  # 復元は「新規成立」として保存されない
    updates = boards(d2.feed("staging", all_staging_scene(), repeat=STABLE_REPEAT))
    assert len(updates) == 1
    assert updates[0].staging_box_ids == list(BOX_IDS)


def test_camera_side_mismatch_warns(caplog: pytest.LogCaptureFixture) -> None:
    """合成カメラ(y=-500 = front側)と設定 back の食い違いで警告が出る(設営確認用)。"""
    d2 = PipeDriver(expected_camera_side="back")
    with caplog.at_level("WARNING", logger="app.cv.pipeline"):
        d2.feed("empty", Scene(), repeat=2)
    assert d2.pipeline.calibrated
    assert any("カメラ側の設定と実測が食い違う" in rec.message for rec in caplog.records)


def test_camera_side_match_and_unset_do_not_warn(caplog: pytest.LogCaptureFixture) -> None:
    # 手前(front)側カメラ: 設定 front と一致 / 未設定(None)はチェックなし
    for driver in (PipeDriver(expected_camera_side="front"), PipeDriver()):
        with caplog.at_level("WARNING", logger="app.cv.pipeline"):
            driver.feed("empty", Scene(), repeat=2)
        assert driver.pipeline.calibrated
    # 奥(back)側カメラ: 既定設定 back と一致(本番想定の設営)
    back_cam = make_camera(position=(300.0, 900.0, 600.0))
    back_driver = PipeDriver(expected_camera_side="back", camera=back_cam)
    with caplog.at_level("WARNING", logger="app.cv.pipeline"):
        back_driver.feed("empty", Scene(), repeat=2)
    assert back_driver.pipeline.calibrated
    assert not any("食い違う" in rec.message for rec in caplog.records)


def test_camera_side_mismatch_warns_on_restore(
    d: PipeDriver, caplog: pytest.LogCaptureFixture
) -> None:
    """保存済みキャリブレーション運用(四隅を見せない起動)でも食い違い警告が出る。"""
    d.feed("empty", Scene(), repeat=2)
    data = d.pipeline.export_calibration()
    assert data is not None
    d2 = PipeDriver(expected_camera_side="back")
    with caplog.at_level("WARNING", logger="app.cv.pipeline"):
        d2.pipeline.restore_calibration(data)
    assert any("カメラ側の設定と実測が食い違う" in rec.message for rec in caplog.records)


def test_calibration_restore_rejects_mismatched_layout(d: PipeDriver) -> None:
    d.feed("empty", Scene(), repeat=2)
    data = d.pipeline.export_calibration()
    assert data is not None
    data["mat_size_mm"] = [400.0, 300.0]  # layout.py 変更後の想定
    with pytest.raises(ValueError):
        PipeDriver().pipeline.restore_calibration(data)


def test_calibration_refresh_interval(d: PipeDriver) -> None:
    """キャリブレーションは一定間隔でだけ再推定される(毎フレームの重い計算を避ける)。"""
    d.feed("empty", Scene(), repeat=2)
    first = d.pipeline._camera
    d.feed("empty", Scene(), repeat=2)
    assert d.pipeline._camera is first
    d.feed("empty", Scene(), repeat=CALIBRATION_REFRESH_MS // DT + 2)
    assert d.pipeline._camera is not first


def test_measured_mat_centers_recovers_tag_positions(d: PipeDriver) -> None:
    """棄却診断用の逆投影が、検出したタグ中心のマット座標を正しく復元する。"""
    d.feed("empty", Scene(), repeat=2)
    camera = d.pipeline._camera
    assert camera is not None
    # 既知のずれ(+8, -6)mm を与えたタグ中心を投影し、逆投影で復元できること
    offset = np.array([8.0, -6.0])
    corners_px: dict[int, np.ndarray] = {}
    for tag_id, (cx, cy) in MAT_TAG_CENTERS_MM.items():
        center = np.array([cx, cy]) + offset
        half = MAT_TAG_BLACK_MM / 2.0
        pts = np.array(
            [
                [center[0] - half, center[1] - half, 0.0],
                [center[0] + half, center[1] - half, 0.0],
                [center[0] + half, center[1] + half, 0.0],
                [center[0] - half, center[1] + half, 0.0],
            ]
        )
        corners_px[tag_id] = camera.project(pts)
    measured = FramePipeline.measured_mat_centers(camera, corners_px)
    for tag_id, (cx, cy) in MAT_TAG_CENTERS_MM.items():
        mx, my = measured[tag_id]
        assert abs(mx - (cx + offset[0])) < 0.5
        assert abs(my - (cy + offset[1])) < 0.5


def _synthetic_mat_detections(
    camera: object, offsets: dict[int, tuple[float, float]]
) -> list[TagDetection]:
    """物理配置をずらした四隅タグのコーナー検出を、指定カメラの投影で合成する。"""
    from app.cv.geometry import TAG_CORNER_LOCAL, CameraModel

    assert isinstance(camera, CameraModel)
    half = MAT_TAG_BLACK_MM / 2.0
    dets = []
    for tag_id, (cx, cy) in MAT_TAG_CENTERS_MM.items():
        dx, dy = offsets.get(tag_id, (0.0, 0.0))
        corners_mat = np.hstack(
            [
                TAG_CORNER_LOCAL * half + np.array([cx + dx, cy + dy]),
                np.zeros((4, 1)),
            ]
        )
        dets.append(
            TagDetection(
                tag_id=tag_id,
                corners_px=camera.project(corners_mat),
                decision_margin=100.0,
            )
        )
    return dets


def test_calibration_accepts_fabrication_error_within_9mm(d: PipeDriver) -> None:
    """印刷歪み・貼付誤差相当(右側タグが約6mm外側)は許容して成立する(実測A3マット相当)。"""
    d.feed("empty", Scene(), repeat=2)
    camera = d.pipeline._camera
    assert camera is not None
    d2 = PipeDriver()
    # 注: ずらす組合せによっては焦点距離の自己推定が崩れて残差が数十mmに跳ね、
    # 自己検証で棄却される(例: 201を(6,-3)+202を(6,0))。ここでは推定が安定する
    # 実測相当のパターン(残差約7.5mm)を使う
    dets = _synthetic_mat_detections(camera, {201: (0.0, -3.0), 202: (6.0, 0.0)})
    d2.pipeline.process(dets, 0, make_camera().image_size)
    assert d2.pipeline.calibrated


def test_calibration_rejects_large_offset_with_diagnostic_log(
    d: PipeDriver, caplog: pytest.LogCaptureFixture
) -> None:
    """タグ1枚の大きな貼付ずれ(30mm)は棄却され、タグ別の想定→実測が診断ログに出る。"""
    d.feed("empty", Scene(), repeat=2)
    camera = d.pipeline._camera
    assert camera is not None
    d2 = PipeDriver()
    dets = _synthetic_mat_detections(camera, {201: (30.0, -30.0)})
    with caplog.at_level("WARNING", logger="app.cv.pipeline"):
        d2.pipeline.process(dets, 0, make_camera().image_size)
    assert not d2.pipeline.calibrated
    assert any("タグ別の想定→実測" in rec.message for rec in caplog.records)
