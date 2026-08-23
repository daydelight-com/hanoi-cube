"""効果音(仕様書 §6.5)。Pyxel 内蔵のサウンド定義を使う薄いラッパー。

P3 で「配置」「失敗」、P4 で残り 5 種を暫定で定義した(音色の調整は P5)。
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
    # ボタン: 短いクリック音
    pyxel.sounds[Sfx.BUTTON].set("c4", "p", "5", "f", 4)
    # 判定成功: ファンファーレ風の上昇アルペジオ
    pyxel.sounds[Sfx.JUDGE_OK].set("c3e3g3c4e4g4", "s", "777766", "nnnnnf", 6)
    # 判定済み: 同じ音を 2 回(残念でも失敗でもない)
    pyxel.sounds[Sfx.JUDGED].set("a3ra3", "t", "666", "nnf", 8)
    # カウントダウン: 短いビープ(3, 2, 1 / GO は同じ音)
    pyxel.sounds[Sfx.COUNTDOWN].set("g3", "p", "6", "f", 8)
    # タイムアップ: 長めの下降
    pyxel.sounds[Sfx.TIMEUP].set("g3e3c3c3", "s", "7766", "nnnf", 14)
    _DEFINED.update(set(Sfx))


def play(sfx: Sfx) -> None:
    if sfx in _DEFINED:
        pyxel.play(CHANNEL, int(sfx))
