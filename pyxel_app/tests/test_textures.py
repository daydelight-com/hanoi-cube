"""scene.textures と生成済みアセット(assets/textures/)のテスト(pyxel がある環境のみ)。

生成スクリプト(scripts/make_pyxel_textures.py)の出力が壊れていないこと
(存在・寸法・palette.json との整合)と、読み込み・パレット拡張・縮退経路を確かめる。
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Iterator
from pathlib import Path

import pytest

HAS_PYXEL = importlib.util.find_spec("pyxel") is not None
pytestmark = pytest.mark.skipif(not HAS_PYXEL, reason="pyxel が未導入(macOS arm64 以外)")


@pytest.fixture(autouse=True)
def _restore_palette() -> Iterator[None]:
    """テストがグローバルパレットを伸ばすので、終了時に元へ戻す。"""
    import pyxel

    saved = list(pyxel.colors)
    yield
    pyxel.colors[:] = saved


def assets_dir() -> Path:
    from scene.textures import TEXTURES_DIR

    return TEXTURES_DIR


def test_generated_assets_exist_with_expected_sizes() -> None:
    import pyxel

    from scene.textures import BOX_FILES, MAT_FILE, PALETTE_FILE

    directory = assets_dir()
    for name in BOX_FILES.values():
        image = pyxel.Image.from_image(str(directory / name))
        assert (image.width, image.height) == (64, 64), name
    mat = pyxel.Image.from_image(str(directory / MAT_FILE))
    # マット実寸 420x297mm(layout.MAT_SIZE_MM)と同じ縦横比
    assert mat.width / mat.height == pytest.approx(420 / 297, rel=0.02)
    colors = json.loads((directory / PALETTE_FILE).read_text())["colors"]
    assert colors and all(0 <= c <= 0xFFFFFF for c in colors)
    assert len(set(colors)) == len(colors)


def test_extend_palette_appends_once_and_is_idempotent() -> None:
    import pyxel

    from scene.textures import PALETTE_FILE, extend_palette

    base = list(pyxel.colors)
    extend_palette()
    extended = list(pyxel.colors)
    palette = json.loads((assets_dir() / PALETTE_FILE).read_text())["colors"]
    assert extended[: len(base)] == base  # 既存 16 色(UI が番号参照)は動かさない
    assert set(palette) <= set(extended)
    extend_palette()
    assert list(pyxel.colors) == extended  # 2 回目は何も追加しない


def test_load_returns_all_textures_quantized_losslessly() -> None:
    import pyxel

    from scene.textures import PALETTE_FILE, load

    base = set(pyxel.colors)
    textures = load()
    assert set(textures.boxes) == {"L", "M", "S"}
    assert textures.mat is not None
    palette = set(json.loads((assets_dir() / PALETTE_FILE).read_text())["colors"])
    colors = list(pyxel.colors)
    images = [*textures.boxes.values(), textures.mat]
    for image in images:
        step = max(1, image.width // 16)
        for y in range(0, image.height, step):
            for x in range(0, image.width, step):
                # 量子化は palette.json の色への完全一致になっている(基底 16 色も許容)
                assert colors[image.pget(x, y)] in palette | base


def test_load_without_assets_falls_back_to_empty(tmp_path: Path) -> None:
    import pyxel

    from scene.textures import load

    before = list(pyxel.colors)
    textures = load(tmp_path)
    assert textures.boxes == {} and textures.mat is None
    assert list(pyxel.colors) == before


def test_board_scene_applies_textures_to_nodes() -> None:
    import pyxel

    from board_state import BoardState, size_of
    from input.drag import DragController
    from input.pointer import PointerDriver
    from scene.board_scene import BoardScene
    from scene.textures import Textures, load

    textures = load()
    scene = BoardScene(list(pyxel.colors), 320, 240, textures)
    scene.bind(PointerDriver(DragController(BoardState.initial()), scene))
    assert scene.mat.image is textures.mat
    for box_id, node in scene.boxes.items():
        assert node.image is textures.boxes[size_of(box_id)], box_id

    # テクスチャなしは従来どおり単色(画像 None)に縮退する
    plain = BoardScene(list(range(16)), 320, 240)
    plain.bind(PointerDriver(DragController(BoardState.initial()), plain))
    assert plain.mat.image is None
    assert all(node.image is None for node in plain.boxes.values())
    assert plain.textures == Textures()
