# Hanoi Cube

PyCon JP ブース向けフィジカル×デジタルゲーム。箱(AprilTag付き)をハノイの塔として並べ、
カメラ認識+3D画面でスコアアタックする。**締切: 8/7 全画面モック駆動で完成 / 8/21-22 本番**。

## 読む順序(リポジトリ全体を読まない)

1. この CLAUDE.md
2. `docs/handoff/` の直前セッションのメモだけ
3. 担当に関係する契約 `docs/contracts/`(board / ws-messages / cv-interface / game-core-api / firestore / screens)
4. handoff に記載された仕様書の該当節(`docs/specification.md` §番号)と自分の担当ファイル

## 構成

```
server/app/      Python 3.12+: core(判定・純ロジック) state(状態機械) cv(検出・モック) api(WS/HTTP) cloud(Firebase)
server/tests/    pytest
frontend/src/    React+TS+Vite: display/ controller/ admin/ three/ sfx/ i18n/ contracts/(TS写し)
cloud/           firestore.rules + record/(記録画面SPA、Firebase Hosting)
scripts/         タグシート生成ほか
docs/contracts/  モジュール間契約(正)。docs/handoff/ 引き継ぎメモ(S1.md, ...)
```

## コマンド

- `make check` — lint+型+テスト(server: ruff/mypy strict/pytest、frontend/cloud: eslint/prettier/tsc)。全セッションの完了条件
- `make dev` — サーバー(:8000)+フロント(:5173)起動
- `make mock` — モックCVのCLI(キーボードで盤面操作。`board LMS//L` 等)

## 絶対規則

1. **契約(docs/contracts/)の変更は禁止が既定**。必要なら変更内容と影響範囲を handoff に明記し、
   影響を受ける側の修正まで同一セッションで完了させる。Python/TS の写しと乖離したら契約mdが正。
2. **テストは実装と同じセッションで書く**。「後でテスト」は禁止。
3. 契約・仕様に不明点や矛盾を見つけたら、勝手に解釈で確定させず handoff に「要判断」として記録し、
   妥当なデフォルトを選んで進める(選んだ内容も記録)。
4. 節目(モジュール完成・契約凍結/変更・大リファクタ後)で `/super-review` を実行する。
5. セッション終了時は `/finish` を実行する(super-review → make check → handoff更新 →
   日本語メッセージでコミット → push を内包)。
6. モックCV(`server/app/cv/mock.py`)は本番の縮退経路。**削除しない**。
