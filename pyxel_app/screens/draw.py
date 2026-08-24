"""描画の共通部品(Pyxel 依存): ボタン、拡大文字、日本語フォント、基調色パレット。

日本語フォント(umplus 10px BDF)は `main.py` が `set_font()` で注入し、各描画関数に
`font=` で渡す(`None` なら内蔵 4x6 フォント)。基調色 `#438532`(既存仕様 §5.1)は
Pyxel 16 色に無いため、`setup_palette()` で未使用のスロット 3(GREEN)を差し替える。
"""

from __future__ import annotations

from typing import Final

import pyxel

from screens.ui import Button, Rect

CHAR_W: Final = 4  # 内蔵フォント(3x5 + 余白)
CHAR_H: Final = 6
FONT_H: Final = 12  # umplus 10px の行送り(BDF の bounding box 高さ)

BRAND: Final = 3  # 基調色に差し替えるパレット番号(pyxel_app 内で未使用の GREEN)
BRAND_RGB: Final = 0x438532

_SCRATCH_W: Final = 128
_SCRATCH_H: Final = 16
_scratch: pyxel.Image | None = None

FONT: pyxel.Font | None = None  # 日本語フォント(main.py が起動時に注入)


def setup_palette() -> None:
    """基調色をパレットへ入れる。`BoardScene`(Shading)生成より前に呼ぶこと。"""
    pyxel.colors[BRAND] = BRAND_RGB


def set_font(font: pyxel.Font) -> None:
    global FONT
    FONT = font


def text_width(s: str, font: pyxel.Font | None = None) -> int:
    if font is not None:
        return font.text_width(s)
    return len(s) * CHAR_W - 1


def text_height(font: pyxel.Font | None = None) -> int:
    return FONT_H if font is not None else CHAR_H


def _scratch_image() -> pyxel.Image:
    global _scratch
    if _scratch is None:
        _scratch = pyxel.Image(_SCRATCH_W, _SCRATCH_H)
    return _scratch


def big_text(
    cx: float,
    cy: float,
    s: str,
    col: int,
    scale: int,
    *,
    shadow: int | None = 0,
    font: pyxel.Font | None = None,
) -> None:
    """文字列を `scale` 倍にして (cx, cy) を中心に描く(オフスクリーン → 拡大 blt)。"""
    w = min(_SCRATCH_W, text_width(s, font))
    h = text_height(font)
    img = _scratch_image()
    colkey = 15 if col != 15 else 14
    img.rect(0, 0, _SCRATCH_W, _SCRATCH_H, colkey)
    img.text(0, 0, s, col, font)
    # blt の scale は (x, y, w, h) の中心を軸に拡大するので、中心が (cx, cy) に来るよう置く
    x = cx - w / 2
    y = cy - h / 2
    if shadow is not None:
        img_shadow = img  # 同じ画像を色違いで出すためパレット差し替えを使う
        pyxel.pal(col, shadow)
        pyxel.blt(x + scale, y + scale, img_shadow, 0, 0, w, h, colkey, 0, scale)
        pyxel.pal()
    pyxel.blt(x, y, img, 0, 0, w, h, colkey, 0, scale)


def button(
    b: Button,
    *,
    enabled: bool = True,
    accent: int = 11,
    label: str | None = None,
    font: pyxel.Font | None = None,
) -> None:
    """ボタンを描く。`label` を渡すと `b.label` の代わりに使う(言語別ラベル用)。"""
    r = b.rect
    face = accent if enabled else 5
    pyxel.rect(r.x, r.y, r.w, r.h, face)
    pyxel.rectb(r.x, r.y, r.w, r.h, 7 if enabled else 13)
    text = b.label if label is None else label
    # 基調色(暗め)の面には白、明るい面には黒のラベル
    text_col = (7 if accent == BRAND else 0) if enabled else 13
    x = r.cx - text_width(text, font) // 2
    y = r.cy - text_height(font) // 2 + 1
    pyxel.text(x, y, text, text_col, font)


def panel(r: Rect, col: int = 0, border: int = 7) -> None:
    pyxel.rect(r.x, r.y, r.w, r.h, col)
    pyxel.rectb(r.x, r.y, r.w, r.h, border)


def text_centered(cx: float, y: float, s: str, col: int, font: pyxel.Font | None = None) -> None:
    pyxel.text(cx - text_width(s, font) / 2, y, s, col, font)
