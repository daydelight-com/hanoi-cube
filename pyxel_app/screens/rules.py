"""ルール説明画面(仕様書 §3.3): 「<」「>」でページ送り、BACK / 最終ページで「とじる」。

文言は `i18n.RULE_PAGES`(既存 frontend の 5 ページを流用)。ページ状態は `menu_logic.RulesNav`。
各ページには図版(`rule_figures.RULE_FIGURES`。Three.js 版ルールダイアログの移植)を
本文の上に大きく描き、文言 3 行を下に添える(図が主役・文言が補助)。
"""

from __future__ import annotations

import math
from typing import Final

import pyxel

import i18n
import sfx
from app.core.precompute import PrecomputeTable
from scene.board_scene import BoardScene
from screens import draw, menu_logic, rule_figures
from screens.base import Pointer, Screen
from screens.menu_logic import (
    RULES_BACK_BUTTON,
    RULES_NEXT_BUTTON,
    RULES_PREV_BUTTON,
    RulesAction,
)
from screens.rule_figures import FigPanel, FigSize, Joiner, RuleFigure, Verdict
from screens.ui import ClickEdge, Rect

BG_COLOR: Final = 1
PANEL: Final = Rect(8, 10, 304, 194)
HEADING_H: Final = 22
FIG_TOP: Final = 33  # 図版の上端(見出し帯のすぐ下)
LINE_START_Y: Final = 142
LINE_STEP: Final = 14
INDICATOR_Y: Final = 186
INDICATOR_STEP: Final = 12

# 図版の色。箱は盤面テクスチャの実物色(大=緑/中=橙/小=白)に近いパレット色、枠線は各色の縁色。
# 棒・台・ラベルは基調色、○/矢印/バッジは +N と同じ緑、✕ は赤(frontend RuleFigure.tsx と同じ関係)。
BOX_FILL: Final[dict[FigSize, int]] = {"L": 11, "M": 9, "S": 7}
BOX_EDGE: Final[dict[FigSize, int]] = {"L": draw.BRAND, "M": 4, "S": 12}
OK_COLOR: Final = 11
NG_COLOR: Final = 8
FRAME_COLOR: Final = draw.BRAND


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
        # ページ数は文言(i18n)と図版で二重管理のため、範囲外はクランプして守る
        figs = rule_figures.RULE_FIGURES
        fig = figs[min(self.nav.page, len(figs) - 1)]
        _draw_figure(fig, PANEL.cx - rule_figures.figure_width(fig) // 2, FIG_TOP, i18n.current())
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


# ---- 図版の描画(データ・レイアウトは rule_figures.py) ----


def _draw_figure(fig: RuleFigure, x0: int, y0: int, lang: i18n.Lang) -> None:
    offsets = rule_figures.panel_offsets(fig)
    for panel, dx in zip(fig.panels, offsets, strict=True):
        _draw_panel(panel, x0 + dx, y0, lang)
    if fig.joiner is not None:
        for i in range(len(fig.panels) - 1):
            jx = x0 + offsets[i] + rule_figures.panel_width(fig.panels[i]) + rule_figures.PANEL_GAP
            _draw_joiner(fig.joiner, jx, y0)


def _draw_panel(panel: FigPanel, x: int, y: int, lang: i18n.Lang) -> None:
    w = rule_figures.panel_width(panel)
    if panel.towers:
        pyxel.rect(x + 2, y + rule_figures.BASE_Y, w - 4, 2, FRAME_COLOR)  # 台
    for t, stack in enumerate(panel.towers):
        cx = x + rule_figures.tower_center_x(t)
        pole_h = rule_figures.BASE_Y - rule_figures.POLE_TOP
        pyxel.rect(cx - 1, y + rule_figures.POLE_TOP, 2, pole_h, FRAME_COLOR)
        for level, size in enumerate(stack):
            _draw_box(cx, y + rule_figures.box_top_y(level), size)
        if panel.tower_labels:
            pyxel.text(cx - 1, y + rule_figures.LABEL_Y, "ABC"[t], FRAME_COLOR)  # 内蔵 4x6
    if panel.move is not None:
        _draw_move(panel, x, y)
    if panel.verdict is not None:
        _draw_verdict(panel.verdict, x + w - 10, y + rule_figures.VERDICT_CY)
    if panel.badge is not None:
        _draw_badge(panel.badge[lang], x + w // 2, y, bool(panel.towers))
    if panel.caption is not None:
        caption = panel.caption[lang]
        draw.text_centered(x + w / 2, y + rule_figures.CAPTION_Y, caption, 11, draw.FONT)


def _draw_box(cx: int, top: int, size: FigSize) -> None:
    w = rule_figures.BOX_W[size]
    h = rule_figures.BOX_H - 2  # 段の間に 1px の隙間を空ける
    pyxel.rect(cx - w // 2, top + 1, w, h, BOX_FILL[size])
    pyxel.rectb(cx - w // 2, top + 1, w, h, BOX_EDGE[size])
    pyxel.rect(cx - w // 2 + 2, top + 3, w - 4, 1, 7)  # ハイライト(立体感)


def _draw_verdict(kind: Verdict, cx: int, cy: int) -> None:
    if kind == "ok":
        pyxel.circb(cx, cy, rule_figures.VERDICT_R, OK_COLOR)
        pyxel.circb(cx, cy, rule_figures.VERDICT_R - 1, OK_COLOR)
    else:
        for o in (0, 1):  # 2px 幅の ✕
            pyxel.line(cx - 5 + o, cy - 5, cx + 5 + o, cy + 5, NG_COLOR)
            pyxel.line(cx + 5 - o, cy - 5, cx - 5 - o, cy + 5, NG_COLOR)


def _draw_move(panel: FigPanel, x: int, y: int) -> None:
    """箱を動かす矢印(移動元の箱に色枠 + 移動先の塔の上へ弧)。"""
    move = panel.move
    assert move is not None
    from_stack = panel.towers[move.from_tower]
    to_stack = panel.towers[move.to_tower]
    level = move.box_index if move.box_index is not None else len(from_stack) - 1
    size = from_stack[level]
    color = NG_COLOR if panel.verdict == "ng" else OK_COLOR
    w = rule_figures.BOX_W[size]
    sx_c = x + rule_figures.tower_center_x(move.from_tower)
    box_top = y + rule_figures.box_top_y(level)
    pyxel.rectb(sx_c - w // 2 - 2, box_top - 1, w + 4, rule_figures.BOX_H + 2, color)
    sy = box_top + rule_figures.BOX_H // 2
    tx = x + rule_figures.tower_center_x(move.to_tower)
    ty = y + rule_figures.box_top_y(len(to_stack)) - 2
    sx = sx_c + (w // 2 + 3 if tx > sx_c else -(w // 2 + 3))
    _draw_arc_arrow(sx, sy, (sx + tx) // 2, min(sy, ty) - 16, tx, ty, color)


def _draw_arc_arrow(x1: int, y1: int, cx: int, cy: int, x2: int, y2: int, col: int) -> None:
    """2次ベジェを折れ線近似した弧 + 終端の矢じり。"""
    steps = 12
    px, py = float(x1), float(y1)
    for i in range(1, steps + 1):
        t = i / steps
        qx = (1 - t) ** 2 * x1 + 2 * (1 - t) * t * cx + t * t * x2
        qy = (1 - t) ** 2 * y1 + 2 * (1 - t) * t * cy + t * t * y2
        pyxel.line(px, py, qx, qy, col)
        px, py = qx, qy
    ang = math.atan2(y2 - cy, x2 - cx)  # 終端の接線 = 制御点 → 終端
    for da in (2.6, -2.6):
        pyxel.line(x2, y2, x2 + 5 * math.cos(ang + da), y2 + 5 * math.sin(ang + da), col)


def _draw_badge(text: str, cx: int, y: int, has_towers: bool) -> None:
    """バッジ(得点式など)。塔のあるコマでは棒の上、ないコマでは中央。"""
    cy = y + (rule_figures.BADGE_CY if has_towers else rule_figures.BADGE_ONLY_CY)
    tw = draw.text_width(text, draw.FONT)
    bw = tw + 10
    pyxel.rect(cx - bw // 2, cy - 8, bw, 16, 0)
    pyxel.rectb(cx - bw // 2, cy - 8, bw, 16, OK_COLOR)
    draw.text_centered(cx, cy - 6, text, OK_COLOR, draw.FONT)


def _draw_joiner(kind: Joiner, x: int, y: int) -> None:
    cy = y + rule_figures.JOINER_CY
    jw = rule_figures.JOINER_W
    if kind == "arrow":
        pyxel.rect(x, cy - 1, jw - 4, 2, OK_COLOR)
        pyxel.tri(x + jw - 5, cy - 4, x + jw - 5, cy + 4, x + jw, cy, OK_COLOR)
        return
    # 鏡像: 縦の鏡線(破線)+ ⇄(左右の余白へ少しはみ出して描く)
    mx = x + jw // 2
    for yy in range(y + rule_figures.POLE_TOP - 8, y + rule_figures.BASE_Y + 6, 6):
        pyxel.rect(mx, yy, 1, 3, FRAME_COLOR)
    pyxel.rect(x - 4, cy - 1, jw + 8, 2, OK_COLOR)
    for sign in (1, -1):
        ex = x + jw + 6 if sign == 1 else x - 6
        pyxel.tri(ex - sign * 5, cy - 4, ex - sign * 5, cy + 4, ex, cy, OK_COLOR)
