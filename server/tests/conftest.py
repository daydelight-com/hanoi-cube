"""テスト共通設定。

開発者のシェルで HANOI_* 環境変数(実CV切替等)が設定されていても、
テストが影響を受けないよう毎テストで隔離する。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from app.cloud import uploader

# app.cv.layout はモジュール読み込み時に HANOI_MAT_SIZE を評価する。テストのレイアウト
# 前提値(塔x=150/300/450 等)は 600x400 で書かれているため、テストモジュールの import より
# 前(conftest 読み込み時)に 600x400 へ固定する(既定は A3=420x297)
_TEST_MAT_SIZE = "600x400"
os.environ["HANOI_MAT_SIZE"] = _TEST_MAT_SIZE

_ISOLATED_ENV_VARS = [
    "HANOI_CV",
    "HANOI_CV_CAMERA",
    "HANOI_CV_VIDEO",
    "HANOI_CV_WIDTH",
    "HANOI_CV_HEIGHT",
    "HANOI_TAG_MASTER",
    "HANOI_MOCK_API",
    "HANOI_FIREBASE_CREDENTIALS",
    "HANOI_FIREBASE_PROJECT",
    "FIRESTORE_EMULATOR_HOST",
    "GOOGLE_APPLICATION_CREDENTIALS",
]


@pytest.fixture(autouse=True)
def _isolate_hanoi_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ISOLATED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # 既定は実CV(カメラ必須)になったため、テストでは常にモックCVを明示する
    monkeypatch.setenv("HANOI_CV", "mock")
    # create_app() を使うテストがディスク上のDBを作らないようメモリDBに固定
    monkeypatch.setenv("HANOI_DB_PATH", ":memory:")
    # CVワーカー等の子プロセスは環境変数からレイアウトを再評価するため、
    # 削除ではなくテスト用寸法を明示的に継承させる
    monkeypatch.setenv("HANOI_MAT_SIZE", _TEST_MAT_SIZE)
    # 開発機のリポジトリ直下に実在する service-account.json(既定の自動検出先)が
    # テストに影響しないよう、存在しないパスへ差し替える
    monkeypatch.setattr(
        uploader,
        "default_credentials_path",
        lambda: Path("/nonexistent/service-account.json"),
    )
