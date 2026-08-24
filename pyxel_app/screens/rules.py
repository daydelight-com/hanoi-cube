"""ルール説明画面(仕様書 §3.3): 「<」「>」でページ送り、BACK / 最終ページで「とじる」。

文言は `i18n.RULE_PAGES`(既存 frontend の 5 ページを流用)。ページ状態は `menu_logic.RulesNav`。
"""

from __future__ import annotations

from typing import Final

import pyxel

import i18n
import sfx
from app.core.precompute import PrecomputeTable
from scene.board_scene import BoardScene
from screens import draw, menu_logic
from screens.base import Pointer, Screen
from screens.menu_logic import (
    RULES_BACK_BUTTON,
    RULES_NEXT_BUTTON,
    RULES_PREV_BUTTON,
    RulesAction,
)
from screens.ui import ClickEdge, Rect

BG_COLOR: Final = 1
PANEL: Final = Rect(8, 10, 304, 194)
HEADING_H: Final = 22
LINE_START_Y: Final = 58
LINE_STEP: Final = 18
INDICATOR_Y: Final = 186
INDICATOR_STEP: Final = 12


class RulesScreen(Screen):
    def __init__(self, table: PrecomputeTable, scene: BoardScene) -> None:
        self.table = table
        self.scene = scene
        self.nav = menu_logic.RulesNav(len(i18n.rule_pages()))
        self._click = ClickEdge()

    def update(self, pointer: Pointer, now: float) -> Screen | None:
        if pyxel.btnp(pyxel.KEY_ESCAPE):  # 補助(§3.1)
            sfx.play(sfx.Sfx.BUTTON)
            return self._title()
        edge = self._click.feed(pointer.x, pointer.y, pointer.held)
        if edge is None:
            return None
        action = self.nav.click(*edge)
        if action is RulesAction.PAGE_CHANGED:
            sfx.play(sfx.Sfx.BUTTON)
        elif action is RulesAction.CLOSE:
            sfx.play(sfx.Sfx.BUTTON)
            return self._title()
        return None

    def _title(self) -> Screen:
        from screens.title import TitleScreen  # 循環 import 回避(title → rules)

        return TitleScreen(self.table, self.scene)

    def draw(self, now: float) -> None:
        pyxel.cls(BG_COLOR)
        m = i18n.msg()
        font = draw.FONT
        pages = i18n.rule_pages()
        page = pages[self.nav.page]
        draw.panel(PANEL, 0, 7)
        pyxel.rect(PANEL.x + 1, PANEL.y + 1, PANEL.w - 2, HEADING_H, draw.BRAND)
        draw.text_centered(PANEL.cx, PANEL.y + 6, page.title, 7, font)
        for i, line in enumerate(page.lines):
            draw.text_centered(PANEL.cx, LINE_START_Y + i * LINE_STEP, line, 7, font)
        self._draw_indicator(len(pages))
        draw.button(RULES_PREV_BUTTON, enabled=self.nav.page > 0, accent=6)
        if self.nav.on_last_page:
            draw.button(RULES_NEXT_BUTTON, accent=draw.BRAND, label=m.rulesClose, font=font)
        else:
            draw.button(RULES_NEXT_BUTTON, accent=6)
        draw.button(RULES_BACK_BUTTON, accent=6, label=m.rulesBack, font=font)

    def _draw_indicator(self, count: int) -> None:
        """ページインジケーター(●○○○○)。"""
        x0 = PANEL.cx - (count - 1) * INDICATOR_STEP / 2
        for i in range(count):
            x = x0 + i * INDICATOR_STEP
            if i == self.nav.page:
                pyxel.circ(x, INDICATOR_Y, 2, 10)
            else:
                pyxel.circb(x, INDICATOR_Y, 2, 13)
