#!/usr/bin/env python3
"""Three.js 版のアートワーク(frontend/public/textures/)を Pyxel 用にドット化する。

800x800 のグラデーション画像をそのまま Pyxel に読ませるとパレット量子化で縞が出るため、
縮小(箱 64x64 / マット 256x181)と各画像 16 色への減色(ディザなし)を先に済ませ、
使った全色を palette.json にまとめて出力する。実行時は pyxel_app/scene/textures.py が
palette.json の色を pyxel.colors の末尾へ追加してから PNG を読むので、Pyxel の
最近色量子化が完全一致になり無劣化で読み込める。

生成物(pyxel_app/assets/textures/)はコミットする。再生成が必要なのは
frontend/public/textures/ のアートワークを差し替えたときだけ:

    uv run --with pillow python scripts/make_pyxel_textures.py

ロゴ入り素材(cube_l_logo / cube_m_logo)を出力の cube_l / cube_m に使う。
pyxel.cube の box プリミティブは 6 面すべてに同一 UV(画像全面)を貼るため、
Three.js 版の「ロゴは面 1・6 のみ」は再現せず全面ロゴとする(小箱はロゴなし素材のみ)。
"""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "frontend" / "public" / "textures"
OUT_DIR = REPO_ROOT / "pyxel_app" / "assets" / "textures"
PALETTE_FILE = "palette.json"

# (元ファイル名, 出力ファイル名, 出力サイズ)。マットは実寸 420x297mm(仕様 §4.1)と同比
COLORS_PER_IMAGE = 16
TARGETS: list[tuple[str, str, tuple[int, int]]] = [
    ("cube_l_logo.png", "cube_l.png", (64, 64)),
    ("cube_m_logo.png", "cube_m.png", (64, 64)),
    ("cube_s.png", "cube_s.png", (64, 64)),
    ("play_mat.png", "play_mat.png", (256, 181)),
]


def pixelate(src: Path, size: tuple[int, int]) -> Image.Image:
    """縮小 + 減色(ディザなし)。戻り値はパレットモード(P)画像。"""
    image = Image.open(src).convert("RGB").resize(size, Image.LANCZOS)
    return image.quantize(colors=COLORS_PER_IMAGE, dither=Image.Dither.NONE)


def used_colors(image: Image.Image) -> list[int]:
    """画像が実際に使っている色を 0xRRGGBB の昇順で返す。"""
    rgb = image.convert("RGB")
    counts = rgb.getcolors(maxcolors=rgb.width * rgb.height)
    assert counts is not None
    return sorted((r << 16) | (g << 8) | b for _, (r, g, b) in counts)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    palette: list[int] = []
    for src_name, out_name, size in TARGETS:
        image = pixelate(SRC_DIR / src_name, size)
        image.save(OUT_DIR / out_name)
        for color in used_colors(image):
            if color not in palette:
                palette.append(color)
        print(f"{out_name}: {size[0]}x{size[1]}")
    (OUT_DIR / PALETTE_FILE).write_text(json.dumps({"colors": palette}, indent=2) + "\n")
    print(f"{PALETTE_FILE}: {len(palette)} colors")


if __name__ == "__main__":
    main()
