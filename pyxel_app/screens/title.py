"""タイトル画面(P4 時点の仮。ルール説明・言語切替・自己ベストは P5 で実装する)。"""

from __future__ import annotations

from typing import Final

import pyxel

import sfx
from app.core.precompute import PrecomputeTable
from scene.board_scene import BoardScene
from screens import draw
from screens.base import Pointer, Screen
from screens.ui import Button, ClickEdge, Rect

START_BUTTON: Final = Button(Rect(120, 150, 80, 24), "START")
TITLE_TEXT: Final = "HANOI CUBE"


class TitleScreen(Screen):
    def __init__(self, table: PrecomputeTable, scene: BoardScene) -> None:
        self.table = table
        self.scene = scene
        self._click = ClickEdge()

    def update(self, pointer: Pointer, now: float) -> Screen | None:
        self.scene.sync(0.0)
        edge = self._click.feed(pointer.x, pointer.y, pointer.held)
        if edge is not None and START_BUTTON.hit(*edge):
            sfx.play(sfx.Sfx.BUTTON)
            from screens.game import GameScreen

            return GameScreen(self.table, self.scene, now)
        return None

    def draw(self, now: float) -> None:
        self.scene.draw_to(0, 0, pyxel.width, pyxel.height)
        draw.big_text(pyxel.width / 2, 60, TITLE_TEXT, 7, 3)
        draw.button(START_BUTTON)
