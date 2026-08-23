"""フレームレート非依存の指数平滑化(`frontend/src/three/smoothing.ts` の写し)。Pyxel に依存しない。

箱の描画位置を毎フレーム目標値へ収束させ、配置時に「スッと収まる」動きにする(仕様書 §6.3)。
λ=12 は約 0.2 秒で目標値の 9 割に到達する。
"""

from __future__ import annotations

import math
from typing import Final

Vec = tuple[float, float, float]

POS_LAMBDA: Final = 12.0  # 位置の収束速度(1/秒)。smoothing.ts の POS_LAMBDA と同値
SNAP_EPSILON: Final = 1e-4  # これ以下の残差は目標値に吸着させる(ワールド単位 = 0.01mm)


def damp_factor(lam: float, dt_sec: float) -> float:
    """経過時間 dt(秒)に対する平滑化係数(0..1)。smoothing.ts の dampFactor と同式。"""
    return 1.0 - math.exp(-lam * dt_sec)


def damp_vec(current: Vec, target: Vec, lam: float, dt_sec: float) -> Vec:
    """current を target へ係数分だけ近づける。十分近ければ target に吸着する。"""
    k = damp_factor(lam, dt_sec)
    out = (
        current[0] + (target[0] - current[0]) * k,
        current[1] + (target[1] - current[1]) * k,
        current[2] + (target[2] - current[2]) * k,
    )
    if all(abs(t - o) < SNAP_EPSILON for o, t in zip(out, target, strict=True)):
        return target
    return out


class SmoothedPosition:
    """目標位置へ指数平滑化で追従する位置。`snap()` で即座に合わせる。"""

    def __init__(self, position: Vec, lam: float = POS_LAMBDA) -> None:
        self.current: Vec = position
        self.target: Vec = position
        self.lam = lam

    def snap(self, position: Vec) -> None:
        self.current = self.target = position

    def step(self, dt_sec: float) -> Vec:
        self.current = damp_vec(self.current, self.target, self.lam, dt_sec)
        return self.current

    @property
    def settled(self) -> bool:
        return self.current == self.target
