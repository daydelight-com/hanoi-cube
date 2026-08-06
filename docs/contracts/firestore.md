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
      "points": 12,                   // 獲得点 = 箱数4 * 最短手数3。無得点は 0
      "min_moves": 3,                 // クリア可能時のみ。クリア不可は null
      "dup_of_seq": null,             // 重複時: 得点した元判定の seq。それ以外 null
      "tower_box_ids": [              // 判定時に塔にあった箱の個体(下から上)。表示専用
        ["large-1", "medium-1", "small-1"], [], ["large-2"]
      ]
    }
  ]
}
```

- `tower_box_ids` は記録画面の表示専用。サイズ列は `board` と一致する(cv-interface.md §3)。
  クリア条件2は箱の個体で判定する(ルールブック§5)ため、同サイズの箱を入れ替えただけの
  クリアは `board` だけでは初期状態と区別が付かない。個体を残して見分けられるようにする。
- 箱の座標は保存しない。最短手順の再生は個体を初期状態として `min_path` を順に適用すれば
  よい(動かすのは常に `from` 塔の最上段なので、個体は `size` + `from` から一意に定まる)。
- **判定・重複判定には個体を使わない。** 重複は円盤のサイズと並び(鏡像同一視)だけで
  決まる(ルールブック§6 / game-core-api.md §2)。

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
