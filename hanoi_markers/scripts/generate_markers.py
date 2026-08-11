#!/usr/bin/env python3
"""最適化済みパターンから markers/H.png 〜 I.png を生成する。

使い方(リポジトリルートから):
    cd server && uv run python ../hanoi_markers/scripts/generate_markers.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.generator import generate_all

OUT_DIR = Path(__file__).resolve().parents[1] / "markers"


def main() -> None:
    for path in generate_all(OUT_DIR, cell_size=100, border_bits=1, quiet_zone_bits=1):
        print(f"生成: {path}")


if __name__ == "__main__":
    main()
