"""ルール説明の図版データとレイアウト(Pyxel 非依存)。

既存 frontend の `display/screens/ruleFigures.ts`(Three.js 版ルールダイアログの図版)を
320✕240 向けに移植した。図版は「文字が読めない子でも ○✕ と矢印で分かる」ことを狙い、
盤面テクスチャの実物色(大=緑/中=橙/小=白)で塔に積んだ箱を描く。文言の正は
docs/game/hanoi_arrange_rules.md。描画(Pyxel 依存)は `screens/rules.py`。

座標は図版ローカル(左上原点)。`screens/rules.py` がパネル中央に置く。
320✕240 では長いキャプションが入らないため、キャプションは要所(あらまし・クリア)だけに
絞り、○✕ の理由は本文 3 行(`i18n.RULE_PAGES`)に委ねる。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

from i18n import Lang

FigSize = Literal["L", "M", "S"]
Verdict = Literal["ok", "ng"]
Joiner = Literal["arrow", "mirror"]

# ---- 寸法(図版ローカル座標。スクリーン座標への配置は rules.py) ----

BOX_W: Final[dict[FigSize, int]] = {"L": 32, "M": 24, "S": 16}
BOX_H: Final = 10
TOWER_PITCH: Final = 36
PANEL_PAD_X: Final = 6
PANEL_GAP: Final = 8
JOINER_W: Final = 12
BADGE_PANEL_W: Final = 56  # 塔のないコマ(バッジだけ)の幅

FIG_H: Final = 107
VERDICT_CY: Final = 24  # 塔から離れて浮かないよう、棒の上端に寄せる
VERDICT_R: Final = 7
POLE_TOP: Final = 50
BASE_Y: Final = 84
LABEL_Y: Final = 89  # A/B/C(内蔵 4x6 フォント)
CAPTION_Y: Final = 97  # 10px フォント。FIG_H に収まる
JOINER_CY: Final = 60
BADGE_CY: Final = 24  # 塔のあるコマ: 棒の上
BADGE_ONLY_CY: Final = 60  # 塔のないコマ: 中央(つなぎ矢印の高さに合わせる)

# 図版を置ける最大幅(ルール画面のパネル幅 304 から左右余白を引いた値)
MAX_FIGURE_W: Final = 296


@dataclass(frozen=True)
class Move:
    """箱を動かす矢印。`box_index` は移動元の塔の下からの段(省略はいちばん上)。"""

    from_tower: int
    to_tower: int
    box_index: int | None = None


@dataclass(frozen=True)
class FigPanel:
    """図版1コマ。`towers` は塔(左→右)、各塔は下→上の箱列。"""

    towers: tuple[tuple[FigSize, ...], ...]
    verdict: Verdict | None = None  # ○✕印(コマ右上)
    move: Move | None = None
    caption: dict[Lang, str] | None = None  # コマ下の短い説明(日英)
    badge: dict[Lang, str] | None = None  # コマ内のバッジ(得点式など。日英)
    tower_labels: bool = False  # 塔の足元に A/B/C を出す


@dataclass(frozen=True)
class RuleFigure:
    panels: tuple[FigPanel, ...]
    joiner: Joiner | None = None  # コマ間の記号(→ / ⇄)


def panel_width(panel: FigPanel) -> int:
    if not panel.towers:
        return BADGE_PANEL_W
    return PANEL_PAD_X * 2 + len(panel.towers) * TOWER_PITCH


def tower_center_x(index: int) -> int:
    """コマ内での塔の中心 x。"""
    return PANEL_PAD_X + TOWER_PITCH * index + TOWER_PITCH // 2


def box_top_y(level: int) -> int:
    """下から `level` 段目の箱の上端 y。"""
    return BASE_Y - BOX_H * (level + 1)


def figure_width(fig: RuleFigure) -> int:
    panels = sum(panel_width(p) for p in fig.panels)
    gaps = max(0, len(fig.panels) - 1)
    joiner = JOINER_W if fig.joiner else 0
    return panels + gaps * (PANEL_GAP * 2 + joiner)


def panel_offsets(fig: RuleFigure) -> list[int]:
    """各コマの左端 x(図版座標)。"""
    offsets: list[int] = []
    x = 0
    joiner = JOINER_W if fig.joiner else 0
    for i, p in enumerate(fig.panels):
        if i > 0:
            x += PANEL_GAP * 2 + joiner
        offsets.append(x)
        x += panel_width(p)
    return offsets


def mirror_towers(towers: tuple[tuple[FigSize, ...], ...]) -> tuple[tuple[FigSize, ...], ...]:
    """左右反転(A⇄C)。クリア条件の図に使う。"""
    return tuple(reversed(towers))


# ---- ページごとの図版(i18n.RULE_PAGES と同じ順・同じページ数) ----

_START: Final[tuple[tuple[FigSize, ...], ...]] = (("L", "M", "S"), ("L", "M"), ("L",))

RULE_FIGURES: Final[tuple[RuleFigure, ...]] = (
    # 0 どんなゲーム?: 積む → はんてい → ポイント
    RuleFigure(
        joiner="arrow",
        panels=(
            FigPanel(
                towers=_START,
                tower_labels=True,
                caption={"ja": "はこを つむ", "en": "STACK"},
            ),
            FigPanel(
                towers=(),
                badge={"ja": "はんてい!", "en": "JUDGE!"},
                caption={"ja": "ボタンを おす", "en": "PRESS"},
            ),
            FigPanel(
                towers=(),
                badge={"ja": "+18", "en": "+18"},
                caption={"ja": "ポイント!", "en": "POINTS!"},
            ),
        ),
    ),
    # 1 つみかた ○✕(理由は本文 3 行が説明する)
    RuleFigure(
        panels=(
            FigPanel(towers=(("L", "M", "S"),), verdict="ok"),
            FigPanel(towers=(("S", "L"),), verdict="ng"),
            FigPanel(towers=(("M", "M"),), verdict="ng"),
        ),
    ),
    # 2 うごかしかた ○✕
    RuleFigure(
        panels=(
            FigPanel(towers=(("M", "S"), ("L",)), move=Move(0, 1), verdict="ok"),
            FigPanel(towers=(("L", "M"), ("S",)), move=Move(0, 1), verdict="ng"),
            FigPanel(towers=(("L", "M", "S"), ()), move=Move(0, 1, box_index=1), verdict="ng"),
        ),
    ),
    # 3 クリアとは: さいしょ ⇄ ひっくりかえし
    RuleFigure(
        joiner="mirror",
        panels=(
            FigPanel(towers=_START, tower_labels=True, caption={"ja": "さいしょ", "en": "START"}),
            FigPanel(
                towers=mirror_towers(_START),
                tower_labels=True,
                verdict="ok",
                caption={"ja": "ひだりみぎ はんたい", "en": "MIRRORED"},
            ),
        ),
    ),
    # 4 ポイント: はこのかず ✕ てすう
    RuleFigure(
        panels=(
            FigPanel(
                towers=_START,
                tower_labels=True,
                badge={"ja": "6こ × 3て = 18", "en": "6 BOXES x 3 MOVES = 18"},  # noqa: RUF001
            ),
        ),
    ),
)
