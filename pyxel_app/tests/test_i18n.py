"""i18n のテスト: 辞書の欠落キー検出(DoD)、言語切替、日本語フォントのグリフ網羅。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import fields
from pathlib import Path

import pytest

import i18n

APP_DIR = Path(__file__).resolve().parents[1]
FONT_PATH = APP_DIR / "assets" / "umplus_j10r.bdf"

LANGS: tuple[i18n.Lang, ...] = ("ja", "en")


@pytest.fixture(autouse=True)
def _reset_lang() -> Iterator[None]:
    yield
    i18n.set_lang(i18n.DEFAULT_LANG)


# ---- 辞書の網羅(キー集合は dataclass で強制。空文字の混入をここで検出) ----


def test_all_message_fields_are_non_empty_in_both_langs() -> None:
    for lang in LANGS:
        messages = i18n.MESSAGES[lang]
        for f in fields(messages):
            value = getattr(messages, f.name)
            assert isinstance(value, str) and value.strip(), f"{lang}.{f.name}"


def test_rule_pages_have_same_shape_in_both_langs() -> None:
    ja, en = i18n.RULE_PAGES["ja"], i18n.RULE_PAGES["en"]
    assert len(ja) == len(en) == 5  # 既存 frontend の 5 ページを流用
    for page_ja, page_en in zip(ja, en, strict=True):
        assert page_ja.title.strip() and page_en.title.strip()
        assert 1 <= len(page_ja.lines) <= 8  # §3.6: 1 ページ 8 行以内
        assert 1 <= len(page_en.lines) <= 8
        assert all(line.strip() for line in page_ja.lines + page_en.lines)


def test_rule_lines_fit_in_320px_panel() -> None:
    # §3.6: 和文 10px で 1 行 32 文字。半角(ASCII)は 0.5 文字で数え、
    # パネル(幅 304px)に収まる全角 29 文字相当までに制限する
    for lang in LANGS:
        for page in i18n.RULE_PAGES[lang]:
            for line in page.lines:
                width = sum(0.5 if ord(ch) < 0x100 else 1.0 for ch in line)
                assert width <= 29, f"{lang}: {line}"


# ---- 言語状態 ----


def test_default_lang_is_japanese() -> None:
    assert i18n.DEFAULT_LANG == "ja"
    assert i18n.current() == "ja"
    assert i18n.msg() is i18n.MESSAGES["ja"]
    assert i18n.rule_pages() is i18n.RULE_PAGES["ja"]


def test_toggle_switches_between_ja_and_en() -> None:
    assert i18n.toggle() == "en"
    assert i18n.msg() is i18n.MESSAGES["en"]
    assert i18n.rule_pages() is i18n.RULE_PAGES["en"]
    assert i18n.toggle() == "ja"
    assert i18n.msg() is i18n.MESSAGES["ja"]


def test_set_lang() -> None:
    i18n.set_lang("en")
    assert i18n.current() == "en"


# ---- フォントのグリフ網羅(表示できない文字が辞書に入っていないか) ----


def _bdf_encodings(path: Path) -> set[int]:
    return {
        int(line.split()[1])
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.startswith("ENCODING ")
    }


def _all_display_strings() -> Iterator[str]:
    for lang in LANGS:
        messages = i18n.MESSAGES[lang]
        for f in fields(messages):
            yield getattr(messages, f.name)
        for page in i18n.RULE_PAGES[lang]:
            yield page.title
            yield from page.lines


def test_every_character_has_a_glyph_in_bundled_font() -> None:
    encodings = _bdf_encodings(FONT_PATH)
    missing = {
        ch for s in _all_display_strings() for ch in s if ch != " " and ord(ch) not in encodings
    }
    assert missing == set(), f"フォントに無い文字: {sorted(missing)}"
