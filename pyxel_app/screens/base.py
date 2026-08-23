"""画面の基底(仕様書 §6.2)。Pyxel 依存層が継承する。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Pointer:
    """そのフレームのポインタ状態(`main.py` が Pyxel から読んで渡す)。"""

    x: int
    y: int
    held: bool  # 左ボタン押下中
    inside: bool  # ウィンドウ内


class Screen:
    """`update()` が次の画面(遷移なしは None)を返す。グローバルな状態機械は持たない。"""

    def update(self, pointer: Pointer, now: float) -> Screen | None:
        raise NotImplementedError

    def draw(self, now: float) -> None:
        raise NotImplementedError
