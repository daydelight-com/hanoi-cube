"""効果音(仕様書 §6.5)。Pyxel 内蔵のサウンド定義を使う薄いラッパー。

P3 時点では「配置」「失敗」の 2 種のみ暫定で定義する。
残り 5 種の ID は予約だけしておき P5 で定義する。
`pyxel.init()` 後に `setup()` を一度呼ぶこと。
"""

from __future__ import annotations

from enum import IntEnum
from typing import Final

import pyxel

CHANNEL: Final = 3  # 効果音専用チャンネル(BGM は使わないが、将来のために末尾を使う)


class Sfx(IntEnum):
    """サウンド番号(`pyxel.sounds[n]`)。既存仕様 §5.12 の SFX 一覧の順。"""

    BUTTON = 0
    PLACE = 1
    FAIL = 2
    JUDGE_OK = 3
    JUDGED = 4
    COUNTDOWN = 5
    TIMEUP = 6


_DEFINED: set[Sfx] = set()


def setup() -> None:
    """サウンドを定義する(暫定)。未定義の音は `play()` で無視される。"""
    # 配置: 短い上昇音(スッと収まる感じ)
    pyxel.sounds[Sfx.PLACE].set("c3e3g3c4", "t", "7765", "nnnf", 5)
    # 失敗: 低い下降ブザー
    pyxel.sounds[Sfx.FAIL].set("e2c2", "s", "66", "nf", 12)
    _DEFINED.update({Sfx.PLACE, Sfx.FAIL})


def play(sfx: Sfx) -> None:
    if sfx in _DEFINED:
        pyxel.play(CHANNEL, int(sfx))
