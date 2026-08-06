"""CVワーカー本体(別プロセスで実行。仕様§3.2-3)。

カメラ(または動画ファイル)からフレームを取得し、検出→幾何→盤面構成の
パイプラインを回して CvMessage をキューに流す。プロセス分離により30fpsの
画像処理が FastAPI のイベントループを塞がない。

キュー投入の方針: CvFrame は満杯なら捨てる(最新フレームがすぐ来る)。
CvBoardUpdate は確定盤面の変化イベントで喪失できないため、送れるまで手元に保持して
再送する。未送の盤面イベントがある間はフレームを流さない(t_ms の時系列順を保つ)。
"""

from __future__ import annotations

import contextlib
import json
import logging
import queue
import time
from collections import deque
from dataclasses import dataclass
from multiprocessing.queues import Queue as MpQueue
from pathlib import Path

from app.cv.interface import CvBoardUpdate, CvMessage
from app.cv.layout import MAT_TAG_IDS

logger = logging.getLogger(__name__)

QUEUE_MAX = 256
_STATUS_LOG_FRAMES = 150  # 約5秒ごとに検出状況をログする(現場での診断用)


@dataclass(frozen=True)
class CvWorkerConfig:
    """ワーカー設定(spawn でワーカープロセスへ渡すため picklable に保つ)。"""

    camera_index: int = 0
    video_path: str | None = None  # 指定時は動画ファイル入力(開発・検証用)
    width: int = 1920
    height: int = 1080
    video_fps: float = 30.0  # 動画入力の t_ms 換算(メタデータが無い場合の既定)
    tag_master_path: str | None = None  # None なら tag_master.tag_master_path()
    # キャリブレーションの保存先。前回の推定を再起動時に読み込むため、
    # 稼働中に四隅タグが箱で隠れ続けても(一度設営時に成立していれば)動ける。
    # None で無効(テスト等)
    calibration_path: str | None = None
    # HANOI_CAMERA_SIDE(back/front)。実測カメラ位置と食い違えば警告する(設営確認用)
    camera_side: str = "back"


def worker_main(config: CvWorkerConfig, out: MpQueue[CvMessage]) -> None:
    """ワーカープロセスのエントリポイント。"""
    # 子プロセス側でのみ使う重い import(親プロセスのメモリを汚さない)
    import cv2
    import numpy as np

    from app.cv.detector import TagDetector
    from app.cv.pipeline import FramePipeline
    from app.cv.tag_master import load_tag_master

    logging.basicConfig(level=logging.INFO, format="[cv-worker] %(levelname)s %(message)s")

    master = load_tag_master(Path(config.tag_master_path) if config.tag_master_path else None)
    detector = TagDetector(master)
    pipeline = FramePipeline(master, expected_camera_side=config.camera_side)

    calib_path = Path(config.calibration_path) if config.calibration_path else None
    if calib_path is not None and calib_path.exists():
        try:
            pipeline.restore_calibration(json.loads(calib_path.read_text()))
            logger.info("保存済みキャリブレーションを読み込んだ: %s", calib_path)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("キャリブレーションファイルを無視(%s): %s", exc, calib_path)

    if config.video_path is not None:
        cap = cv2.VideoCapture(config.video_path)
        fps = float(cap.get(cv2.CAP_PROP_FPS)) or config.video_fps
    else:
        cap = cv2.VideoCapture(config.camera_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.height)
        cap.set(cv2.CAP_PROP_FPS, 30)
        fps = 0.0
    if not cap.isOpened():
        logger.error("入力を開けない: %s", config.video_path or config.camera_index)
        return
    logger.info(
        "入力を開いた: %s (%.0fx%.0f)",
        config.video_path or f"camera={config.camera_index}",
        cap.get(cv2.CAP_PROP_FRAME_WIDTH),
        cap.get(cv2.CAP_PROP_FRAME_HEIGHT),
    )

    was_calibrated = pipeline.calibrated  # 復元済みなら「完了」ログは出さない
    calibration_saved = False
    frame_idx = 0
    pending_boards: deque[CvBoardUpdate] = deque()
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                logger.info("入力終了(%dフレーム処理)", frame_idx)
                break
            gray = np.asarray(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), dtype=np.uint8)
            if config.video_path is not None:
                t_ms = int(frame_idx * 1000.0 / fps)
            else:
                t_ms = int(time.monotonic() * 1000)
            detections = detector.detect(gray)
            image_size = (gray.shape[1], gray.shape[0])
            for message in pipeline.process(detections, t_ms, image_size):
                if isinstance(message, CvBoardUpdate):
                    pending_boards.append(message)
                elif not pending_boards:
                    # フレームは捨ててよい(次フレームで上書きされる)。ただし
                    # 未送の盤面イベントより先に流さない(時系列順の維持)
                    with contextlib.suppress(queue.Full):
                        out.put_nowait(message)
            _flush_boards(out, pending_boards)
            if pipeline.calibrated and not was_calibrated:
                was_calibrated = True
                logger.info("キャリブレーション完了(%dフレーム目)", frame_idx)
            if calib_path is not None and not calibration_saved and pipeline.has_fresh_calibration:
                data = pipeline.export_calibration()
                if data is not None:
                    calib_path.parent.mkdir(parents=True, exist_ok=True)
                    calib_path.write_text(json.dumps(data))
                    calibration_saved = True
                    logger.info("キャリブレーションを保存した: %s", calib_path)
            if frame_idx % _STATUS_LOG_FRAMES == 0:
                mat_count = sum(1 for d in detections if d.tag_id in MAT_TAG_IDS)
                logger.info(
                    "frame=%d 検出タグ=%d(マット%d/4) キャリブレーション=%s",
                    frame_idx,
                    len(detections),
                    mat_count,
                    "済"
                    if pipeline.calibrated
                    else "未(四隅を一度ずつ見せれば成立し、以後は保存される)",
                )
            frame_idx += 1
        # 動画終端: 残った盤面イベントを送り切ってから終了する(親停止時は10秒で諦める)
        flush_deadline = time.monotonic() + 10.0
        while pending_boards and time.monotonic() < flush_deadline:
            _flush_boards(out, pending_boards)
            if pending_boards:
                time.sleep(0.05)
    finally:
        cap.release()


def _flush_boards(out: MpQueue[CvMessage], pending: deque[CvBoardUpdate]) -> None:
    """未送の確定盤面イベントを順序を保って送る(満杯なら次フレームで再試行)。"""
    while pending:
        try:
            out.put_nowait(pending[0])
        except queue.Full:
            return
        pending.popleft()
