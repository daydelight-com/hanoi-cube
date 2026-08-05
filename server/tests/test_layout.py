"""layout.py のマット寸法導出のテスト。

layout はモジュール読み込み時に HANOI_MAT_SIZE を評価する(conftest がテスト全体を
600x400 に固定している)ため、既定値(A3)や別寸法の検証はサブプロセスで行う。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parent.parent

_DUMP_CODE = """
import json
import app.cv.layout as l
print(json.dumps({
    "mat": l.MAT_SIZE_MM,
    "tower_x": l.TOWER_X_MM,
    "tower_y": l.TOWER_Y_MM,
    "staging_y_max": l.STAGING_Y_MAX_MM,
    "tags": {str(k): v for k, v in l.MAT_TAG_CENTERS_MM.items()},
}))
"""


def _load_layout(mat_size: str | None) -> dict[str, object]:
    env = {k: v for k, v in os.environ.items() if k != "HANOI_MAT_SIZE"}
    if mat_size is not None:
        env["HANOI_MAT_SIZE"] = mat_size
    out = subprocess.run(
        [sys.executable, "-c", _DUMP_CODE],
        cwd=_SERVER_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    result: dict[str, object] = json.loads(out.stdout)
    return result


def test_default_mat_size_is_a3() -> None:
    layout = _load_layout(None)
    assert layout["mat"] == [420.0, 297.0]
    assert layout["tower_x"] == {"A": 105.0, "B": 210.0, "C": 315.0}
    assert layout["tower_y"] == 297.0 * 0.7
    # 待機帯に最大箱(75mm)が収まる
    staging_y_max = layout["staging_y_max"]
    assert isinstance(staging_y_max, float)
    assert staging_y_max >= 75.0
    # 四隅タグは各辺から30mm内側
    assert layout["tags"] == {
        "200": [30.0, 267.0],
        "201": [390.0, 267.0],
        "202": [390.0, 30.0],
        "203": [30.0, 30.0],
    }


def test_env_override_mat_size() -> None:
    layout = _load_layout("600x400")
    assert layout["mat"] == [600.0, 400.0]
    assert layout["tower_x"] == {"A": 150.0, "B": 300.0, "C": 450.0}
    assert layout["tower_y"] == 280.0
