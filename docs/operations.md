# 運用手順: 本番リセット(プレイデータの開始前初期化)

開発・検証も本番と同じストア(ローカル `server/output/plays.sqlite3` と Firestore の
`plays` コレクション)に書く運用のため(S12後のユーザー決定)、**本番開始直前に一度だけ**
`scripts/reset_plays.py` で両方をセットで初期化する。

- **リセットするのは開発→本番の切り替え時の1回のみ。** 2日目の朝はリセットしない
  (仕様§3.2-2: ランキングは2日間累積・リセットなし)。
- **片側だけの削除は禁止。** SQLite だけ残すと開発プレイがランキングに出続け、その QR は
  永遠に「準備中」になる。スクリプトは Firestore 未構成なら SQLite にも手を付けずに
  エラー終了する。
- Firestore の削除はクライアントからはルールで禁止(firestore.md §3)のため、
  ブースMacのサービスアカウント鍵による Admin SDK 経由でのみ可能。

## 手順(必ずこの順)

1. **サーバー停止**(`make dev` / uvicorn を Ctrl-C で終了)。
   起動中に DB ファイルを消しても、開いているプロセスが古いデータを持ち続けるため不可。
2. **リセット実行**(リポジトリルートに本番の `service-account.json` がある前提):

   ```bash
   cd server && HANOI_FIREBASE_CREDENTIALS=../service-account.json uv run python ../scripts/reset_plays.py
   ```

   削除対象(SQLite のプレイ数・Firestore のドキュメント数と削除先)が表示されるので、
   内容を確認して `yes` を入力する。`yes` 以外を入力すれば何も消さずに中止する。
3. **サーバー起動**(通常の本番起動手順)。SQLite のスキーマは起動時に自動作成される。
   アップロードキューも SQLite 内にあるため、リセット後に開発プレイが本番 Firestore へ
   送られる事故は起きない。

`HANOI_DB_PATH` を変えてサーバーを運用している場合は、スクリプトにも同じ値を
渡す(同じ cwd で実行するか `--db` で絶対パスを指定)。

## 途中失敗時のリカバリ

削除順は SQLite → Firestore。Firestore 側で失敗しても残るのは「SQLite だけ消えた」状態で、
ローカルランキングには影響しない。**原因(ネットワーク・認証)を解消して再実行**すれば
残りが削除されて完了する(再実行は安全)。

## エミュレータでの検証(リハーサル)

```bash
# 1. エミュレータ起動(別ターミナル)
cd cloud && firebase emulators:start --only firestore --project demo-hanoi

# 2. リセット実行
cd server && FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 HANOI_FIREBASE_PROJECT=demo-hanoi \
  uv run python ../scripts/reset_plays.py
```

検証時のサーバー・記録画面の起動構成は docs/handoff/S12.md「次セッションへの注意」を参照。
自動テストは `server/tests/test_reset.py`(セット削除の担保・確認プロンプト)。
