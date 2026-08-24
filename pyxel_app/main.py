"""Hanoi Cube Pyxel 版のエントリ。

P4 時点: タイトル(仮)→ ゲーム(3-2-1-GO、60 秒、JUDGE で判定・得点)→ リザルト(仮)。
画面は `screens/base.Screen` の実装で、`update()` が次の画面を返す(仕様書 §6.2)。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# --- `app.core` への経路を補う(仕様書 §2.2) ---------------------------------------
# `.pyxapp` 展開後は起動スクリプトのディレクトリしか sys.path に入らないため、
# ① パッケージ実行時: main.py と同階層の `_core/`(ビルド時に server/app/core をコピー)
# ② リポジトリから直接実行時: `../server`
# の順に、存在する方を追加する。
_HERE = Path(__file__).resolve().parent
for _candidate in (_HERE / "_core", _HERE.parent / "server"):
    if (_candidate / "app" / "core").is_dir():
        sys.path.insert(0, str(_candidate))
        break
else:
    raise SystemExit("app.core が見つかりません(_core/ または ../server が必要)")

import pyxel  # noqa: E402

import sfx  # noqa: E402
from app.core import precompute  # noqa: E402
from board_state import BoardState  # noqa: E402
from input.drag import DragController  # noqa: E402
from input.pointer import PointerDriver  # noqa: E402
from scene.board_scene import BoardScene  # noqa: E402
from screens import draw  # noqa: E402
from screens.base import Pointer, Screen  # noqa: E402
from screens.title import TitleScreen  # noqa: E402

WIDTH = 320
HEIGHT = 240
FPS = 60
FONT_PATH = str(_HERE / "assets" / "umplus_j10r.bdf")
SHOW_FPS = False  # P6 の計測用(True で右下に fps を出す)


class FpsMeter:
    """直近 1 秒の描画回数(§10 の 60fps 確認用)。"""

    def __init__(self) -> None:
        self.value = 0
        self._count = 0
        self._since = time.monotonic()

    def tick(self, now: float) -> None:
        self._count += 1
        if now - self._since >= 1.0:
            self.value = self._count
            self._count = 0
            self._since = now


class App:
    def __init__(self) -> None:
        # Esc は「タイトルへ」の補助キー(§3.1)なので終了キーにしない(終了は Q)
        pyxel.init(WIDTH, HEIGHT, title="Hanoi Cube", fps=FPS, quit_key=pyxel.KEY_NONE)
        pyxel.mouse(True)
        draw.setup_palette()  # 基調色 #438532。BoardScene(Shading)生成より前に行う
        sfx.setup()
        self.font = pyxel.Font(FONT_PATH)
        draw.set_font(self.font)  # 日本語 UI(§3.6)。各画面は draw.FONT で描く
        self.table = precompute.load_table()
        self.scene = BoardScene(pyxel.colors, WIDTH, HEIGHT)
        # タイトル中も盤面を背景に出すため、初期配置で結線しておく(ゲーム開始時に bind し直す)
        self.scene.bind(PointerDriver(DragController(BoardState.initial()), self.scene))
        self.screen: Screen = TitleScreen(self.table, self.scene)
        self.fps = FpsMeter()
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        if pyxel.btnp(pyxel.KEY_Q):
            pyxel.quit()
        now = time.monotonic()
        x, y = pyxel.mouse_x, pyxel.mouse_y
        pointer = Pointer(
            x, y, pyxel.btn(pyxel.MOUSE_BUTTON_LEFT), 0 <= x < WIDTH and 0 <= y < HEIGHT
        )
        next_screen = self.screen.update(pointer, now)
        if next_screen is not None:
            self.screen = next_screen

    def draw(self) -> None:
        now = time.monotonic()
        self.fps.tick(now)
        self.screen.draw(now)
        if SHOW_FPS:
            pyxel.text(WIDTH - 24, HEIGHT - 8, f"{self.fps.value:2d}fps", 13)


if __name__ == "__main__":
    App()
