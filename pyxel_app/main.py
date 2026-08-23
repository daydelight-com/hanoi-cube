"""Hanoi Cube Pyxel 版のエントリ。

P3 時点: 3D 盤面(`scene/board_scene.py`)にマウス / タッチ入力を流し、9 箱を塔・待機エリア間で
ドラッグ&ドロップできる。判定・得点・画面遷移は P4 以降。
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
from app.core import engine, precompute  # noqa: E402  (起動時に core を読めることの確認)
from board_state import BoardState  # noqa: E402
from input.drag import DragController, DropOutcome  # noqa: E402
from input.pointer import PointerDriver  # noqa: E402
from scene import layout  # noqa: E402
from scene.board_scene import BoardScene  # noqa: E402

WIDTH = 320
HEIGHT = 240
FPS = 60
MAX_DT = 0.1  # 処理落ち・タブ非表示からの復帰で平滑化が飛ばないよう dt を上限で切る
FONT_PATH = str(_HERE / "assets" / "umplus_j10r.bdf")
TITLE_JA = "ハノイキューブ"


def core_status() -> str:
    """`app.core` の読み込み状態を表す文字列(画面に表示する)。"""
    table = precompute.load_table()
    # judge() まで一度通して pydantic モデルが Pyodide 上でも動くことを確かめる
    judgement = engine.judge("LMS//", set(), set(), table)
    return f"core OK ({len(table.boards)} boards, LMS// -> {judgement.points}pt)"


class FpsMeter:
    """直近 1 秒の描画回数(§10 の 60fps 確認用。画面に表示する)。"""

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
        pyxel.init(WIDTH, HEIGHT, title="Hanoi Cube", fps=FPS)
        pyxel.mouse(True)
        sfx.setup()
        self.font = pyxel.Font(FONT_PATH)
        self.status = core_status()
        self.board = BoardState.initial()
        self.scene = BoardScene(pyxel.colors, WIDTH, HEIGHT)
        self.driver = PointerDriver(DragController(self.board), self.scene)
        self.scene.bind(self.driver)
        self.last_outcome: DropOutcome | None = None
        self.fps = FpsMeter()
        self.debug = False  # D キー: ピッキング計算の投影点を十字で重ねる(描画とのずれ確認用)
        self._last = time.monotonic()
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        if pyxel.btnp(pyxel.KEY_Q):
            pyxel.quit()
        if pyxel.btnp(pyxel.KEY_D):
            self.debug = not self.debug
        now = time.monotonic()
        dt = min(now - self._last, MAX_DT)
        self._last = now
        x, y = pyxel.mouse_x, pyxel.mouse_y
        inside = 0 <= x < WIDTH and 0 <= y < HEIGHT
        outcome = self.driver.feed(x, y, pyxel.btn(pyxel.MOUSE_BUTTON_LEFT), inside)
        if outcome is not None:
            self.last_outcome = outcome
            sfx.play(sfx.Sfx.PLACE if outcome.placed else sfx.Sfx.FAIL)
        self.scene.sync(dt)

    def draw(self) -> None:
        self.fps.tick(time.monotonic())
        self.scene.draw_to(0, 0, pyxel.width, pyxel.height)
        pyxel.text(4, 4, self.status, 7)
        pyxel.text(4, 12, f"{pyxel.VERSION} / {self.fps.value}fps", 13)
        pyxel.text(4, 20, self.board.board_string() or "//", 7)
        if self.last_outcome is not None:
            o = self.last_outcome
            reason = f" {o.reason.value}" if o.reason is not None else ""
            pyxel.text(4, 28, f"{o.box_id}: {o.result.value}{reason}", 7)
        if self.debug:
            self.draw_debug()
        pyxel.text(4, HEIGHT - 14, TITLE_JA, 7, self.font)

    def draw_debug(self) -> None:
        w, h = layout.MAT_SIZE_MM
        points = [layout.mat_to_world(x, y) for x in (0.0, w) for y in (0.0, h)]
        points += [layout.tower_position(t) for t in ("A", "B", "C")]
        points += [layout.box_center(self.board, b) for b in self.board]
        for p in points:
            s = self.scene.project(p)
            if s is not None:
                x, y = int(s[0]), int(s[1])
                pyxel.line(x - 3, y, x + 3, y, 8)
                pyxel.line(x, y - 3, x, y + 3, 8)
        pyxel.text(4, 36, f"mouse {pyxel.mouse_x},{pyxel.mouse_y}", 7)


if __name__ == "__main__":
    App()
