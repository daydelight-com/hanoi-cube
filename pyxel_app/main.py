"""Hanoi Cube Pyxel 版のエントリ。

P1 時点ではサンプル c01 相当の回転キューブに、
`app.core` の import 確認(`core OK`)と日本語フォントの表示確認を加えたもの。
"""

from __future__ import annotations

import sys
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
from pyxel.cube import Camera, Mat4, Node, Shading, Vec3  # noqa: E402

from app.core import engine, precompute  # noqa: E402  (起動時に core を読めることの確認)

WIDTH = 320
HEIGHT = 240
FPS = 60
FONT_PATH = str(_HERE / "assets" / "umplus_j10r.bdf")
CUBE_COLORS = [8, 9, 10, 11, 12, 14]
CUBE_COUNT = len(CUBE_COLORS)
TITLE_JA = "ハノイキューブ"


def core_status() -> str:
    """`app.core` の読み込み状態を表す文字列(画面に表示する)。"""
    table = precompute.load_table()
    # judge() まで一度通して pydantic モデルが Pyodide 上でも動くことを確かめる
    judgement = engine.judge("LMS//", set(), set(), table)
    return f"core OK ({len(table.boards)} boards, LMS// -> {judgement.points}pt)"


class Cube(Node):
    def __init__(self, index: int) -> None:
        super().__init__()
        self.color = CUBE_COLORS[index]
        self.phase = index * 360.0 / CUBE_COUNT

    def on_update(self) -> None:
        frame = pyxel.frame_count
        orbit = self.phase + frame * 1.0
        position = Vec3(
            pyxel.cos(orbit) * 2.0,
            pyxel.sin(self.phase + frame * 2.0) * 0.5 + 0.4,
            pyxel.sin(orbit) * 2.0,
        )
        spin = Mat4.from_euler(Vec3(frame * 1.5, frame * 2.5, 0.0))
        self.transform = Mat4.from_translation(position) * spin

    def on_draw(self) -> None:
        self.box(Mat4.IDENTITY, Vec3(0.6, 0.6, 0.6), self.color)


class Scene(Node):
    def __init__(self) -> None:
        super().__init__()
        self.shading = Shading(pyxel.colors)
        self.shading.direction = Vec3(0.5, -1.5, -1.0).normalize()
        self.camera = Camera()
        self.camera.clear_color = 0
        self.camera.transform = Mat4.look_at(Vec3(0.0, 3.0, 4.0), Vec3.ZERO)
        for i in range(CUBE_COUNT):
            self.add_child(Cube(i))


class App:
    def __init__(self) -> None:
        pyxel.init(WIDTH, HEIGHT, title="Hanoi Cube", fps=FPS)
        self.font = pyxel.Font(FONT_PATH)
        self.status = core_status()
        self.scene = Scene()
        pyxel.run(self.update, self.draw)

    def update(self) -> None:
        if pyxel.btnp(pyxel.KEY_Q):
            pyxel.quit()
        self.scene.update()

    def draw(self) -> None:
        self.scene.draw(0, 0, pyxel.width, pyxel.height)
        pyxel.text(4, 4, self.status, 7)
        pyxel.text(4, 12, f"{pyxel.VERSION} / {FPS}fps", 13)
        pyxel.text(4, HEIGHT - 14, TITLE_JA, 7, self.font)
        pyxel.text(4, HEIGHT - 26, "Hanoi Cube (Pyxel Cube)", 7, self.font)


if __name__ == "__main__":
    App()
