"""マーカーPNG生成(黒枠 + 7×7データ領域 + 白quiet zone)。"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from src.marker_patterns import GRID, LETTERS, get_patterns


def generate_marker_image(
    marker: np.ndarray,
    cell_size: int = 100,
    border_bits: int = 1,
    quiet_zone_bits: int = 1,
) -> np.ndarray:
    """7×7パターンからグレースケール画像(uint8)を作る。

    外側から quiet zone(白) → border(黒) → データ領域 の順。
    1セル = cell_size px。
    """
    assert marker.shape == (GRID, GRID)
    assert set(np.unique(marker)) <= {0, 1}, "パターンは0/1のみ(1=白, 0=黒)"
    b, q = border_bits, quiet_zone_bits
    n = GRID + 2 * b + 2 * q
    cells = np.ones((n, n), dtype=np.uint8)  # 1=白
    cells[q : n - q, q : n - q] = 0  # border黒
    cells[q + b : q + b + GRID, q + b : q + b + GRID] = marker
    return np.kron(cells * 255, np.ones((cell_size, cell_size), dtype=np.uint8))


def generate_all(
    out_dir: Path,
    cell_size: int = 100,
    border_bits: int = 1,
    quiet_zone_bits: int = 1,
) -> list[Path]:
    """H.png〜I.png を out_dir に書き出す。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    patterns = get_patterns()
    paths = []
    for letter in LETTERS:
        img = generate_marker_image(
            patterns[letter], cell_size, border_bits, quiet_zone_bits
        )
        path = out_dir / f"{letter}.png"
        if not cv2.imwrite(str(path), img):
            raise OSError(f"PNG書き込みに失敗: {path}")
        paths.append(path)
    return paths
