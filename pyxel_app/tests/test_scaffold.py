"""P1 の足場のテスト: ランタイム同梱物・フォント・main.py の sys.path 補完・サイト組み立て。"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_DIR.parent
RUNTIME = APP_DIR / "runtime"
BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_pyxel_site.py"


def _load_build_module() -> object:
    spec = importlib.util.spec_from_file_location("build_pyxel_site", BUILD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- ランタイム(仕様書 §2.3) -------------------------------------------------------


def test_runtime_has_required_files() -> None:
    for name in ("pyxel.js", "pyxel.css", "import_hook.py", "VERSION.md"):
        assert (RUNTIME / name).is_file(), name
    assert len(list((RUNTIME / "images").iterdir())) == 7
    wheels = list(RUNTIME.glob("pyxel-*-emscripten_*_wasm32.whl"))
    assert len(wheels) == 1


def test_pyxel_js_points_to_bundled_wheel() -> None:
    js = (RUNTIME / "pyxel.js").read_text(encoding="utf-8")
    wheel = next(RUNTIME.glob("pyxel-*-emscripten_*_wasm32.whl")).name
    assert f'const PYXEL_WHEEL_PATH = "{wheel}";' in js


def test_index_html_uses_local_runtime_not_cdn() -> None:
    html = (APP_DIR / "web" / "index.html").read_text(encoding="utf-8")
    assert 'src="runtime/pyxel.js"' in html
    assert 'href="runtime/pyxel.css"' in html
    assert "cdn.jsdelivr.net" not in html
    assert 'packages="pydantic"' in html
    assert "gamepad=" not in html


# --- 日本語フォント(仕様書 §3.6) ----------------------------------------------------


def _bdf_encodings(path: Path) -> set[int]:
    return {
        int(line.split()[1])
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.startswith("ENCODING ")
    }


def test_japanese_font_bundled_with_license() -> None:
    font = APP_DIR / "assets" / "umplus_j10r.bdf"
    assert font.is_file()
    assert (APP_DIR / "assets" / "LICENSE_umplus_j10r.txt").is_file()
    encodings = _bdf_encodings(font)
    # 「ハノイキューブ」と基本的なラテン文字が揃っている
    for ch in "ハノイキューブ":
        assert ord(ch) in encodings, ch
    assert {ord(c) for c in "Hanoi Cube0123456789"} <= encodings


# --- main.py(Pyxel 非依存の部分) -----------------------------------------------------


HAS_PYXEL = importlib.util.find_spec("pyxel") is not None


@pytest.mark.skipif(not HAS_PYXEL, reason="pyxel が未導入(macOS arm64 以外)")
def test_main_resolves_core_from_server_dir() -> None:
    """リポジトリから直接実行したとき ../server を sys.path に足して app.core が読める。"""
    code = (
        "import sys; sys.modules.pop('pyxel', None)\n"
        "import runpy; ns = runpy.run_path('main.py', run_name='not_main')\n"
        "print(ns['core_status']())"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=APP_DIR, capture_output=True, text=True, check=True
    )
    assert result.stdout.startswith("core OK (512 boards, LMS// -> 21pt)")


def test_main_fails_clearly_without_core(tmp_path: Path) -> None:
    shutil.copy2(APP_DIR / "main.py", tmp_path / "main.py")
    result = subprocess.run(
        [sys.executable, "main.py"], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "app.core が見つかりません" in result.stderr


# --- サイト組み立て(仕様書 §7.1) ------------------------------------------------------


@pytest.mark.skipif(not HAS_PYXEL, reason="pyxel が未導入(macOS arm64 以外)")
def test_build_site_produces_required_files() -> None:
    mod = _load_build_module()
    out = REPO_ROOT / "build" / "site-test"  # --out はリポジトリ内に限定される
    mod.build(out)  # type: ignore[attr-defined]
    assert mod.missing_files(out) == []  # type: ignore[attr-defined]
    assert (out / ".nojekyll").exists()
    import zipfile

    with zipfile.ZipFile(out / "hanoi_cube.pyxapp") as zf:
        names = set(zf.namelist())
    assert "hanoi_cube/main.py" in names
    assert "hanoi_cube/_core/app/core/data/precompute.json" in names
    assert "hanoi_cube/assets/umplus_j10r.bdf" in names
    # P2 の Pyxel 非依存層(main.py が import する。欠けると .pyxapp で ImportError)
    for module in (
        "board_state.py",
        "scene/__init__.py",
        "scene/layout.py",
        "scene/picking.py",
        "input/__init__.py",
        "input/drag.py",
    ):
        assert f"hanoi_cube/{module}" in names, module
    # ランタイム・テストは .pyxapp に入れない
    assert not any(n.startswith(("hanoi_cube/runtime/", "hanoi_cube/tests/")) for n in names)


def test_build_refuses_unsafe_out_dir(tmp_path: Path) -> None:
    mod = _load_build_module()
    for bad in (REPO_ROOT, APP_DIR, REPO_ROOT / "server" / "x", tmp_path):
        with pytest.raises(SystemExit):
            mod._check_out_dir(bad)  # type: ignore[attr-defined]
    # リポジトリ内の未作成ディレクトリは OK
    mod._check_out_dir(REPO_ROOT / "site-test-does-not-exist")  # type: ignore[attr-defined]


def test_build_refuses_existing_foreign_dir(tmp_path: Path) -> None:
    """生成物の印が無い既存ディレクトリは消さない。"""
    mod = _load_build_module()
    foreign = REPO_ROOT / "build" / "foreign-dir-for-test"
    foreign.mkdir(parents=True, exist_ok=True)
    try:
        with pytest.raises(SystemExit):
            mod._check_out_dir(foreign)  # type: ignore[attr-defined]
    finally:
        foreign.rmdir()


def test_missing_files_detects_absent_runtime(tmp_path: Path) -> None:
    mod = _load_build_module()
    (tmp_path / "index.html").write_text("")
    missing = mod.missing_files(tmp_path)  # type: ignore[attr-defined]
    assert "runtime/pyxel.js" in missing
    assert "hanoi_cube.pyxapp" in missing
