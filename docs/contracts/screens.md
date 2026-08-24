# 契約: 画面IDと遷移表(screens)

specification.md §5 の機械可読版。状態機械(`server/app/state/`、S2)はこの表を実装し、
遷移表の全行をテストで網羅する(品質ゲート)。

## 1. 画面ID

| screen | 仕様 | 備考 |
|---|---|---|
| `idle_title` | §5.2 待機(タイトル) | **入場時に言語を ja にリセット** |
| `idle_ranking` | §5.2 待機(ランキング) | 全件を1位が最上段の並びでせり上がり表示(最後に1位で静止) |
| `mode_select` | §5.3 モード選択 | ctx.focus で選択位置を持つ |
| `rule_dialog` | §5.4 ルールダイアログ | ctx.from で呼び出し元を持つモーダル(独立した状態として扱う) |
| `practice` | §5.5 練習 | 制限時間なし。記録・ランキングに残らない |
| `game_countdown` | §5.6 本番(3,2,1,GO) | 判定不可。箱ストリームは動く |
| `game_play` | §5.6 本番(計測中) | 1:00 カウントダウン |
| `result` | §5.7 リザルト(名前入力) | 入場時に iPad を name 入力モードへ |
| `ranking` | §5.8 ランキング | 直前プレイをハイライト |
| `qr` | §5.9 QR | URLは事前採番(play_id) |

管理画面 `/admin`(§5.11)はこの状態機械の外(S10)。記録画面(§5.10)はクラウドで独立。

## 2. イベント

- `left` / `right` / `enter` — iPadボタン(ws-messages.md §6)。表にない組は**無視**(無効ボタン。テスト対象)
- `timeout:<名前>` — サーバー内タイマー
- `box_moved` — CVが箱の移動を検出(practice の選択解除用)
- `name_text` / `name_done` — 名前入力(result のみ)

## 3. 遷移表

| # | 状態 | イベント | ガード | アクション | 次状態 |
|---|---|---|---|---|---|
| 1 | idle_title | timeout:title(5s) | | | idle_ranking |
| 2 | idle_title | enter | | | mode_select |
| 3 | idle_ranking | timeout:ranking(1位表示+3s) | | | idle_title |
| 4 | idle_ranking | enter | | | idle_title |
| 5 | mode_select | left / right | | focus移動(rules→practice→game→lang。端はループする。S5で確定) | mode_select |
| 6 | mode_select | enter | focus=rules | | rule_dialog(from=mode_select, page=0) |
| 7 | mode_select | enter | focus=practice | スコア等を初期化 | practice |
| 8 | mode_select | enter | focus=game | play_id 採番、スコア初期化 | game_countdown |
| 9 | mode_select | enter | focus=lang | lang トグル+全体配信 | mode_select |
| 10 | rule_dialog | left / right | | ページ移動(クランプ) | rule_dialog |
| 11 | rule_dialog | enter | | 閉じる | ctx.from の画面 |
| 12 | practice | left / right | | 選択状態を有効化し back⇄help をfocus移動 | practice |
| 13 | practice | box_moved | 選択状態 | 選択状態を解除 | practice |
| 14 | practice | enter | 選択=back | | mode_select |
| 15 | practice | enter | 選択=help | | rule_dialog(from=practice, page=0) |
| 16 | practice | enter | 選択なし ∧ 盤面legal ∧ クールダウン外 | 判定(§4) | practice |
| 17 | game_countdown | timeout:countdown(GO後) | | 計測開始 | game_play |
| 18 | game_play | enter | 盤面legal ∧ クールダウン外 ∧ 残時間>0 | 判定(§4) | game_play |
| 19 | game_play | timeout:timeup(60s) | | 最新の合法盤面を最後に1回判定して結果確定、iPadをname入力モードへ | result |
| 20 | result | name_text | | ディスプレイへミラー(10文字上限) | result |
| 21 | result | name_done | | iPadをbuttonsモードへ | result |
| 22 | result | left / right | buttonsモード | 入力⇄決定 のfocus移動 | result |
| 23 | result | enter | focus=入力 | iPadをnameモードへ(再入力) | result |
| 24 | result | enter | focus=決定 ∧ 1≦名前≦10文字 | プレイ保存+アップロードキュー投入 | ranking |
| 25 | ranking | enter | 表示から3秒以上 | | qr |
| 26 | qr | enter | 表示から5秒以上 | | idle_title(言語をjaへリセット) |

- 起動時の初期状態は `idle_title`。
- 判定クールダウンは0.5秒(仕様§5.6)。ガードを満たさない enter は無視(演出・音も出さない)。
- 時間切れ直前の判定: enter の受信時刻が timeup 前なら有効(仕様§5.6)。タイムアップ時は、
  最新の確定盤面が合法ならクールダウンを無視して最後に1回だけ判定する。違法盤面・未確定盤面は判定しない。

## 4. 判定アクション(行16・18の共通処理)

1. 確定盤面(cv-interface.md §3 の最新 CvBoardUpdate、legal=true)を対象に `judge()`(game-core-api.md)を実行。
2. scored なら合計スコアに加点。unclearable なら fail_count+1。判定済み集合(canonical_key と生盤面文字列)に追加。
3. `judge` メッセージを display へ、`flash` を controller へ送信(ws-messages.md)。
4. 本番のみ judgements 履歴(seq, board, elapsed_ms, result, points, min_moves, dup_of_seq)を記録。練習は記録しない。

## 5. 画面別 ctx 型(snapshot / screen の payload)

```jsonc
idle_title:     {}
idle_ranking:   { "entries": RankingEntry[] }
mode_select:    { "focus": "rules" | "practice" | "game" | "lang" }
rule_dialog:    { "from": "mode_select" | "practice", "page": 0, "page_count": 5 }
practice:       { "score": 0, "selection": null | "back" | "help" }
game_countdown: { "value": "3" | "2" | "1" | "go" }
game_play:      { "score": 0, "fail_count": 0, "remaining_ms": 60000 }
result:         { "score": 0, "fail_count": 0, "rank": 3, "name_text": "",
                  "focus": "input" | "decide", "input_mode": "buttons" | "name" }
ranking:        { "entries": RankingEntry[], "highlight_play_id": "uuid" }
qr:             { "url": "https://.../records/<play_id>", "play_id": "uuid" }
```

- result 入場直後は input_mode=name(キーボード自動表示)、キーボード完了後の初期 focus は `decide`。
- 盤面・箱ストリームは ctx に含めない(`boxes` / `board` メッセージで別送。全画面共通)。
