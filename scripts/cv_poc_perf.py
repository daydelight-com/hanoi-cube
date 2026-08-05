#!/usr/bin/env python3
"""1080p全景シーンでの AprilTag 検出スループット計測(S7 CV PoC)

本番相当の 1920x1080 フレーム(マット四隅タグ4枚+9箱x2面=22タグ)を合成し、
pupil-apriltags の1フレーム処理時間を quad_decimate / nthreads 別に実測する。
30fps(33ms)の予算内でどこまで賄えるかを見るためのもの。
注意: 計測は det.detect() のみ。カメラ取得・色変換・座標変換・盤面構成・IPCは
含まないため、パイプライン全体の予算検討では検出以外のコストを別途見込むこと。

使い方:
    .venv/bin/python scripts/cv_poc_perf.py
"""

from __future__ import annotations

import sys
import time
from itertools import product
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cv_poc_synth import PX_PER_MM, load_tag, render
from pupil_apriltags import Detector

W, H = 1920, 1080
N_FRAMES = 30


def build_scene() -> tuple[np.ndarray, set[int]]:
    """マット4隅+9箱x2面(仕様§2.3「通常2〜3面が見える」の中間)相当の1080pシーン。

    箱タグは大・中=黒枠16mm、小=黒枠20.8mm。各箱とも側面(視線角30〜45°)と
    上面(視線角60°)の2枚が見えている想定。計 4+18=22 タグ。
    """
    rng = np.random.default_rng(42)
    scene = np.full((H, W), 130.0) + rng.normal(0, 2.5, (H, W))  # 背景+ノイズ
    scene = np.clip(scene, 0, 255).astype(np.uint8)

    # (tag_id, 黒枠mm, 視線角)。id は箱ごとに別面(box*6+face-1)
    specs: list[tuple[int, float, float]] = [
        (200, 36.8, 30.0),
        (201, 36.8, 30.0),
        (202, 36.8, 45.0),
        (203, 36.8, 45.0),
    ]
    for box in range(9):
        black_mm = 16.0 if box < 6 else 20.8  # 大3・中3 / 小3
        side_ang = 30.0 if box % 2 == 0 else 45.0
        specs.append((box * 6, black_mm, side_ang))  # 側面
        specs.append((box * 6 + 1, black_mm, 60.0))  # 上面

    expected: set[int] = set()
    x, y, row_h = 20, 20, 0
    for tid, black_mm, ang in specs:
        patch = render(
            load_tag(tid), black_mm * PX_PER_MM, ang, blur_px=0.0, gain=1.0,
            noise_sigma=3.0, rng=np.random.default_rng(tid),
        )
        ph, pw = patch.shape
        if x + pw > W - 20:  # 行送り
            x = 20
            y += row_h + 10
            row_h = 0
        if y + ph > H:
            raise SystemExit("シーンにタグが収まらない(配置ロジックを見直すこと)")
        scene[y : y + ph, x : x + pw] = patch
        x += pw + 10
        row_h = max(row_h, ph)
        expected.add(tid)
    return scene, expected


def main() -> None:
    scene, expected = build_scene()
    print(f"シーン: {W}x{H}, タグ{len(expected)}枚(マット4+箱9x2面)")
    print(f"{'decimate':>8} {'sigma':>5} {'threads':>7} | {'ms/frame':>8} {'fps':>6} | 検出")

    for dec, sigma, threads in product([1.0, 1.5, 2.0], [0.0], [1, 4, 8]):
        det = Detector(
            families="tag36h11", nthreads=threads, quad_decimate=dec,
            quad_sigma=sigma, refine_edges=True, decode_sharpening=0.25,
        )
        det.detect(scene)  # ウォームアップ
        t0 = time.perf_counter()
        for _ in range(N_FRAMES):
            dets = det.detect(scene)
        dt = (time.perf_counter() - t0) / N_FRAMES * 1000
        found = {d.tag_id for d in dets if d.hamming <= 1}
        miss = expected - found
        ok = f"{len(found & expected)}/{len(expected)}" + (f" 欠落{sorted(miss)}" if miss else "")
        print(f"{dec:8.1f} {sigma:5.1f} {threads:7d} | {dt:8.1f} {1000 / dt:6.0f} | {ok}")


if __name__ == "__main__":
    main()
