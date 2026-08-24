"""ドット化テクスチャの読み込み(Pyxel 依存)。

`scripts/make_pyxel_textures.py` が Three.js 版のアートワークから生成した
`assets/textures/` の PNG と palette.json を読む。`load()` は palette.json の色のうち
未登録のものを `pyxel.colors` の末尾へ追加してから PNG を読むため、Pyxel の
最近色量子化が完全一致になり無劣化で読み込める。

パレット追加を伴うので、`load()` は `BoardScene`(Shading)生成より前に呼ぶこと。
画像一式が無い環境では空の `Textures` を返し、呼び出し側は従来の単色描画へ縮退する。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

import pyxel

from app.core.board import Size

TEXTURES_DIR: Final = Path(__file__).resolve().parents[1] / "assets" / "textures"
PALETTE_FILE: Final = "palette.json"
BOX_FILES: Final[dict[Size, str]] = {"L": "cube_l.png", "M": "cube_m.png", "S": "cube_s.png"}
MAT_FILE: Final = "play_mat.png"


@dataclass(frozen=True)
class Textures:
    """読み込んだテクスチャ一式。欠けている分は単色描画へ縮退する。"""

    boxes: dict[Size, pyxel.Image] = field(default_factory=dict)
    mat: pyxel.Image | None = None


def extend_palette(textures_dir: Path = TEXTURES_DIR) -> None:
    """palette.json の色のうち未登録のものを `pyxel.colors` の末尾へ追加する(冪等)。"""
    path = textures_dir / PALETTE_FILE
    if not path.is_file():
        return
    colors = [int(c) for c in json.loads(path.read_text())["colors"]]
    existing = set(pyxel.colors)
    pyxel.colors.extend([c for c in colors if c not in existing])


def load(textures_dir: Path = TEXTURES_DIR) -> Textures:
    """パレットを拡張し、存在するテクスチャだけを読み込んで返す。"""
    extend_palette(textures_dir)
    boxes: dict[Size, pyxel.Image] = {}
    for size, name in BOX_FILES.items():
        path = textures_dir / name
        if path.is_file():
            boxes[size] = pyxel.Image.from_image(str(path))
    mat_path = textures_dir / MAT_FILE
    mat = pyxel.Image.from_image(str(mat_path)) if mat_path.is_file() else None
    return Textures(boxes=boxes, mat=mat)
