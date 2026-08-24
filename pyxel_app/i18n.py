"""表示文言の日英辞書(仕様書 §3.6)。Pyxel に依存しない。

文言は既存 `frontend/src/i18n/strings.ts` を流用し、Pyxel 版固有のキー(ボタン名など)だけ追加した。
`Messages` を frozen dataclass にすることで両言語のキー集合の一致を構築時に強制し、
空文字の混入はテスト(`tests/test_i18n.py`)で検出する。
言語状態はこのモジュールが 1 つ持つ(既定は日本語。タイトル画面の JA/EN ボタンで切替)。

ゲームタイトル(HANOI CUBE)・カウントダウン・GO!・スコア数値・盤面文字列は
言語非依存(既存仕様 §5.13)。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Lang = Literal["ja", "en"]

DEFAULT_LANG: Final[Lang] = "ja"


@dataclass(frozen=True)
class Messages:
    # タイトル
    titleSubtitle: str
    titleClickStart: str  # 点滅プロンプト(§3.2。クリック操作なので「けっていボタンで」から変更)
    titleStart: str
    titleRules: str
    # ルール説明
    rulesBack: str
    rulesClose: str
    # ゲーム HUD / ボタン
    scoreLabel: str
    timeLabel: str
    failLabel: str
    judgeButton: str
    titleButton: str
    # 判定フィードバック(scored は +N 表示のため言語非依存)
    judgeFail: str
    judgeDup: str
    # リザルト
    resultHeading: str
    resultJudgeCount: str
    resultBest: str
    resultRetry: str
    resultTitle: str
    # 自己ベスト(タイトル・リザルト共通)
    selfBest: str
    newRecord: str


MESSAGES: Final[dict[Lang, Messages]] = {
    "ja": Messages(
        titleSubtitle="はこを ならべて スコアアタック!",
        titleClickStart="クリックで スタート",
        titleStart="スタート",
        titleRules="ルール",
        rulesBack="もどる",
        rulesClose="とじる",
        scoreLabel="スコア",
        timeLabel="のこり",
        failLabel="しっぱい",
        judgeButton="はんてい",
        titleButton="タイトル",
        judgeFail="しっぱい...",
        judgeDup="はんていずみ",
        resultHeading="タイムアップ!",
        resultJudgeCount="はんてい",
        resultBest="ベスト",
        resultRetry="もういちど",
        resultTitle="タイトルへ",
        selfBest="じこベスト",
        newRecord="しんきろく!",
    ),
    "en": Messages(
        titleSubtitle="STACK THE BOXES, BEAT THE SCORE!",
        titleClickStart="CLICK TO START",
        titleStart="START",
        titleRules="RULES",
        rulesBack="BACK",
        rulesClose="CLOSE",
        scoreLabel="SCORE",
        timeLabel="TIME",
        failLabel="FAILS",
        judgeButton="JUDGE",
        titleButton="TITLE",
        judgeFail="FAILED...",
        judgeDup="ALREADY JUDGED",
        resultHeading="TIME UP!",
        resultJudgeCount="JUDGES",
        resultBest="BEST",
        resultRetry="RETRY",
        resultTitle="TITLE",
        selfBest="YOUR BEST",
        newRecord="NEW RECORD!",
    ),
}


@dataclass(frozen=True)
class RulePage:
    title: str
    lines: tuple[str, ...]


# 既存 frontend/src/i18n/strings.ts の RULE_PAGES(5 ページ)をそのまま流用。
# 仕様書 §3.3 は「4 ページ構成」だが、正となる既存文言が 5 ページのため 5 ページとした
# (handoff の要判断参照)。
RULE_PAGES: Final[dict[Lang, tuple[RulePage, ...]]] = {
    "ja": (
        RulePage(
            title="どんな ゲーム?",
            lines=(
                "はこを つんで「はんてい」ボタン!",
                "うまく つめたら ポイント!",
                "1ぷんで たくさん あつめよう",
            ),
        ),
        RulePage(
            title="つみかた",
            lines=(
                "うえに いくほど ちいさく!",
                "おなじ おおきさは かさねない",
                "1つの とうに 3こまで",
            ),
        ),
        RulePage(
            title="うごかしかた",
            lines=(
                "うごかせるのは いちばんうえ の 1こ",
                "おけるのは からっぽ か",
                "じぶんより おおきい はこ の うえ",
            ),
        ),
        RulePage(
            title="クリア とは?",
            lines=(
                "うごかして ひだりと みぎを",
                "いれかえた かたちに できたら クリア!",
                "(さいしょから おなじ かたちでも 1こは うごかそう)",
            ),
        ),
        RulePage(
            title="ポイント",
            lines=(
                # 既存文言の乗算記号を保持する
                "ポイント = はこの かず × さいたん てすう",  # noqa: RUF001
                "むずかしい かたち ほど たかい!",
                "おなじ かたち(かがみうつしも)は 1かいだけ",
            ),
        ),
    ),
    "en": (
        RulePage(
            title="WHAT IS THIS GAME?",
            lines=(
                "Stack boxes and press JUDGE!",
                "A good layout earns points!",
                "Collect as many as you can in 1 minute.",
            ),
        ),
        RulePage(
            title="HOW TO STACK",
            lines=(
                "Smaller on top!",
                "Never two of the same size.",
                "Max 3 boxes per tower.",
            ),
        ),
        RulePage(
            title="HOW TO MOVE",
            lines=(
                "Move only the top box, one at a time.",
                "Put it on an empty tower,",
                "or on a bigger box.",
            ),
        ),
        RulePage(
            title='WHAT IS "CLEAR"?',
            lines=(
                "Move the boxes until left and right",
                "are swapped - that is a CLEAR!",
                "(Already mirrored? Still move one box.)",
            ),
        ),
        RulePage(
            title="POINTS",
            lines=(
                "Points = boxes x shortest moves.",
                "Harder layouts score higher!",
                "Each layout (mirrors too) counts only once.",
            ),
        ),
    ),
}

_current: Lang = DEFAULT_LANG


def current() -> Lang:
    return _current


def set_lang(lang: Lang) -> None:
    global _current
    _current = lang


def toggle() -> Lang:
    set_lang("en" if _current == "ja" else "ja")
    return _current


def msg() -> Messages:
    """現在の言語の辞書。"""
    return MESSAGES[_current]


def rule_pages() -> tuple[RulePage, ...]:
    return RULE_PAGES[_current]
