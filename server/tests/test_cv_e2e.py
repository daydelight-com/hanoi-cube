"""実CVのE2E: 合成動画 → 別プロセスCVワーカー(RealCv)→ 状態機械の通しプレイ。

S8のDoD「実箱でS5の通しプレイが成立」の無人実行代替。実箱・実カメラの代わりに、
通しプレイを演じる合成動画(MJPG圧縮でカメラ画質劣化も模す)を CvWorkerConfig の
動画入力に渡し、cv-interface 契約どおりの確定盤面イベント列が出ること、
それを状態機械に流してゲーム(モード選択→本番→判定→スコア)が成立することを検証する。

シナリオに含めるロバスト性要件(仕様§4.2):
  - 移動中の全タグロスト(露出1/60s相当)でも盤面が飛ばない(ロスト保持)
  - 「小の上に大」の違反検出と、オーバーハング遮蔽下での違反保持
  - 積んだ箱の一時遮蔽(1秒)で盤面が変わらない
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import pytest
from app.core.precompute import load_table
from app.cv.interface import BOX_IDS, BoxId, CvBoardUpdate, CvFrame
from app.cv.real import RealCv
from app.cv.worker import CvWorkerConfig

from tests.cv_scene import (
    BoxPose,
    Scene,
    make_camera,
    render_scene,
    scene_from_layout,
    synthetic_tag_master_json,
)
from tests.test_state_machine import SCORED_POINTS, Driver, sent

FPS = 30.0


def _layout(
    stacks: dict[str, list[BoxId]],
    *,
    absent: frozenset[BoxId] = frozenset(),
    midair: dict[BoxId, tuple[float, float, float]] | None = None,
    hidden_tag_ids: set[int] | None = None,
) -> Scene:
    """塔配置+残りは待機。absent は画面から消えた箱(持ち運び中の全ロスト)。"""
    placed = {b for stack in stacks.values() for b in stack}
    midair = midair or {}
    staging = [b for b in BOX_IDS if b not in placed and b not in absent and b not in midair]
    scene = scene_from_layout(stacks, staging)
    for box_id, pos in midair.items():
        scene.boxes.append(BoxPose(box_id=box_id, pos=pos))
    if hidden_tag_ids:
        scene.hidden_tag_ids |= hidden_tag_ids
    return scene


def _write_playthrough_video(path: Path) -> None:
    cam = make_camera()
    small1_tags = {BOX_IDS.index("small-1") * 6 + f for f in range(6)}
    phases: list[tuple[Scene, int]] = [
        # P0: 空マット(起動時キャリブレーション)→ 初回確定盤面 "//"
        (Scene(), 30),
        # P1: 全箱を待機エリアへ → "//"(待機9箱)
        (_layout({}), 20),
        # P2: large-1 を持ち上げ中(可視・エリア外)。0.3秒未満なので確定しない
        (_layout({}, midair={"large-1": (150.0, 180.0, 40.0)}), 8),
        # P3: large-1 を塔Aへ → "L//"
        (_layout({"A": ["large-1"]}), 20),
        # P4: medium-1 運搬中の全タグロスト(モーションブラー相当)→ 盤面は変わらない
        (_layout({"A": ["large-1"]}, absent=frozenset({"medium-1"})), 12),
        # P5: medium-1 を塔Bへ → "L/M/"
        (_layout({"A": ["large-1"], "B": ["medium-1"]}), 20),
        # P6: small-1 運搬中の全ロスト
        (_layout({"A": ["large-1"], "B": ["medium-1"]}, absent=frozenset({"small-1"})), 10),
        # P7: small-1 を塔Bの上へ → "L/MS/"
        (_layout({"A": ["large-1"], "B": ["medium-1", "small-1"]}), 20),
        # P8: small-2 を塔Cへ → "L/MS/S"
        (_layout({"A": ["large-1"], "B": ["medium-1", "small-1"], "C": ["small-2"]}), 20),
        # P9: 違反: large-2 を small-2 の上へ。小箱はオーバーハングで実際に隠れる
        (
            _layout(
                {
                    "A": ["large-1"],
                    "B": ["medium-1", "small-1"],
                    "C": ["small-2", "large-2"],
                }
            ),
            20,
        ),
        # P10: 違反を解消(両方待機へ戻す)→ "L/MS/"
        (_layout({"A": ["large-1"], "B": ["medium-1", "small-1"]}), 20),
        # P11: large-2 を塔Cへ → "L/MS/L"(判定対象の最終盤面)
        (_layout({"A": ["large-1"], "B": ["medium-1", "small-1"], "C": ["large-2"]}), 20),
        # P12: 塔B頂上の small-1 が1秒間の一時遮蔽 → 盤面は変わらない
        (
            _layout(
                {"A": ["large-1"], "B": ["medium-1", "small-1"], "C": ["large-2"]},
                hidden_tag_ids=small1_tags,
            ),
            30,
        ),
        # P13: 遮蔽解除
        (_layout({"A": ["large-1"], "B": ["medium-1", "small-1"], "C": ["large-2"]}), 10),
    ]
    fourcc = cv2.VideoWriter.fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(path), fourcc, FPS, cam.image_size)
    assert writer.isOpened()
    try:
        for scene, nframes in phases:
            gray, _ = render_scene(scene, cam)
            bgr = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
            for _ in range(nframes):
                writer.write(bgr)
    finally:
        writer.release()


EXPECTED_BOARDS = [
    ("//", True),  # P0 空マット
    ("//", True),  # P1 全箱待機
    ("L//", True),  # P3
    ("L/M/", True),  # P5
    ("L/MS/", True),  # P7
    ("L/MS/S", True),  # P8
    ("L/MS/SL", False),  # P9 違反
    ("L/MS/", True),  # P10 解消
    ("L/MS/L", True),  # P11 最終盤面
]


@pytest.fixture(scope="module")
def cv_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[list[CvBoardUpdate], list[CvFrame]]:
    """動画を生成し、RealCv(別プロセスワーカー)で最後まで処理した結果を返す。"""
    tmp = tmp_path_factory.mktemp("cv_e2e")
    video = tmp / "playthrough.avi"
    _write_playthrough_video(video)
    master_path = tmp / "tag_master.json"
    master_path.write_text(json.dumps(synthetic_tag_master_json()))

    calibration_path = tmp / "cv_calibration.json"
    cv = RealCv(
        CvWorkerConfig(
            video_path=str(video),
            tag_master_path=str(master_path),
            calibration_path=str(calibration_path),
        )
    )
    updates: list[CvBoardUpdate] = []
    frames: list[CvFrame] = []
    deadline = time.time() + 120
    try:
        while time.time() < deadline:
            batch = cv.poll()
            for message in batch:
                if isinstance(message, CvBoardUpdate):
                    updates.append(message)
                else:
                    frames.append(message)
            if not batch and not cv.alive:
                break
            time.sleep(0.02)
    finally:
        cv.close()
    assert time.time() < deadline, "CVワーカーが時間内に動画を処理し終えなかった"
    assert calibration_path.exists(), "キャリブレーションが保存されていない"
    return updates, frames


def test_board_update_sequence(cv_run: tuple[list[CvBoardUpdate], list[CvFrame]]) -> None:
    """確定盤面イベント列が演じたシナリオと一致する(違反検出・ロスト保持を含む)。"""
    updates, _ = cv_run
    assert [(u.board, u.legal) for u in updates] == EXPECTED_BOARDS
    # 全箱待機の確定盤面は9箱すべてを待機として持つ
    assert updates[1].staging_box_ids == list(BOX_IDS)
    # 違反の内訳
    violation = updates[6]
    assert [(v.tower, v.type) for v in violation.violations] == [("C", "size_order")]
    # t_ms は単調非減少
    t = [u.t_ms for u in updates]
    assert t == sorted(t)


def test_frames_cover_all_boxes_and_mat(cv_run: tuple[list[CvBoardUpdate], list[CvFrame]]) -> None:
    _updates, frames = cv_run
    assert frames, "CvFrame が届いていない"
    assert all(len(f.boxes) == 9 for f in frames)
    # 空マットのフレームではマット四隅が4つ検出されている(起動時セルフチェック)
    assert any(f.mat_corners_detected == 4 for f in frames)
    # 一時遮蔽中も small-1 は盤面(塔B)に保持されている(visible=false)
    held = [
        b
        for f in frames
        for b in f.boxes
        if b.box_id == "small-1" and not b.visible and b.area == "B"
    ]
    assert held, "遮蔽中の保持フレームが見つからない"


def test_playthrough_with_state_machine(cv_run: tuple[list[CvBoardUpdate], list[CvFrame]]) -> None:
    """S5相当の通しプレイ: CVの確定盤面列を状態機械へ流し、判定・スコアが成立する。"""
    updates, _ = cv_run
    d = Driver(load_table())
    d.to_game_play()

    for update in updates[:-3]:  # 違反盤面の手前まで
        d.advance(500)
        d.machine.on_cv_message(update, d.now)

    # 違反盤面("L/MS/SL")では判定ボタンが無効(仕様§4.2)
    violation = updates[-3]
    d.advance(500)
    d.machine.on_cv_message(violation, d.now)
    assert not sent(d.press("enter"), "judge")

    # 解消 → 最終盤面 "L/MS/L" で判定 → SCORED_POINTS(S1で検証済みのスコア)
    for update in updates[-2:]:
        d.advance(500)
        d.machine.on_cv_message(update, d.now)
    out = d.press("enter")
    judge = sent(out, "judge")[0]
    assert judge.payload["result"] == "scored"
    assert judge.payload["points"] == SCORED_POINTS
