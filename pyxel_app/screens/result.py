"""リザルト画面(仕様書 §3.5。P4 時点は仮。自己ベスト・日本語化は P5)。"""

from __future__ import annotations

from typing import Final

import pyxel

import sfx
from scene.board_scene import BoardScene
from screens import draw
from screens.base import Pointer, Screen
from screens.ui import Button, ClickEdge, Rect
from session import GameSession

PANEL: Final = Rect(40, 40, 240, 160)
RETRY_BUTTON: Final = Button(Rect(64, 164, 80, 24), "RETRY")
TITLE_BUTTON: Final = Button(Rect(176, 164, 80, 24), "TITLE")


class ResultScreen(Screen):
    def __init__(self, session: GameSession, scene: BoardScene) -> None:
        self.session = session
        self.scene = scene
        self._click = ClickEdge()
        self._next: Screen | None = None

    def update(self, pointer: Pointer, now: float) -> Screen | None:
        self.scene.sync(0.0)
        edge = self._click.feed(pointer.x, pointer.y, pointer.held)
        if edge is None:
            return None
        from screens.game import GameScreen
        from screens.title import TitleScreen

        if RETRY_BUTTON.hit(*edge):
            sfx.play(sfx.Sfx.BUTTON)
            return GameScreen(self.session.table, self.scene, now)
        if TITLE_BUTTON.hit(*edge):
            sfx.play(sfx.Sfx.BUTTON)
            return TitleScreen(self.session.table, self.scene)
        return None

    def draw(self, now: float) -> None:
        self.scene.draw_to(0, 0, pyxel.width, pyxel.height)
        draw.panel(PANEL)
        cx = PANEL.cx
        draw.big_text(cx, PANEL.y + 18, "TIME UP", 10, 2)
        s = self.session
        draw.text_centered(cx, PANEL.y + 44, f"SCORE  {s.score:4d}", 7)
        stats = f"MISS {s.fail_count:2d}   JUDGE {s.judge_count:2d}"
        draw.text_centered(cx, PANEL.y + 58, stats, 7)
        best = s.best
        if best is None:
            draw.text_centered(cx, PANEL.y + 80, "BEST  -", 13)
        else:
            draw.text_centered(cx, PANEL.y + 80, f"BEST  {best.board}  {best.points}pt", 11)
        draw.button(RETRY_BUTTON)
        draw.button(TITLE_BUTTON, accent=6)
