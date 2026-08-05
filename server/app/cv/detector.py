"""AprilTag検出のラッパ(検出器設定と受理条件は docs/cv_poc.md §4 で決定)。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt
from pupil_apriltags import Detector

from app.cv.tag_master import TagMaster

# docs/cv_poc.md §4: S8の検出器初期値
DETECTOR_KWARGS: dict[str, object] = {
    "families": "tag36h11",
    "nthreads": 4,
    "quad_decimate": 2.0,
    "quad_sigma": 0.0,
    "refine_edges": True,
    "decode_sharpening": 0.25,
}
HAMMING_MAX = 1
DECISION_MARGIN_MIN = 15.0


@dataclass(frozen=True)
class TagDetection:
    """受理条件を満たした1タグの検出結果。"""

    tag_id: int
    corners_px: npt.NDArray[np.float64]  # (4,2) geometry.TAG_CORNER_LOCAL 順
    decision_margin: float


class TagDetector:
    """pupil-apriltags 検出+受理フィルタ(hamming・margin・IDマスタ照合)。"""

    def __init__(self, master: TagMaster, **overrides: object) -> None:
        self._known_ids = master.known_ids
        self._detector = Detector(**{**DETECTOR_KWARGS, **overrides})

    def detect(self, gray: npt.NDArray[np.uint8]) -> list[TagDetection]:
        detections = []
        for d in self._detector.detect(gray):
            if (
                d.hamming <= HAMMING_MAX
                and d.decision_margin >= DECISION_MARGIN_MIN
                and d.tag_id in self._known_ids
            ):
                detections.append(
                    TagDetection(
                        tag_id=d.tag_id,
                        corners_px=np.asarray(d.corners, dtype=np.float64),
                        decision_margin=float(d.decision_margin),
                    )
                )
        return detections
