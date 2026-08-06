# 契約: WebSocketメッセージ(ws-messages)

エンドポイント(仕様§8.1): `/ws/display`(ディスプレイ)、`/ws/controller`(iPad)。
すべてのメッセージは `{"type": string, "payload": object}` のJSON。未知の type は受信側で無視する。
画面ID・遷移の定義は [screens.md](screens.md)、盤面型は [board.md](board.md) / [cv-interface.md](cv-interface.md)。

- 実装の写し: Python `server/app/api/messages.py`(S2)、TS `frontend/src/contracts/ws.ts`(S0で作成済み)。乖離したら本契約が正。
- 切断→再接続時、サーバーは接続直後に `snapshot` を送る(途中復帰)。クライアントは常に `snapshot` で全状態を上書きできること。

## 1. サーバー → ディスプレイ(/ws/display)

| type | 送信タイミング | payload |
|---|---|---|
| `snapshot` | 接続直後・再接続直後 | `{ screen, ctx, lang, board }`(§3。board = 最新の確定盤面) |
| `screen` | 画面遷移のたび | `{ screen, ctx }` |
| `lang` | 言語切替・リセット時 | `{ lang: "ja" \| "en" }` |
| `boxes` | 約30fps(全画面で常時) | `{ t_ms, boxes: BoxObservation[] }`(cv-interface.md §2 と同型) |
| `board` | 確定盤面の変化時 | `{ t_ms, towers, board, legal, violations, staging_box_ids, tower_box_ids }`(cv-interface.md §3 と同型。`kind` のみ除く) |
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
// snapshot: lang と最新の確定盤面(board メッセージと同型)を含む。
// 静止盤面のまま再接続しても board を待たずに全状態を復元できるようにする
{ "screen": "game_play", "ctx": { ... }, "lang": "ja",
  "board": { "t_ms": 0, "towers": ["", "", ""], "board": "//", "legal": true,
             "violations": [], "staging_box_ids": [ ... ] } }   // 未確定なら null
{ "screen": "game_play", "ctx": { ... } }                        // screen
```

`screen` は screens.md の画面ID。`ctx` は画面ごとの表示データ(screens.md §3 に画面別の ctx 型を定義)。

## 4. SfxId(仕様§5.12)

`cursor` `decide` `back` `count` `go` `judge_success` `judge_fail` `judge_dup` `tick10`
`timeup` `rank_tick` `fanfare` `key_touch` `pad_button` `pad_flash`

- **発火方式(S6で確定)**: 全効果音を**クライアント自律発火**とする。判定・画面遷移・タイマーは
  既存メッセージ(`judge` / `screen` / `countdown` / `timer` / `name` / `lang` / `flash`)から
  確定的に導出できるため、サーバーは現状 `sfx` を送信しない。`sfx` メッセージは将来の
  上書きチャネルとして契約に残し、クライアントは受信したら無条件に再生する。
  ガードを満たさない操作はサーバーが何も送らないため、音も自然に出ない(screens.md §3 注記)。

| SfxId | 再生側 | 発火トリガー(クライアント自律) |
|---|---|---|
| `cursor` | display | `screen` 受信で同一画面の focus / page / selection(非null)が変化。mode_select 中の `lang` 受信(言語トグル) |
| `decide` | display | `screen` 受信での前進遷移(idle_title→mode_select、mode_select→rule_dialog/practice、practice→rule_dialog、result→ranking、ranking→qr、qr→idle_title)、result の input_mode 変化(入力⇄完了) |
| `back` | display | `screen` 受信での後退遷移(rule_dialog→呼び出し元、practice→mode_select) |
| `count` | display | `countdown` 受信(value 3/2/1) |
| `go` | display | `countdown` 受信(value go。GO! のクライアント表示と同時) |
| `judge_success` | display | `judge` 受信(result=scored。points に応じて豪華に) |
| `judge_fail` | display | `judge` 受信(result=unclearable) |
| `judge_dup` | display | `judge` 受信(result=duplicate_same / duplicate_mirror) |
| `tick10` | display | `timer` 受信(0 < remaining_ms < 10000) |
| `timeup` | display | `timer` 受信(remaining_ms ≦ 0) |
| `rank_tick` | display | idle_ranking のせり上がり演出(クライアントタイマー。1行=1秒) |
| `fanfare` | display | 同演出の1位到達時(クライアントタイマー) |
| `key_touch` | display | `name` 受信で text が変化(ミラー表示と同時) |
| `pad_button` | controller | ボタン押下のローカル再生(かんりょうボタン含む。§5 注記の通り) |
| `pad_flash` | controller | `flash` 受信(フラッシュ演出と同時) |

- mode_select→game_countdown の遷移は `decide` を鳴らさない(直後の `count`「3」が
  フィードバックを兼ねる)。game_countdown→game_play は `go`、game_play→result は
  `timeup` が代替するため遷移音なし。idle_title⇄idle_ranking はタイムアウト遷移と
  区別できないため無音。

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
