#!/usr/bin/env python
"""全512盤面の判定履歴を持つデモ用プレイ記録を作り、Firestore の plays に投入する。

判定履歴は「得点降順 → 鏡像(重複・0点) → クリア不可(失敗)」の順に並ぶ。

JSONの確認だけ(投入しない):

    cd server && uv run python ../scripts/generate_all_patterns_play.py \
        --out ../output/all_patterns_play.json

本番Firestoreへ投入(確認プロンプトで "yes"):

    cd server && HANOI_FIREBASE_CREDENTIALS=../service-account.json \
        uv run python ../scripts/generate_all_patterns_play.py

エミュレータ相手の検証:

    cd server && FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 HANOI_FIREBASE_PROJECT=demo-hanoi \
        uv run python ../scripts/generate_all_patterns_play.py

本体は server/app/cloud/demo_play.py(テスト・型検査対象)。ここは起動用の薄い入口のみ。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))

from app.cloud.demo_play import run_cli

if __name__ == "__main__":
    sys.exit(run_cli())
