# 記録画面(cloud/record)

来場者がQRから開くプレイ記録のSPA(仕様 `docs/specification.md` §5.10)。
Firebase Hosting に静的デプロイし、Firestore Web SDK(lite)で `plays/{play_id}` を
1ドキュメント読み取って表示する。データ形は契約 [docs/contracts/firestore.md](../../docs/contracts/firestore.md) §1。

## 開発

```bash
npm install
npm run dev        # http://localhost:5173/records/demo でFirestoreなしのデモ表示
npm run check      # eslint + prettier + tsc + vitest(make check-cloud と同じ)
```

- `/records/demo` は同梱のデモデータを表示する(Firebase設定不要。ブースでの動作確認用)
- Firestoreエミュレータと繋ぐ場合(通し検証。手順は `docs/handoff/S12.md`):
  `VITE_FIREBASE_PROJECT_ID=demo-hanoi VITE_FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 npm run dev`

## ビルド・デプロイ

```bash
VITE_FIREBASE_PROJECT_ID=<本番プロジェクトID> VITE_FIREBASE_API_KEY=<WebAPIキー> npm run build
cd .. && firebase deploy --only firestore,hosting   # cloud/firebase.json(rewrite設定済み)
```

- 事前計算テーブルは `server/app/core/data/precompute.json` をビルド時に同梱する
  (リポジトリ相対import。写しは持たない)
- OGPは全プレイ共通の静的設定(`index.html`)
