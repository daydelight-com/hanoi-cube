"""ルール図版(rule_figures.py)のデータとレイアウトのテスト。Pyxel 非依存。

図版はルールの実例なので、○✕ がルールブック(配置ルール・移動ルール)と一致することも
データから検証する(絵と本文が食い違う事故を防ぐ)。
"""

from __future__ import annotations

from itertools import pairwise

from i18n import RULE_PAGES
from screens import rule_figures as rf
from screens.rule_figures import FigPanel, FigSize, Move

SIZE_ORDER: dict[FigSize, int] = {"L": 3, "M": 2, "S": 1}


# ---- ページとの対応・レイアウト ----


def test_figures_match_rule_page_count() -> None:
    assert len(rf.RULE_FIGURES) == len(RULE_PAGES["ja"]) == len(RULE_PAGES["en"])


def test_every_figure_fits_in_panel_width() -> None:
    for fig in rf.RULE_FIGURES:
        assert rf.figure_width(fig) <= rf.MAX_FIGURE_W, fig


def test_panel_offsets_leave_gaps_and_end_at_figure_width() -> None:
    for fig in rf.RULE_FIGURES:
        offsets = rf.panel_offsets(fig)
        assert len(offsets) == len(fig.panels)
        prev_end: int | None = None
        for panel, off in zip(fig.panels, offsets, strict=True):
            if prev_end is not None:
                assert off - prev_end >= rf.PANEL_GAP * 2  # コマの間に隙間がある
            prev_end = off + rf.panel_width(panel)
        assert prev_end == rf.figure_width(fig)


def test_vertical_layout_fits_figure_height() -> None:
    # 3 段積みでも棒の上端より下、キャプション(10px フォント)は FIG_H に収まる
    assert rf.box_top_y(2) >= rf.POLE_TOP
    assert rf.CAPTION_Y + 10 <= rf.FIG_H
    assert rf.VERDICT_CY - rf.VERDICT_R >= 0


# ---- データの健全性 ----


def test_stacks_have_at_most_three_known_boxes() -> None:
    for fig in rf.RULE_FIGURES:
        for panel in fig.panels:
            for stack in panel.towers:
                assert len(stack) <= 3
                assert all(size in rf.BOX_W for size in stack)


def test_captions_and_badges_are_bilingual_and_nonempty() -> None:
    for fig in rf.RULE_FIGURES:
        for panel in fig.panels:
            for text in (panel.caption, panel.badge):
                if text is not None:
                    assert set(text) == {"ja", "en"}
                    assert all(text[lang] for lang in ("ja", "en"))


def test_moves_reference_existing_towers_and_boxes() -> None:
    for fig in rf.RULE_FIGURES:
        for panel in fig.panels:
            move = panel.move
            if move is None:
                continue
            assert 0 <= move.from_tower < len(panel.towers)
            assert 0 <= move.to_tower < len(panel.towers)
            assert move.from_tower != move.to_tower
            assert panel.towers[move.from_tower]  # 空の塔からは動かせない
            if move.box_index is not None:
                assert 0 <= move.box_index < len(panel.towers[move.from_tower])


# ---- ○✕ がルールと一致すること ----


def _stack_legal(stack: tuple[FigSize, ...]) -> bool:
    """配置ルール: 上に行くほど小さい(同サイズ不可)。"""
    return all(SIZE_ORDER[low] > SIZE_ORDER[high] for low, high in pairwise(stack))


def _move_legal(panel: FigPanel, move: Move) -> bool:
    """移動ルール: いちばん上の箱を、空の塔か自分より大きい箱の上へ。"""
    from_stack = panel.towers[move.from_tower]
    to_stack = panel.towers[move.to_tower]
    level = move.box_index if move.box_index is not None else len(from_stack) - 1
    if level != len(from_stack) - 1:
        return False
    if len(to_stack) >= 3:
        return False
    return not to_stack or SIZE_ORDER[to_stack[-1]] > SIZE_ORDER[from_stack[level]]


def test_verdicts_match_hanoi_rules() -> None:
    for fig in rf.RULE_FIGURES:
        for panel in fig.panels:
            if panel.verdict is None:
                continue
            legal = all(_stack_legal(s) for s in panel.towers) and (
                panel.move is None or _move_legal(panel, panel.move)
            )
            assert legal == (panel.verdict == "ok"), panel


def test_clear_page_shows_mirrored_start() -> None:
    """クリアの図(ページ 3)は「さいしょ」とその左右反転が並ぶ。"""
    fig = rf.RULE_FIGURES[3]
    assert fig.joiner == "mirror"
    first, second = fig.panels
    assert second.towers == rf.mirror_towers(first.towers)


def test_mirror_towers_reverses_and_roundtrips() -> None:
    towers: tuple[tuple[FigSize, ...], ...] = (("L", "M"), ("S",), ())
    assert rf.mirror_towers(towers) == ((), ("S",), ("L", "M"))
    assert rf.mirror_towers(rf.mirror_towers(towers)) == towers
