"""実CVソース: 別プロセスのCVワーカーから検出結果を受ける CvSource 実装。

サーバー(api/main.py)は環境変数 HANOI_CV=real でモックの代わりにこれを使う。
ワーカーが死んだ場合(カメラ切断等)はバックオフ付きで自動再起動する。
モックCV(mock.py)は本番の縮退経路として残る(CLAUDE.md 規則6)。
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import os
import queue
import time
from multiprocessing.queues import Queue as MpQueue

from app.cv.interface import CvBoardUpdate, CvMessage
from app.cv.tag_master import DEFAULT_TAG_MASTER_PATH
from app.cv.worker import QUEUE_MAX, CvWorkerConfig, worker_main

logger = logging.getLogger(__name__)

_RESTART_BACKOFF_S = 3.0

DEFAULT_CALIBRATION_PATH = DEFAULT_TAG_MASTER_PATH.parent / "cv_calibration.json"


def config_from_env() -> CvWorkerConfig:
    """環境変数からワーカー設定を組み立てる。

    HANOI_CV_CAMERA / _VIDEO / _WIDTH / _HEIGHT / HANOI_TAG_MASTER /
    HANOI_CV_CALIBRATION(空文字で永続化無効。既定 output/cv_calibration.json)
    """
    return CvWorkerConfig(
        camera_index=int(os.environ.get("HANOI_CV_CAMERA", "0")),
        video_path=os.environ.get("HANOI_CV_VIDEO") or None,
        width=int(os.environ.get("HANOI_CV_WIDTH", "1920")),
        height=int(os.environ.get("HANOI_CV_HEIGHT", "1080")),
        tag_master_path=os.environ.get("HANOI_TAG_MASTER") or None,
        calibration_path=os.environ.get("HANOI_CV_CALIBRATION", str(DEFAULT_CALIBRATION_PATH))
        or None,
    )


class RealCv:
    """cv-interface.md 準拠の CvSource(実CV)。poll() でワーカーの結果を配る。"""

    def __init__(self, config: CvWorkerConfig | None = None) -> None:
        self._config = config or config_from_env()
        self._ctx = mp.get_context("spawn")
        self._queue: MpQueue[CvMessage] = self._ctx.Queue(maxsize=QUEUE_MAX)
        self._process: mp.process.BaseProcess | None = None
        self._started_at = 0.0
        self._last_board: CvBoardUpdate | None = None
        self._start()

    # ---- CvSource ----

    def poll(self) -> list[CvMessage]:
        drained: list[CvMessage] = []
        while True:
            try:
                drained.append(self._queue.get_nowait())
            except queue.Empty:
                break
        # 停滞明けに古いフレームの塊を一斉配信しないよう、フレームは最新の1件に
        # 間引く(盤面イベントは全件・順序維持)。ワーカーは盤面イベントを常に
        # 同時刻以前のフレームより先に送るため、末尾フレームで t_ms 非減少が保たれる
        messages: list[CvMessage] = []
        latest_frame: CvMessage | None = None
        for message in drained:
            if isinstance(message, CvBoardUpdate):
                self._last_board = message
                messages.append(message)
            else:
                latest_frame = message
        if latest_frame is not None:
            messages.append(latest_frame)
        self._ensure_alive()
        return messages

    @property
    def last_board(self) -> CvBoardUpdate | None:
        """最新の確定盤面(スナップショット用。MockCv と同形)。"""
        return self._last_board

    # ---- ライフサイクル ----

    @property
    def alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def close(self) -> None:
        if self._process is not None and self._process.is_alive():
            self._process.terminate()
            self._process.join(timeout=3.0)
        self._process = None

    # ---- 内部 ----

    def _start(self) -> None:
        self._process = self._ctx.Process(
            target=worker_main, args=(self._config, self._queue), daemon=True
        )
        self._process.start()
        self._started_at = time.monotonic()
        logger.info("CVワーカー起動 pid=%s", self._process.pid)

    def _ensure_alive(self) -> None:
        if self.alive:
            return
        if self._config.video_path is not None:
            return  # 動画入力は読み終わったら終了してよい(検証用途)
        if time.monotonic() - self._started_at < _RESTART_BACKOFF_S:
            return
        logger.warning("CVワーカーが停止している。再起動する(カメラ切断?)")
        self._start()
