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
from app.cv.pipeline import CALIBRATION_REFRESH_MS, FramePipeline
from app.cv.tracker import LOST_HOLD_MS, STABLE_MS

from tests.cv_scene import (
    BoxPose,
    Scene,
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

    def __init__(self) -> None:
        master = synthetic_tag_master()
        self.detector = TagDetector(master)
        self.pipeline = FramePipeline(master)
        self.camera = make_camera()
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


def test_yaw_estimated_from_rotated_box(d: PipeDriver) -> None:
    """回転して置かれた箱のヨー(mod 90°)が CvFrame の quat に反映される。"""
    d.feed("empty", Scene(), repeat=2)
    scene = Scene(
        boxes=[
            BoxPose(box_id="small-2", pos=(450.0, 280.0, 0.0), yaw_deg=25.0),
            BoxPose(box_id="large-1", pos=(150.0, 280.0, 0.0)),
        ]
    )
    frame = frames(d.feed("rotated", scene, repeat=2))[-1]

    def yaw_mod90_deg(box_id: str) -> float:
        box = next(b for b in frame.boxes if b.box_id == box_id)
        qz, qw = box.quat[2], box.quat[3]
        return float(np.degrees(2 * np.arctan2(qz, qw))) % 90.0

    assert yaw_mod90_deg("small-2") == pytest.approx(25.0, abs=3.0)
    upright = yaw_mod90_deg("large-1")
    assert upright < 3.0 or upright > 87.0


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
