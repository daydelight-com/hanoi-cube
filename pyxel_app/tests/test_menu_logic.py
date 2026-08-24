"""タイトル / ルール / リザルトのボタン当たり判定と遷移判断のテスト(DoD)。Pyxel 非依存。"""

from __future__ import annotations

from screens.menu_logic import (
    RESULT_RETRY_BUTTON,
    RESULT_TITLE_BUTTON,
    RULES_BACK_BUTTON,
    RULES_NEXT_BUTTON,
    RULES_PREV_BUTTON,
    TITLE_LANG_BUTTON,
    TITLE_RULES_BUTTON,
    TITLE_START_BUTTON,
    ResultAction,
    RulesAction,
    RulesNav,
    TitleAction,
    result_action,
    title_action,
)
from screens.ui import Button

WIDTH, HEIGHT = 320, 240

TITLE_BUTTONS = (TITLE_START_BUTTON, TITLE_RULES_BUTTON, TITLE_LANG_BUTTON)
RULES_BUTTONS = (RULES_PREV_BUTTON, RULES_NEXT_BUTTON, RULES_BACK_BUTTON)
RESULT_BUTTONS = (RESULT_RETRY_BUTTON, RESULT_TITLE_BUTTON)


# ---- 矩形の健全性(画面内・同一画面で重ならない) ----


def _assert_on_screen_and_disjoint(buttons: tuple[Button, ...]) -> None:
    for b in buttons:
        r = b.rect
        assert r.x >= 0 and r.x + r.w <= WIDTH, b.label
        assert r.y >= 0 and r.y + r.h <= HEIGHT, b.label
    for i, a in enumerate(buttons):
        for b in buttons[i + 1 :]:
            ra, rb = a.rect, b.rect
            overlap_x = ra.x < rb.x + rb.w and rb.x < ra.x + ra.w
            overlap_y = ra.y < rb.y + rb.h and rb.y < ra.y + ra.h
            assert not (overlap_x and overlap_y), f"{a.label} と {b.label} が重なる"


def test_buttons_are_on_screen_and_disjoint_per_screen() -> None:
    _assert_on_screen_and_disjoint(TITLE_BUTTONS)
    _assert_on_screen_and_disjoint(RULES_BUTTONS)
    _assert_on_screen_and_disjoint(RESULT_BUTTONS)


# ---- タイトル ----


def test_title_action_hits_each_button() -> None:
    assert title_action(TITLE_START_BUTTON.rect.cx, TITLE_START_BUTTON.rect.cy) is TitleAction.START
    assert title_action(TITLE_RULES_BUTTON.rect.cx, TITLE_RULES_BUTTON.rect.cy) is TitleAction.RULES
    assert title_action(TITLE_LANG_BUTTON.rect.cx, TITLE_LANG_BUTTON.rect.cy) is TitleAction.LANG


def test_title_action_rect_edges_are_half_open() -> None:
    r = TITLE_START_BUTTON.rect
    assert title_action(r.x, r.y) is TitleAction.START  # 左上は含む
    assert title_action(r.x + r.w - 1, r.y + r.h - 1) is TitleAction.START
    assert title_action(r.x + r.w, r.y + r.h) is None  # 右下の外側
    assert title_action(r.x - 1, r.y) is None


def test_title_action_outside_all_buttons_is_none() -> None:
    assert title_action(0, 0) is None
    assert title_action(160, 100) is None  # 盤面(ボタン外)


# ---- ルール(ページ送りと閉じる) ----


def _click(nav: RulesNav, b: Button) -> RulesAction | None:
    return nav.click(b.rect.cx, b.rect.cy)


def test_rules_nav_pages_forward_and_backward() -> None:
    nav = RulesNav(5)
    assert _click(nav, RULES_PREV_BUTTON) is None  # 先頭ページの「<」は無効
    assert nav.page == 0
    for expected in (1, 2, 3, 4):
        assert _click(nav, RULES_NEXT_BUTTON) is RulesAction.PAGE_CHANGED
        assert nav.page == expected
    assert nav.on_last_page
    assert _click(nav, RULES_PREV_BUTTON) is RulesAction.PAGE_CHANGED
    assert nav.page == 3


def test_rules_nav_next_on_last_page_closes() -> None:
    nav = RulesNav(2)
    assert _click(nav, RULES_NEXT_BUTTON) is RulesAction.PAGE_CHANGED
    assert nav.on_last_page
    assert _click(nav, RULES_NEXT_BUTTON) is RulesAction.CLOSE  # 最終ページの「とじる」
    assert nav.page == 1  # 閉じてもページは変えない


def test_rules_nav_back_always_closes() -> None:
    nav = RulesNav(5)
    assert _click(nav, RULES_BACK_BUTTON) is RulesAction.CLOSE
    _click(nav, RULES_NEXT_BUTTON)
    assert _click(nav, RULES_BACK_BUTTON) is RulesAction.CLOSE


def test_rules_nav_outside_buttons_is_none() -> None:
    nav = RulesNav(5)
    assert nav.click(160, 100) is None
    assert nav.page == 0


def test_rules_nav_single_page_next_closes_immediately() -> None:
    nav = RulesNav(1)
    assert _click(nav, RULES_NEXT_BUTTON) is RulesAction.CLOSE


# ---- リザルト ----


def test_result_action_hits_each_button() -> None:
    r = RESULT_RETRY_BUTTON.rect
    assert result_action(r.cx, r.cy) is ResultAction.RETRY
    t = RESULT_TITLE_BUTTON.rect
    assert result_action(t.cx, t.cy) is ResultAction.TITLE
    assert result_action(160, 100) is None
    assert result_action(r.x + r.w, r.cy) is None  # 右端の外側(半開区間)
