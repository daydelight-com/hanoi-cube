"""画面部品の純ロジック(矩形・ボタンの当たり判定)。Pyxel に依存しない。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    def contains(self, px: float, py: float) -> bool:
        return self.x <= px < self.x + self.w and self.y <= py < self.y + self.h

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2


@dataclass(frozen=True)
class Button:
    """ラベル付きボタン。描画は Pyxel 依存層(`screens/draw.py`)が行う。"""

    rect: Rect
    label: str

    def hit(self, px: float, py: float) -> bool:
        return self.rect.contains(px, py)


class ClickEdge:
    """押下エッジの検出(ボタンは mouse down で反応させる。タッチでも同じ)。

    生成時点で押されていたボタンはエッジにしない(Pyxel web の「CLICK TO START」のクリックや
    前画面のボタンを押したまま遷移した場合に、次の画面のボタンを誤って押さないため)。
    """

    def __init__(self) -> None:
        self._held = True

    def feed(self, x: float, y: float, held: bool) -> tuple[float, float] | None:
        """毎フレーム呼ぶ。押下エッジならその座標、それ以外は None。"""
        edge = (x, y) if held and not self._held else None
        self._held = held
        return edge
