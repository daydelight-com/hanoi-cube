#!/usr/bin/env python
"""本番開始前にプレイデータを初期化する(ローカルSQLite削除+Firestore plays 全削除)。

必ずサーバーを停止してから実行する(手順は docs/operations.md)。

実行方法(server の uv 環境に firebase-admin が入っている):

    cd server && HANOI_FIREBASE_CREDENTIALS=../service-account.json \
        uv run python ../scripts/reset_plays.py

エミュレータ相手の検証:

    cd server && FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 HANOI_FIREBASE_PROJECT=demo-hanoi \
        uv run python ../scripts/reset_plays.py

本体は server/app/cloud/reset.py(テスト・型検査対象)。ここは起動用の薄い入口のみ。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from app.cloud.reset import run_cli

if __name__ == "__main__":
    sys.exit(run_cli())
