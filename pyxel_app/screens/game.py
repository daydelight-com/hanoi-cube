"""ゲーム画面(仕様書 §3.4。Pyxel 依存)。

HUD(SCORE / TIME / MISS)、3-2-1-GO、JUDGE ボタン、判定フィードバックを描く。
入力の結線と判定は `screens/game_logic.GamePlay`、集計は `session.GameSession`、
盤面は `scene/board_scene.BoardScene`。ここはそれらを呼んで描くだけ。
"""

from __future__ import annotations

from typing import Final

import pyxel

import sfx
from app.core.precompute import PrecomputeTable
from board_state import BoardState
from input.drag import DragController
from input.pointer import PointerDriver
from scene.board_scene import BoardScene
from screens import draw
from screens.base import Pointer, Screen
from screens.game_logic import (
    HEIGHT,
    HUD_HEIGHT,
    JUDGE_BUTTON,
    TITLE_BUTTON,
    WIDTH,
    FeedbackKind,
    GameEvent,
    GamePlay,
)
from screens.result import ResultScreen
from session import GameSession

MAX_DT: Final = 0.1  # 処理落ち・タブ非表示からの復帰で平滑化が飛ばないよう dt を上限で切る
HUD_BG: Final = 0
HUD_LABEL: Final = 13
HUD_VALUE: Final = 7
WARNING_COLOR: Final = 8
BLINK_HZ: Final = 4
FEEDBACK_COLOR: Final[dict[FeedbackKind, int]] = {
    FeedbackKind.SCORED: 11,
    FeedbackKind.MISS: 8,
    FeedbackKind.ALREADY: 10,
}
FEEDBACK_CY: Final = 96  # 塔の上あたり

_SFX_OF: Final[dict[GameEvent, sfx.Sfx]] = {
    GameEvent.PLACE: sfx.Sfx.PLACE,
    GameEvent.DROP_FAIL: sfx.Sfx.FAIL,
    GameEvent.JUDGE_OK: sfx.Sfx.JUDGE_OK,
    GameEvent.JUDGE_MISS: sfx.Sfx.FAIL,
    GameEvent.JUDGE_ALREADY: sfx.Sfx.JUDGED,
    GameEvent.BUTTON: sfx.Sfx.BUTTON,
    GameEvent.COUNTDOWN: sfx.Sfx.COUNTDOWN,
    GameEvent.GO: sfx.Sfx.COUNTDOWN,
    GameEvent.TIME_UP: sfx.Sfx.TIMEUP,
}


class GameScreen(Screen):
    def __init__(self, table: PrecomputeTable, scene: BoardScene, now: float) -> None:
        self.scene = scene
        board = BoardState.initial()
        driver = PointerDriver(DragController(board), scene)
        scene.bind(driver)
        self.session = GameSession(table)
        self.session.start(now)
        self.play = GamePlay(self.session, driver)
        self._last = now
        self._go_title = False

    def update(self, pointer: Pointer, now: float) -> Screen | None:
        dt = min(now - self._last, MAX_DT)
        self._last = now
        events = self.play.frame(pointer.x, pointer.y, pointer.held, pointer.inside, now)
        if pyxel.btnp(pyxel.KEY_RETURN):  # 補助(§3.1)
            event = self.play.press_judge(now)
            if event is not None:
                events.append(event)
        for event in events:
            sound = _SFX_OF.get(event)
            if sound is not None:
                sfx.play(sound)
            if event is GameEvent.TITLE:
                self._go_title = True
        self.scene.sync(dt)
        if self._go_title:
            from screens.title import TitleScreen  # 循環 import 回避(title → game)

            return TitleScreen(self.session.table, self.scene)
        if self.session.is_over(now):
            return ResultScreen(self.session, self.scene)
        return None

    def draw(self, now: float) -> None:
        self.scene.draw_to(0, 0, WIDTH, HEIGHT)
        self._draw_hud(now)
        draw.button(TITLE_BUTTON, accent=6)
        draw.button(JUDGE_BUTTON, enabled=self.play.judge_enabled(now))
        value = self.session.countdown_value(now)
        if value is not None:
            draw.big_text(WIDTH / 2, FEEDBACK_CY, str(value), 10, 5)
        elif self.session.show_go(now):
            draw.big_text(WIDTH / 2, FEEDBACK_CY, "GO!", 11, 5)
        feedback = self.play.visible_feedback(now)
        if feedback is not None:
            draw.big_text(WIDTH / 2, FEEDBACK_CY, feedback.text, FEEDBACK_COLOR[feedback.kind], 4)

    def _draw_hud(self, now: float) -> None:
        pyxel.rect(0, 0, WIDTH, HUD_HEIGHT, HUD_BG)
        y = 5
        pyxel.text(6, y, "SCORE", HUD_LABEL)
        pyxel.text(30, y, f"{self.session.score:04d}", HUD_VALUE)
        time_col = HUD_VALUE
        if self.session.in_warning(now) and int(now * BLINK_HZ) % 2 == 0:
            time_col = WARNING_COLOR
        pyxel.text(136, y, "TIME", HUD_LABEL)
        pyxel.text(156, y, self.session.remaining_display(now), time_col)
        pyxel.text(274, y, "MISS", HUD_LABEL)
        pyxel.text(294, y, str(self.session.fail_count), HUD_VALUE)
