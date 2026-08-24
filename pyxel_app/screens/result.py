"""リザルト画面(仕様書 §3.5): スコア・しっぱい・はんてい回数・今回ベスト盤面・自己ベスト。

自己ベスト(`storage.best_store()`)は画面生成時に一度だけ反映し、更新なら「しんきろく!」を点滅させる。
クリック判断は `screens/menu_logic.py`。
"""

from __future__ import annotations

from typing import Final

import pyxel

import i18n
import sfx
import storage
from scene.board_scene import BoardScene
from screens import draw, menu_logic
from screens.base import Pointer, Screen
from screens.menu_logic import RESULT_RETRY_BUTTON, RESULT_TITLE_BUTTON, ResultAction
from screens.ui import ClickEdge, Rect
from session import GameSession

PANEL: Final = Rect(40, 40, 240, 160)
BLINK_HZ: Final = 2


class ResultScreen(Screen):
    def __init__(self, session: GameSession, scene: BoardScene) -> None:
        self.session = session
        self.scene = scene
        self._click = ClickEdge()
        store = storage.best_store()
        self.is_new_record = store.update(session.score)
        self.self_best = store.best

    def update(self, pointer: Pointer, now: float) -> Screen | None:
        self.scene.sync(0.0)
        if pyxel.btnp(pyxel.KEY_ESCAPE):  # 補助(§3.1)
            sfx.play(sfx.Sfx.BUTTON)
            return self._title()
        edge = self._click.feed(pointer.x, pointer.y, pointer.held)
        if edge is None:
            return None
        action = menu_logic.result_action(*edge)
        if action is ResultAction.RETRY:
            sfx.play(sfx.Sfx.BUTTON)
            from screens.game import GameScreen  # 循環 import 回避(game → result)

            return GameScreen(self.session.table, self.scene, now)
        if action is ResultAction.TITLE:
            sfx.play(sfx.Sfx.BUTTON)
            return self._title()
        return None

    def _title(self) -> Screen:
        from screens.title import TitleScreen

        return TitleScreen(self.session.table, self.scene)

    def draw(self, now: float) -> None:
        self.scene.draw_to(0, 0, pyxel.width, pyxel.height)
        m = i18n.msg()
        font = draw.FONT
        s = self.session
        draw.panel(PANEL, 0, draw.BRAND)
        cx = PANEL.cx
        draw.big_text(cx, PANEL.y + 18, m.resultHeading, 10, 2, font=font)
        # スコア(ラベルは小さく、数字は大きく)
        draw.text_centered(cx - 40, PANEL.y + 44, m.scoreLabel, 13, font)
        draw.big_text(cx + 30, PANEL.y + 49, f"{s.score}", 7, 3)
        stats = f"{m.failLabel} {s.fail_count}   {m.resultJudgeCount} {s.judge_count}"
        draw.text_centered(cx, PANEL.y + 68, stats, 7, font)
        best = s.best
        if best is not None:
            line = f"{m.resultBest}  {best.board}  {best.points}pt"
            draw.text_centered(cx, PANEL.y + 86, line, 11, font)
        else:
            draw.text_centered(cx, PANEL.y + 86, f"{m.resultBest}  -", 13, font)
        draw.text_centered(cx - 24, PANEL.y + 104, f"{m.selfBest}  {self.self_best}", 10, font)
        if self.is_new_record and int(now * BLINK_HZ) % 2 == 0:
            draw.text_centered(cx + 66, PANEL.y + 104, m.newRecord, 8, font)
        draw.button(RESULT_RETRY_BUTTON, accent=draw.BRAND, label=m.resultRetry, font=font)
        draw.button(RESULT_TITLE_BUTTON, accent=6, label=m.resultTitle, font=font)
