"""sfx のテスト(pyxel がある環境のみ。`pyxel.init()` はせず play / sounds を差し替える)。"""

from __future__ import annotations

import importlib.util

import pytest

HAS_PYXEL = importlib.util.find_spec("pyxel") is not None
pytestmark = pytest.mark.skipif(not HAS_PYXEL, reason="pyxel が未導入(macOS arm64 以外)")


class _Sound:
    def __init__(self) -> None:
        self.args: tuple[object, ...] | None = None

    def set(self, *args: object) -> None:
        self.args = args


def test_setup_defines_all_seven_and_play_ignores_undefined(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import pyxel

    import sfx

    sounds = [_Sound() for _ in range(8)]
    played: list[tuple[int, int]] = []
    monkeypatch.setattr(pyxel, "sounds", sounds)
    monkeypatch.setattr(pyxel, "play", lambda ch, snd: played.append((ch, snd)))
    monkeypatch.setattr(sfx, "_DEFINED", set())

    sfx.play(sfx.Sfx.PLACE)  # setup 前は無視
    assert played == []
    sfx.setup()
    assert all(sounds[s].args is not None for s in sfx.Sfx)
    sfx.play(sfx.Sfx.PLACE)
    sfx.play(sfx.Sfx.FAIL)
    sfx.play(sfx.Sfx.JUDGE_OK)
    assert played == [(sfx.CHANNEL, 1), (sfx.CHANNEL, 2), (sfx.CHANNEL, 3)]
    monkeypatch.setattr(sfx, "_DEFINED", {sfx.Sfx.PLACE})
    sfx.play(sfx.Sfx.TIMEUP)  # 未定義は無視
    assert len(played) == 3
    # 既存仕様 §5.12 の順で 7 種
    assert [s.value for s in sfx.Sfx] == list(range(7))
