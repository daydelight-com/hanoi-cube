"""scene.smoothing のテスト: smoothing.ts との一致、収束、吸着。"""

from __future__ import annotations

import math
import re
from pathlib import Path

import pytest

from scene.smoothing import POS_LAMBDA, SmoothedPosition, damp_factor, damp_vec

SMOOTHING_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "three" / "smoothing.ts"


def test_lambda_matches_smoothing_ts() -> None:
    src = SMOOTHING_TS.read_text(encoding="utf-8")
    m = re.search(r"export const POS_LAMBDA = (\d+)", src)
    assert m is not None
    assert float(m.group(1)) == POS_LAMBDA
    assert "1 - Math.exp(-lambda * dtSec)" in src


def test_damp_factor_formula() -> None:
    assert damp_factor(12.0, 0.0) == 0.0
    assert damp_factor(12.0, 1 / 60) == pytest.approx(1 - math.exp(-0.2))
    # 約 0.2 秒で 9 割(smoothing.ts のコメント)
    assert damp_factor(POS_LAMBDA, 0.2) == pytest.approx(0.909, abs=0.001)


def test_damp_vec_moves_toward_target_and_snaps() -> None:
    cur = damp_vec((0.0, 0.0, 0.0), (1.0, 2.0, 3.0), 12.0, 1 / 60)
    k = damp_factor(12.0, 1 / 60)
    assert cur == pytest.approx((k, 2 * k, 3 * k))
    # 残差が微小なら目標値に吸着(== で比較できる)
    assert damp_vec((0.99999, 0.0, 0.0), (1.0, 0.0, 0.0), 12.0, 1 / 60) == (1.0, 0.0, 0.0)


def test_smoothed_position_converges_in_about_half_second() -> None:
    pos = SmoothedPosition((0.0, 0.0, 0.0))
    pos.target = (1.0, 0.0, 0.0)
    assert not pos.settled
    for _ in range(12):  # 0.2 秒
        pos.step(1 / 60)
    assert pos.current[0] == pytest.approx(0.909, abs=0.01)
    for _ in range(60):  # +1 秒で吸着
        pos.step(1 / 60)
    assert pos.settled and pos.current == (1.0, 0.0, 0.0)


def test_snap_sets_both() -> None:
    pos = SmoothedPosition((0.0, 0.0, 0.0))
    pos.target = (5.0, 5.0, 5.0)
    pos.snap((1.0, 2.0, 3.0))
    assert pos.current == pos.target == (1.0, 2.0, 3.0)
    assert pos.step(1.0) == (1.0, 2.0, 3.0)
