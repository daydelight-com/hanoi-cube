# 契約: Firestore(firestore)

クラウド側データモデルとセキュリティルール。仕様の正: specification.md §3.2-6, §7.2, §8.2。
書き込みはブースMacの Admin SDK(Python, `server/app/cloud/`、S9)のみ。
読み取りは記録画面(`cloud/record/`)とランキング取得。

## 1. plays コレクション

ドキュメントID = `play_id`(ローカルSQLiteと同じUUID。QRのURLに使用、事前採番)。

```jsonc
// plays/{play_id}
{
  "player_name": "たろう",            // string, 1〜10文字
  "score": 120,                       // int
  "fail_count": 2,                    // int
  "played_at": "2026-08-21T10:00:00+09:00",  // string, ISO8601(タイムゾーン付き)。SQLiteと同表現
  "judgements": [                     // 判定履歴(本番のみ)。埋め込み配列(サブコレクションにしない)
    {
      "seq": 1,                       // 1始まり
      "board": "LMS//L",              // board.md の盤面文字列
      "elapsed_ms": 12345,            // GOからの経過時間
      "result": "scored",             // "scored" | "unclearable" | "duplicate_same" | "duplicate_mirror"
      "points": 9,                    // 無得点は 0
      "min_moves": 3,                 // クリア可能時のみ。クリア不可は null
      "dup_of_seq": null              // 重複時: 得点した元判定の seq。それ以外 null
    }
  ]
}
```

- アップロードは `set()` による全上書き(冪等。リトライで重複しない)。
- 記録画面は1ドキュメント読み取りだけで全表示できる。最短手順の再生は事前計算テーブル
  (game-core-api.md §3 の precompute.json を記録画面にも同梱)から board で引く。
- アップロード前にQRが読まれた場合、記録画面は「準備中」を表示する(ドキュメント不存在=準備中)。

## 2. ランキングクエリ

```
plays を orderBy(score, desc), orderBy(fail_count, asc), orderBy(played_at, asc) で全件取得
```

- 順位: スコア降順 → 失敗数昇順 → 先着順(played_at はISO8601文字列のため辞書順=時刻順)。
- 複合インデックス(firestore.indexes.json に定義): `score DESC, fail_count ASC, played_at ASC`。
- ローカル(SQLite)側も同一の順序規則で導出する。2日間累積・リセットなし。

## 3. セキュリティルール(cloud/firestore.rules)

```
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    match /plays/{playId} {
      allow read: if true;      // 記録画面・ランキングは誰でも読める
      allow write: if false;    // クライアント書き込み全面禁止(Admin SDKはルールを経由しない)
    }
    match /{document=**} {
      allow read, write: if false;
    }
  }
}
```

## 4. 記録画面のルーティング

- URL: `https://<Hosting>/records/{play_id}`。Hosting の rewrite で全パスを `index.html` へ(SPA解決)。
- OGPは全プレイ共通の静的設定(動的処理なし)。
