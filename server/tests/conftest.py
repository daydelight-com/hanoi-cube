"""テスト共通設定。

開発者のシェルで HANOI_* 環境変数(実CV切替等)が設定されていても、
テストが影響を受けないよう毎テストで隔離する。
"""

from __future__ import annotations

import os

import pytest

# app.cv.layout はモジュール読み込み時に HANOI_MAT_SIZE を評価するため、
# テストモジュールの import より前(conftest 読み込み時)に外して既定レイアウトに固定する
os.environ.pop("HANOI_MAT_SIZE", None)

_ISOLATED_ENV_VARS = [
    "HANOI_CV",
    "HANOI_CV_CAMERA",
    "HANOI_CV_VIDEO",
    "HANOI_CV_WIDTH",
    "HANOI_CV_HEIGHT",
    "HANOI_TAG_MASTER",
    "HANOI_MOCK_API",
    "HANOI_MAT_SIZE",
]


@pytest.fixture(autouse=True)
def _isolate_hanoi_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ISOLATED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
