"""ゲーム画面の入力結線(Pyxel 非依存): ポインタ → ボタン / ドラッグ、JUDGE → `GameSession`。

`GameScreen`(Pyxel 依存)は毎フレーム `frame()` を呼び、返る `GameEvent` で効果音を鳴らすだけ。
描画に必要な値(フィードバック・ボタン矩形)もここが持つ。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

from app.core.engine import Judgement
from input.pointer import PointerDriver
from screens.ui import Button, Rect
from session import GameSession, JudgeRejection, SessionEvent

WIDTH: Final = 320
HEIGHT: Final = 240
HUD_HEIGHT: Final = 16
# 下段のボタン(§3.4)。3D ビューは全画面に描くので、箱と重ならない隅に置く
# (待機 L 列の前面は y≈220、L3 の右端は x≈270、L1 の左端は x≈74。P3 handoff)
JUDGE_BUTTON: Final = Button(Rect(258, 212, 58, 24), "JUDGE")
TITLE_BUTTON: Final = Button(Rect(4, 214, 44, 20), "TITLE")
FEEDBACK_SEC: Final = 1.0


class GameEvent(Enum):
    PLACE = "place"  # 箱を置いた
    DROP_FAIL = "drop_fail"  # 違反・範囲外で戻った
    JUDGE_OK = "judge_ok"  # scored
    JUDGE_MISS = "judge_miss"  # unclearable
    JUDGE_ALREADY = "judge_already"  # duplicate_*
    BUTTON = "button"  # TITLE など判定以外のボタン
    COUNTDOWN = "countdown"
    GO = "go"
    TIME_UP = "time_up"
    TITLE = "title"  # TITLE ボタンでタイトルへ(§3.4: 確認なし)


class FeedbackKind(Enum):
    SCORED = "scored"
    MISS = "miss"
    ALREADY = "already"


@dataclass(frozen=True)
class Feedback:
    kind: FeedbackKind
    text: str  # "+N" / "MISS" / "ALREADY"
    at: float

    def visible(self, now: float) -> bool:
        return now - self.at < FEEDBACK_SEC


_FEEDBACK_OF: dict[str, tuple[FeedbackKind, GameEvent]] = {
    "scored": (FeedbackKind.SCORED, GameEvent.JUDGE_OK),
    "unclearable": (FeedbackKind.MISS, GameEvent.JUDGE_MISS),
    "duplicate_same": (FeedbackKind.ALREADY, GameEvent.JUDGE_ALREADY),
    "duplicate_mirror": (FeedbackKind.ALREADY, GameEvent.JUDGE_ALREADY),
}

_SESSION_EVENT_OF: dict[SessionEvent, GameEvent] = {
    SessionEvent.COUNTDOWN_TICK: GameEvent.COUNTDOWN,
    SessionEvent.GO: GameEvent.GO,
    SessionEvent.TIME_UP: GameEvent.TIME_UP,
}


class GamePlay:
    """1 プレイの入力結線。`session.start()` を呼んでから使う。"""

    def __init__(self, session: GameSession, driver: PointerDriver) -> None:
        self.session = session
        self.driver = driver
        self.feedback: Feedback | None = None
        self._held = True  # 生成時点で押されていたボタン(RETRY など)はエッジにしない
        self._captured = False  # 押下がボタンで始まった間はドラッグに流さない

    # ---- 毎フレーム ----

    def frame(self, x: float, y: float, held: bool, inside: bool, now: float) -> list[GameEvent]:
        events = [_SESSION_EVENT_OF[e] for e in self.session.poll(now)]
        if GameEvent.TIME_UP in events and self.driver.drag.is_dragging:
            self.driver.leave()  # 持ったまま終了 → 元位置へ(音は出さない)
        press_edge = held and not self._held
        self._held = held
        if self.session.is_over(now):
            return events  # 終了後はボタンもドラッグも受け付けない(リザルトへ遷移する)
        if press_edge:
            if JUDGE_BUTTON.hit(x, y):
                self._captured = True
                event = self.press_judge(now)
                if event is not None:
                    events.append(event)
                return events
            if TITLE_BUTTON.hit(x, y):
                self._captured = True
                events += [GameEvent.BUTTON, GameEvent.TITLE]
                return events
        if self._captured:
            if not held:
                self._captured = False
            return events
        if held and not press_edge and not self.driver.drag.is_dragging:
            return events  # 入場前から押されていた(RETRY など)。離すまで無視
        outcome = self.driver.feed(x, y, held, inside)
        if outcome is not None:
            events.append(GameEvent.PLACE if outcome.placed else GameEvent.DROP_FAIL)
        return events

    def press_judge(self, now: float) -> GameEvent | None:
        """JUDGE(ボタン / Enter)。受け付けられなければ None(音も演出も無し)。"""
        if not self.driver.drag.can_judge():
            return None  # §4.5: ドラッグ中は判定不可
        result = self.session.judge(self.driver.board.board_string(), now)
        if isinstance(result, JudgeRejection):
            return None
        return self._apply_feedback(result, now)

    def _apply_feedback(self, judgement: Judgement, now: float) -> GameEvent:
        kind, event = _FEEDBACK_OF[judgement.result]
        text = {
            FeedbackKind.SCORED: f"+{judgement.points}",
            FeedbackKind.MISS: "MISS",
            FeedbackKind.ALREADY: "ALREADY",
        }[kind]
        self.feedback = Feedback(kind, text, now)
        return event

    # ---- 描画側が読む ----

    def visible_feedback(self, now: float) -> Feedback | None:
        if self.feedback is not None and self.feedback.visible(now):
            return self.feedback
        return None

    def judge_enabled(self, now: float) -> bool:
        """JUDGE ボタンを有効表示するか(クールダウン中・ドラッグ中・カウントダウン中は無効表示)。"""
        return self.session.can_judge(now) is None and self.driver.drag.can_judge()
