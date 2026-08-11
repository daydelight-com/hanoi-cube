"""cv2.aruco カスタムDictionary構築(ID 0=H, 1=A, 2=N, 3=O, 4=I)。

cv2.aruco.Dictionary.getByteListFromBits() でOpenCV内部形式へ変換する。
ビット規約はOpenCVと同じ 1=白 / 0=黒(実験で確認済み。README参照)。
"""

from __future__ import annotations

import cv2
import numpy as np

from src.marker_patterns import GRID, LABELS, LETTERS, get_patterns
from src.optimizer import evaluate, suggest_max_correction_bits

__all__ = ["LABELS", "create_hanoi_dictionary", "default_max_correction_bits"]

# 安全側の上限。理論値 floor((d-1)/2) がこれより大きくても採用しない
# (訂正を強くしすぎると背景の四角形をマーカーと誤認しやすくなる)
MAX_CORRECTION_BITS_CAP = 3


def default_max_correction_bits() -> int:
    """実際に読み込んだパターンの最小Hamming距離から安全側の値を返す。

    JSONのstats(記録値)ではなくパターン本体から毎回計算する。
    パターンだけ書き換えられてstatsが古いままでも過大な訂正値にならない。
    """
    d = evaluate(get_patterns()).min_distance
    return suggest_max_correction_bits(d, cap=MAX_CORRECTION_BITS_CAP)


def create_hanoi_dictionary(
    max_correction_bits: int | None = None,
) -> cv2.aruco.Dictionary:
    """最適化済み5パターンからカスタムDictionaryを作る。"""
    patterns = get_patterns()
    if max_correction_bits is None:
        max_correction_bits = default_max_correction_bits()
    byte_rows = [
        cv2.aruco.Dictionary.getByteListFromBits(patterns[c]) for c in LETTERS
    ]
    bytes_list = np.concatenate(byte_rows, axis=0)
    return cv2.aruco.Dictionary(bytes_list, GRID, max_correction_bits)
