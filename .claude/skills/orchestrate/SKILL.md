---
name: orchestrate
description: 計画書のセクションを無人で連続実行するオーケストレーション。目標セクションをユーザーに確認し、セクションごとにヘッドレスセッション(claude -p)を起動→検証→次へ、を目標まで繰り返す。使用量制限で止まった場合は数時間後に自動復帰する。「無人で進めて」「オーケストレーションして」「帰るので続きをやっておいて」等で使用。
---

# orchestrate: 無人セクション連続実行

このセッションをオーケストレータとし、`docs/development_plan.md` §4 のセクションを
1セクション=1ヘッドレスセッションで順に無人実行する。

## 1. 開始時にユーザーへ確認する(必須)

- **どのセクションまで進めるか**(例: S6 まで)。回答を得るまで起動しない。
- 確認後は停止条件まで質問せず進める。

## 2. 事前チェック(離席前に完了させる)

過去の失敗(2026-08-04: Skill承認待ちで一晩停止)の再発防止。**全項目を実施する。**

1. **権限監査**: 以下のサイクル中の全ツール呼び出しを列挙し、`.claude/settings.local.json` の
   許可リストと1件ずつ照合する。不足があれば追記する。「権限=Bash」と考えない。
   Skill・Edit・Write も権限を通る。最低限必要: `Bash(claude *)` `Bash(git log *)`
   `Bash(git status *)` `Bash(ls *)` `Bash(caffeinate *)` `Bash(grep *)` `Bash(head *)`
   `Bash(tail *)` `Bash(cat *)` `Bash(uuidgen *)` `Bash(sleep *)`
   `Skill(next-session-prompt)` `Skill(next-session-prompt:*)`
2. **スリープ防止**: `caffeinate -is` をバックグラウンド起動する。
3. **前セクションの完了確認**: 作業ツリーがクリーンで、直前セクションの handoff が
   コミット・push 済みであること。未完了なら先に完了させる。
4. **スモークテスト**: `claude -p --model claude-fable-5 "OKとだけ返答してください"` が通ること。
5. ユーザーに「アプリとこのセッションを開いたまま帰ってよい」と伝える。

## 3. セクション実行サイクル(目標セクションまで繰り返し)

### 起動

1. `Skill(next-session-prompt)` で次セクションの開始プロンプトを生成し、
   スクラッチパッドに `prompt-S{n}.md` として保存する。
2. セッションIDを事前生成して(`uuidgen | tr 'A-Z' 'a-z'`)`sid-S{n}.txt` に保存し、
   4時間ウォッチドッグ付きでバックグラウンド起動する:

```
SID=$(uuidgen | tr 'A-Z' 'a-z') && echo "$SID" > "$SCRATCH/sid-S{n}.txt" && \
cat "$SCRATCH/prompt-S{n}.md" | claude -p --model claude-fable-5 \
  --dangerously-skip-permissions --session-id "$SID" > "$SCRATCH/result-S{n}.md" 2>&1 & CPID=$!
( sleep 14400; kill $CPID 2>/dev/null && echo "TIMEOUT_KILLED" ) & WPID=$!
wait $CPID; STATUS=$?; kill $WPID 2>/dev/null; echo "EXIT_STATUS=$STATUS"
```

### 終了通知を受けたら検証

以下をすべて確認する: exit status / `result-S{n}.md` の最終報告 /
`git log`(コミットあり)/ `git status`(ツリークリーン・push済み)/ handoff 作成済み。

- **完了** → 次セクションへ。目標セクションなら停止して総括を報告する。
- **仕掛かり終了**(実装済みだがコミット・push・レビュー未了。バックグラウンド処理を
  残したままターン終了した場合など)→ 保存済みIDで resume して /finish の残りを指示する:
  `claude -p --resume "$SID" --model claude-fable-5 --dangerously-skip-permissions "<残作業の指示>"`
- **使用量制限**(下記)→ 待機して復帰。
- **その他の失敗** → resume で1回リトライ。それでも失敗ならそこで停止し、状況を
  ユーザー向けに記録して報告する。壊れた状態で次セクションへ進まない。

### 使用量制限からの自動復帰

使用量は5時間窓で制限される。`result-S{n}.md` や exit status に
「usage limit」「rate limit」「limit reached」等が見られたら:

1. 出力からリセット時刻(epoch やタイムスタンプ)のパースを試みる。
2. 「リセット時刻+5分」までのバックグラウンド `sleep` を起動する
   (パース不能なら安全側で `sleep 18000` = 5時間)。sleep 完了で自動的に起こされる。
3. 起床後、保存済みIDで resume して作業の続きから再開する。
4. 途中で作業が進まず止まっているように見える場合も、まず使用量制限を疑う
   (オーケストレータ自身も同じ枠を消費する。sleep 復帰後なら枠は回復している)。

## 4. 原則

- 開始プロンプトは必ず `Skill(next-session-prompt)` で生成する(締切・時間圧の文言を入れない)。
- 子セッションの途中経過は見えない。判定は終了後の最終出力と git の状態で行う。
- 検証で得た申し送り以外に、子セッションの実装判断へ口を出さない。
- 各サイクルの結果はその都度このセッションにユーザー向けの進捗報告として残す。
