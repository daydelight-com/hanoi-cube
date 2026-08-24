"""タイトル画面(仕様書 §3.2): ロゴ、点滅プロンプト、スタート / ルール、言語切替、自己ベスト。

Pyxel Web は最初のクリックまで音声が出せないが、タイトルのボタンクリックがそのまま解放を兼ねる
(ランタイムの「CLICK TO START」も同様)。クリック判断は `screens/menu_logic.py`。
"""

from __future__ import annotations

from typing import Final

import pyxel

import i18n
import sfx
import storage
from app.core.precompute import PrecomputeTable
from scene.board_scene import BoardScene
from screens import draw, menu_logic
from screens.base import Pointer, Screen
from screens.menu_logic import (
    TITLE_LANG_BUTTON,
    TITLE_RULES_BUTTON,
    TITLE_START_BUTTON,
    TitleAction,
)
from screens.ui import ClickEdge

TITLE_TEXT: Final = "HANOI CUBE"  # ロゴは言語非依存(既存仕様 §5.13)
BLINK_HZ: Final = 2


class TitleScreen(Screen):
    def __init__(self, table: PrecomputeTable, scene: BoardScene) -> None:
        self.table = table
        self.scene = scene
        self._click = ClickEdge()

    def update(self, pointer: Pointer, now: float) -> Screen | None:
        self.scene.sync(0.0)
        edge = self._click.feed(pointer.x, pointer.y, pointer.held)
        if edge is None:
            return None
        action = menu_logic.title_action(*edge)
        if action is TitleAction.START:
            sfx.play(sfx.Sfx.BUTTON)
            from screens.game import GameScreen

            return GameScreen(self.table, self.scene, now)
        if action is TitleAction.RULES:
            sfx.play(sfx.Sfx.BUTTON)
            from screens.rules import RulesScreen

            return RulesScreen(self.table, self.scene)
        if action is TitleAction.LANG:
            sfx.play(sfx.Sfx.BUTTON)
            i18n.toggle()
        return None

    def draw(self, now: float) -> None:
        self.scene.draw_to(0, 0, pyxel.width, pyxel.height)
        m = i18n.msg()
        font = draw.FONT
        draw.big_text(pyxel.width / 2, 56, TITLE_TEXT, 7, 3, shadow=draw.BRAND)
        draw.text_centered(pyxel.width / 2, 84, m.titleSubtitle, 10, font)
        if int(now * BLINK_HZ) % 2 == 0:
            draw.text_centered(pyxel.width / 2, 116, m.titleClickStart, 7, font)
        draw.button(TITLE_START_BUTTON, accent=draw.BRAND, label=m.titleStart, font=font)
        draw.button(TITLE_RULES_BUTTON, accent=6, label=m.titleRules, font=font)
        self._draw_lang_button()
        best = storage.best_store().best
        if best > 0:
            draw.text_centered(pyxel.width / 2, 224, f"{m.selfBest}  {best}", 10, font)

    def _draw_lang_button(self) -> None:
        """「JA / EN」(現在の言語を明るく)。ラベルが 2 色なので draw.button を使わず自前で描く。"""
        r = TITLE_LANG_BUTTON.rect
        draw.panel(r, 0, 7)
        active, inactive = 7, 13
        ja_col = active if i18n.current() == "ja" else inactive
        en_col = active if i18n.current() == "en" else inactive
        pyxel.text(r.x + 6, r.cy - draw.CHAR_H // 2 + 1, "JA", ja_col)
        pyxel.text(r.cx - 2, r.cy - draw.CHAR_H // 2 + 1, "/", 5)
        pyxel.text(r.x + r.w - 14, r.cy - draw.CHAR_H // 2 + 1, "EN", en_col)
