#!/usr/bin/env python3
"""画像からH/A/N/O/Iマーカーを検出し、ラベル表示と枠描画を行う。

使い方(リポジトリルートから):
    cd server && uv run python ../hanoi_markers/scripts/detect.py <image>

検出結果を標準出力に表示し、<image名>_detected.png に描画結果を保存する。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import cv2

from src.detector import annotate, detect_letters


def main() -> None:
    if len(sys.argv) != 2:
        print("usage: detect.py <image>", file=sys.stderr)
        sys.exit(2)
    path = Path(sys.argv[1])
    image = cv2.imread(str(path))
    if image is None:
        print(f"画像を読めない: {path}", file=sys.stderr)
        sys.exit(1)

    detections = detect_letters(image)
    if not detections:
        print("マーカーは検出されなかった")
    for det in detections:
        print(f"Detected: {det.label}")

    out = path.with_name(f"{path.stem}_detected.png")
    if not cv2.imwrite(str(out), annotate(image, detections)):
        print(f"描画結果の書き込みに失敗: {out}", file=sys.stderr)
        sys.exit(1)
    print(f"描画結果: {out}")


if __name__ == "__main__":
    main()
