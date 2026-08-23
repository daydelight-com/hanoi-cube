"""描画の共通部品(Pyxel 依存): ボタン、拡大文字。"""

from __future__ import annotations

from typing import Final

import pyxel

from screens.ui import Button, Rect

CHAR_W: Final = 4  # 内蔵フォント(3x5 + 余白)
CHAR_H: Final = 6
_SCRATCH_W: Final = 64
_SCRATCH_H: Final = 8
_scratch: pyxel.Image | None = None


def _scratch_image() -> pyxel.Image:
    global _scratch
    if _scratch is None:
        _scratch = pyxel.Image(_SCRATCH_W, _SCRATCH_H)
    return _scratch


def big_text(cx: float, cy: float, s: str, col: int, scale: int, *, shadow: int | None = 0) -> None:
    """内蔵フォントを `scale` 倍にして (cx, cy) を中心に描く(オフスクリーン → 拡大 blt)。"""
    w = min(_SCRATCH_W, len(s) * CHAR_W)
    h = CHAR_H
    img = _scratch_image()
    colkey = 15 if col != 15 else 14
    img.rect(0, 0, _SCRATCH_W, _SCRATCH_H, colkey)
    img.text(0, 0, s, col)
    # blt の scale は (x, y, w, h) の中心を軸に拡大するので、中心が (cx, cy) に来るよう置く
    x = cx - w / 2
    y = cy - h / 2
    if shadow is not None:
        img_shadow = img  # 同じ画像を色違いで出すためパレット差し替えを使う
        pyxel.pal(col, shadow)
        pyxel.blt(x + scale, y + scale, img_shadow, 0, 0, w, h, colkey, 0, scale)
        pyxel.pal()
    pyxel.blt(x, y, img, 0, 0, w, h, colkey, 0, scale)


def button(b: Button, *, enabled: bool = True, accent: int = 11) -> None:
    r = b.rect
    face = accent if enabled else 5
    pyxel.rect(r.x, r.y, r.w, r.h, face)
    pyxel.rectb(r.x, r.y, r.w, r.h, 7 if enabled else 13)
    label_w = len(b.label) * CHAR_W - 1
    pyxel.text(r.cx - label_w // 2, r.cy - CHAR_H // 2 + 1, b.label, 0 if enabled else 13)


def panel(r: Rect, col: int = 0, border: int = 7) -> None:
    pyxel.rect(r.x, r.y, r.w, r.h, col)
    pyxel.rectb(r.x, r.y, r.w, r.h, border)


def text_centered(cx: float, y: float, s: str, col: int) -> None:
    pyxel.text(cx - (len(s) * CHAR_W - 1) / 2, y, s, col)
