"""TagDetector の受理条件(docs/cv_poc.md §4 で決定した閾値)の境界テスト。

検出器本体(pupil-apriltags)には検出結果を注入できないため、内部検出器を
スタブに差し替えて受理フィルタだけを検証する。検出そのものの精度は
test_cv_geometry.py / test_cv_pipeline.py が実画像で担保する。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from app.cv.detector import DECISION_MARGIN_MIN, HAMMING_MAX, TagDetector

from tests.cv_scene import synthetic_tag_master

_CORNERS = np.zeros((4, 2), dtype=np.float64)


@dataclass
class _FakeRaw:
    tag_id: int
    hamming: int
    decision_margin: float
    corners: np.ndarray


class _StubInner:
    def __init__(self, raws: list[_FakeRaw]) -> None:
        self._raws = raws

    def detect(self, gray: np.ndarray) -> list[_FakeRaw]:
        return self._raws


def _accepted_ids(raws: list[_FakeRaw]) -> list[int]:
    detector = TagDetector(synthetic_tag_master())
    detector._detector = _StubInner(raws)
    gray = np.zeros((8, 8), dtype=np.uint8)
    return [d.tag_id for d in detector.detect(gray)]


def raw(tag_id: int, *, hamming: int = 0, margin: float = DECISION_MARGIN_MIN) -> _FakeRaw:
    return _FakeRaw(tag_id=tag_id, hamming=hamming, decision_margin=margin, corners=_CORNERS)


def test_accepts_at_boundaries() -> None:
    # hamming == 上限、margin == 下限ちょうどは受理する
    assert _accepted_ids([raw(0, hamming=HAMMING_MAX, margin=DECISION_MARGIN_MIN), raw(200)]) == [
        0,
        200,
    ]


def test_rejects_over_hamming() -> None:
    assert _accepted_ids([raw(0, hamming=HAMMING_MAX + 1)]) == []


def test_rejects_below_margin() -> None:
    assert _accepted_ids([raw(0, margin=DECISION_MARGIN_MIN - 0.1)]) == []


def test_rejects_unknown_ids() -> None:
    # 54(予約済み・未貼付)や 999 はマスタ外として棄却する
    assert _accepted_ids([raw(54), raw(999)]) == []
