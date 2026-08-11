"""cv2.aruco.ArucoDetector によるH/A/N/O/I検出と描画。"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from src.dictionary import LABELS, create_hanoi_dictionary


@dataclass(frozen=True)
class Detection:
    marker_id: int
    label: str  # "H" | "A" | "N" | "O" | "I"
    corners: np.ndarray  # (4, 2) float32


def create_detector(
    dictionary: cv2.aruco.Dictionary | None = None,
    parameters: cv2.aruco.DetectorParameters | None = None,
) -> cv2.aruco.ArucoDetector:
    return cv2.aruco.ArucoDetector(
        dictionary or create_hanoi_dictionary(),
        parameters or cv2.aruco.DetectorParameters(),
    )


def detect_letters(
    image: np.ndarray, detector: cv2.aruco.ArucoDetector | None = None
) -> list[Detection]:
    """画像からH/A/N/O/Iマーカーを検出する。imageはBGRまたはグレースケール。"""
    detector = detector or create_detector()
    corners, ids, _rejected = detector.detectMarkers(image)
    if ids is None:
        return []
    return [
        Detection(marker_id=int(i), label=LABELS[int(i)], corners=c.reshape(4, 2))
        for c, i in zip(corners, ids.flatten())
    ]


def annotate(image: np.ndarray, detections: list[Detection]) -> np.ndarray:
    """検出枠と文字ラベルを描き込んだコピーを返す。"""
    out = image.copy()
    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)
    for det in detections:
        pts = det.corners.astype(np.int32)
        cv2.polylines(out, [pts], isClosed=True, color=(0, 255, 0), thickness=2)
        cv2.circle(out, tuple(pts[0]), 5, (0, 0, 255), -1)  # 第1コーナー=向き
        top = pts[pts[:, 1].argmin()]
        cv2.putText(
            out,
            det.label,
            (int(top[0]), int(top[1]) - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
    return out
