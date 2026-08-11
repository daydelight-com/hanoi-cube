#!/usr/bin/env python3
"""パターン探索を実行し、結果を src/optimized_patterns.json へ保存する。

使い方(リポジトリルートから):
    cd server && uv run python ../hanoi_markers/scripts/optimize_markers.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np

from src.marker_patterns import BASE_PATTERNS, LETTERS, save_patterns, to_ascii
from src.optimizer import (
    evaluate,
    hamming_distance,
    optimize,
    pairwise_report,
    suggest_max_correction_bits,
)

SEED = 42


def main() -> None:
    print(f"探索開始 (simulated annealing, seed={SEED}) ...")
    patterns, ev = optimize(seed=SEED)

    print("\n=== 全190ペアのHamming距離 ===")
    for a, b, d in pairwise_report(patterns):
        print(f"{a} vs {b}: {d}")

    print(f"\nMinimum Hamming Distance: {ev.min_distance}")
    print("Minimum pair(s):")
    for a, b in ev.min_pairs:
        print(f"  {a} vs {b}  Distance: {ev.min_distance}")

    mcb = suggest_max_correction_bits(ev.min_distance)
    print(f"\n理論訂正上界 floor((d-1)/2) = {(ev.min_distance - 1) // 2}")
    print(f"推奨 maxCorrectionBits(安全側) = {mcb}")

    print("\n=== original / optimized / difference ===")
    for c in LETTERS:
        diff = np.where(patterns[c] != BASE_PATTERNS[c], patterns[c], 9)
        diff_ascii = "\n".join(
            "".join({1: "＋", 0: "－", 9: "・"}[int(v)] for v in row)
            for row in diff
        )
        changed = hamming_distance(patterns[c], BASE_PATTERNS[c])
        print(f"\n--- {c} (変更 {changed} bit) ---")
        for title, art in [
            ("original", to_ascii(BASE_PATTERNS[c])),
            ("optimized", to_ascii(patterns[c])),
            ("difference (＋=白追加 －=白削除 ・=変更なし)", diff_ascii),
        ]:
            print(f"[{title}]")
            print(art)

    path = save_patterns(
        patterns,
        stats={
            "seed": SEED,
            "min_distance": ev.min_distance,
            "min_pairs": [list(p) for p in ev.min_pairs],
            "total_changed_bits": ev.total_changes,
            "suggested_max_correction_bits": mcb,
        },
    )
    print(f"\n保存: {path}")
    # 保存→再読込→同一評価になることの自己検証
    from src.marker_patterns import get_patterns

    assert evaluate(get_patterns()).min_distance == ev.min_distance
    print("再読込検証 OK")


if __name__ == "__main__":
    main()
