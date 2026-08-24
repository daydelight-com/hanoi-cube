"""タイトル / ルール / リザルトのボタン矩形とクリック振り分け(Pyxel 非依存)。

描画(ラベルは言語で変わる)は各画面の Pyxel 依存層が行い、ここは矩形と遷移判断だけを持つ。
ゲーム画面のボタンは `screens/game_logic.py`。
"""

from __future__ import annotations

from enum import Enum
from typing import Final

from screens.ui import Button, Rect

# ---- タイトル(仕様書 §3.2) ----

TITLE_START_BUTTON: Final = Button(Rect(120, 140, 80, 26), "start")
TITLE_RULES_BUTTON: Final = Button(Rect(120, 174, 80, 20), "rules")
TITLE_LANG_BUTTON: Final = Button(Rect(264, 4, 52, 14), "lang")  # 右上(既存仕様 §5.3 と同じ位置)


class TitleAction(Enum):
    START = "start"
    RULES = "rules"
    LANG = "lang"


def title_action(x: float, y: float) -> TitleAction | None:
    if TITLE_START_BUTTON.hit(x, y):
        return TitleAction.START
    if TITLE_RULES_BUTTON.hit(x, y):
        return TitleAction.RULES
    if TITLE_LANG_BUTTON.hit(x, y):
        return TitleAction.LANG
    return None


# ---- ルール説明(仕様書 §3.3) ----

RULES_PREV_BUTTON: Final = Button(Rect(12, 214, 40, 20), "<")
RULES_NEXT_BUTTON: Final = Button(Rect(268, 214, 40, 20), ">")  # 最終ページでは「とじる」
RULES_BACK_BUTTON: Final = Button(Rect(138, 214, 44, 20), "back")


class RulesAction(Enum):
    PAGE_CHANGED = "page_changed"
    CLOSE = "close"  # BACK / 最終ページの「とじる」


class RulesNav:
    """ページ送りの状態。`click()` が状態を進めて起きたことを返す(反応なしは None)。"""

    def __init__(self, page_count: int) -> None:
        assert page_count > 0
        self.page_count = page_count
        self.page = 0

    @property
    def on_last_page(self) -> bool:
        return self.page == self.page_count - 1

    def click(self, x: float, y: float) -> RulesAction | None:
        if RULES_PREV_BUTTON.hit(x, y):
            if self.page == 0:
                return None  # 先頭ページでは無効(無音)
            self.page -= 1
            return RulesAction.PAGE_CHANGED
        if RULES_NEXT_BUTTON.hit(x, y):
            if self.on_last_page:
                return RulesAction.CLOSE
            self.page += 1
            return RulesAction.PAGE_CHANGED
        if RULES_BACK_BUTTON.hit(x, y):
            return RulesAction.CLOSE
        return None


# ---- リザルト(仕様書 §3.5。矩形は P4 と同じ) ----

RESULT_RETRY_BUTTON: Final = Button(Rect(64, 164, 80, 24), "retry")
RESULT_TITLE_BUTTON: Final = Button(Rect(176, 164, 80, 24), "title")


class ResultAction(Enum):
    RETRY = "retry"
    TITLE = "title"


def result_action(x: float, y: float) -> ResultAction | None:
    if RESULT_RETRY_BUTTON.hit(x, y):
        return ResultAction.RETRY
    if RESULT_TITLE_BUTTON.hit(x, y):
        return ResultAction.TITLE
    return None
