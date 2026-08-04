# 契約: WebSocketメッセージ(ws-messages)

エンドポイント(仕様§8.1): `/ws/display`(ディスプレイ)、`/ws/controller`(iPad)。
すべてのメッセージは `{"type": string, "payload": object}` のJSON。未知の type は受信側で無視する。
画面ID・遷移の定義は [screens.md](screens.md)、盤面型は [board.md](board.md) / [cv-interface.md](cv-interface.md)。

- 実装の写し: Python `server/app/api/messages.py`(S2)、TS `frontend/src/contracts/ws.ts`(S0で作成済み)。乖離したら本契約が正。
- 切断→再接続時、サーバーは接続直後に `snapshot` を送る(途中復帰)。クライアントは常に `snapshot` で全状態を上書きできること。

## 1. サーバー → ディスプレイ(/ws/display)

| type | 送信タイミング | payload |
|---|---|---|
| `snapshot` | 接続直後・再接続直後 | `{ screen, ctx, lang }`(§3) |
| `screen` | 画面遷移のたび | `{ screen, ctx }` |
| `lang` | 言語切替・リセット時 | `{ lang: "ja" \| "en" }` |
| `boxes` | 約30fps(全画面で常時) | `{ t_ms, boxes: BoxObservation[] }`(cv-interface.md §2 と同型) |
| `board` | 確定盤面の変化時 | `{ t_ms, towers, board, legal, violations, staging_box_ids }`(cv-interface.md §3 と同型) |
| `countdown` | 本番開始演出(1秒ごと) | `{ value: "3" \| "2" \| "1" \| "go" }` |
| `timer` | 本番中1秒ごと+タイムアップ時 | `{ remaining_ms: number }`(残り10秒未満の強調はクライアント判断) |
| `judge` | 判定実行のたび(練習・本番) | §2 の Judge |
| `name` | 名前入力の変化のたび | `{ text: string }`(ディスプレイの入力欄へミラー) |
| `ranking` | ランキング表示時・データ更新時 | `{ entries: RankingEntry[], highlight_play_id: string \| null }` |
| `sfx` | 効果音トリガー | `{ id: SfxId }`(§4) |

## 2. 型定義

```jsonc
// Judge(判定結果)
{
  "seq": 3,                        // このプレイ何回目の判定か(1始まり)
  "result": "scored",              // "scored" | "unclearable" | "duplicate_same" | "duplicate_mirror"
  "points": 12,                    // 獲得点 = 箱数4 * 最短手数3(scored 以外は 0)
  "min_moves": 3,                  // クリア可能時の最短手数、unclearable は null
  "board": "LMS//L",               // 判定対象の盤面
  "total_score": 21,               // 判定後の合計スコア
  "fail_count": 1                  // 判定後の失敗数
}

// RankingEntry
{
  "rank": 1, "name": "たろう", "score": 120, "fail_count": 2,
  "play_id": "uuid", "played_at": "2026-08-21T10:00:00+09:00"
}

// result 画面 / qr 画面のデータは screens.md の ctx として screen / snapshot に乗せる
```

## 3. snapshot / screen の payload

```jsonc
{ "screen": "game_play", "ctx": { ... }, "lang": "ja" }   // snapshot(lang付き)
{ "screen": "game_play", "ctx": { ... } }                  // screen
```

`screen` は screens.md の画面ID。`ctx` は画面ごとの表示データ(screens.md §3 に画面別の ctx 型を定義)。

## 4. SfxId(仕様§5.12)

`cursor` `decide` `back` `count` `go` `judge_success` `judge_fail` `judge_dup` `tick10`
`timeup` `rank_tick` `fanfare` `key_touch` `pad_button` `pad_flash`

- 効果音はイベントに付随して確定的に決まるものが多い(判定結果・画面遷移)。クライアントは
  `judge` / `screen` 等から自律的に鳴らしてよいが、サーバーが `sfx` を明示送信した場合はそれに従う。
  どちらで鳴らすかの最終決定は S6(効果音セッション)で行い、本契約の表に追記する。

## 5. サーバー → iPad(/ws/controller)

| type | 送信タイミング | payload |
|---|---|---|
| `snapshot` | 接続直後 | `{ screen, lang, input_mode, name_text }` |
| `input_mode` | リザルト入退場・入力ボタン・完了時 | `{ mode: "buttons" \| "name", name_text: string }`(name時は現在値でフィールド初期化) |
| `lang` | 言語切替時 | `{ lang: "ja" \| "en" }`(プレースホルダー等の文言用) |
| `sfx` | 効果音トリガー | `{ id: SfxId }`(iPadスピーカーで再生。`pad_button` は押下ローカル再生でも可) |
| `flash` | 判定実行時(本番・練習) | `{ result: "scored" \| "failed" \| "duplicate" }`(画面全体フラッシュ演出+`pad_flash`音) |

## 6. iPad → サーバー(/ws/controller)

| type | 送信タイミング | payload |
|---|---|---|
| `button` | ボタン押下時 | `{ button: "left" \| "right" \| "enter" }`(意味づけはサーバーの状態機械が解釈) |
| `name_text` | 名前入力の変化のたび | `{ text: string }`(クライアントで10文字に切り詰めて送る。サーバーでも検証) |
| `name_done` | ソフトウェアキーボードの完了 | `{}`(サーバーは `input_mode: buttons` を返す) |

- ディスプレイ→サーバー方向のメッセージはない(ディスプレイは表示専用)。
  開発時のキーボード操作は `/controller` を同一Macで開くか、モックCLIを使う。
- `/ws/admin`(管理画面)は S10 で本契約に追記する。
