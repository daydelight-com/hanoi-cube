# Cubeでハノイ(Hanoi Cube)

PyCon JP ブース向けのフィジカル×デジタルゲーム。
AprilTag を貼った箱(大・中・小 × 各3個 = 9個)をプレイマット上に「ハノイの塔」として手で並べ、
カメラ認識した盤面を 3D 画面に映しながら、制限時間 1 分でスコアアタックします。

- 得点 = 盤面の箱の総数 × その盤面を最短でクリアするのに必要な手数
- 同じ配置(鏡像を含む)を再び作っても得点は入らない
- ルールの正は [docs/game/hanoi_arrange_rules.md](docs/game/hanoi_arrange_rules.md)、得点表は [docs/game/score_ranking.md](docs/game/score_ranking.md)

## システム構成

| 機材 | 役割 |
|---|---|
| MacBook | サーバー(FastAPI)+ CV(AprilTag 検出)+ 3D 描画(ブラウザ) |
| iPhone | 連係カメラ(Continuity Camera)。斜め上からプレイマットを俯瞰撮影 |
| iPad | コントローラ(←/→/決定、名前入力)。同一 LAN からブラウザで接続 |
| ディスプレイ | ブラウザ全画面(16:9 前提)でゲーム画面を表示 |
| 記録画面 | Firebase Hosting 上の SPA。プレイ後に QR から開く |

```
server/app/      Python 3.12+: core(判定・純ロジック) state(状態機械) cv(検出・モック) api(WS/HTTP) cloud(Firebase)
server/tests/    pytest
frontend/src/    React+TS+Vite: display/ controller/ three/ sfx/ i18n/ contracts/(TS写し)
cloud/           firestore.rules + record/(記録画面SPA、Firebase Hosting)
scripts/         タグシート生成・運用スクリプト
docs/            仕様書・モジュール間契約(docs/contracts/)・引き継ぎメモ(docs/handoff/)
```

## 前提ツール

- Python 3.12 以上 と [uv](https://docs.astral.sh/uv/)(`server/uv.lock` で依存を固定)
- Node.js(LTS)と npm
- (任意)[firebase-tools](https://firebase.google.com/docs/cli) — 記録画面のデプロイ・Firestore エミュレータに使用

## 環境構築

```bash
git clone <このリポジトリ>
cd hanoi-cube

# Python(サーバー)
cd server && uv sync && cd ..

# フロントエンド(ゲーム画面・コントローラ)
cd frontend && npm install && cd ..

# 記録画面 SPA
cd cloud/record && npm install && cd ../..
```

### 実カメラで動かす場合の追加準備

- タグマスタと印刷用シートを生成する(出力先 `output/` は gitignore 済み)。

  ```bash
  cd server && uv run python ../scripts/generate_tag_sheet.py
  ```

  `output/apriltag_sheet.pdf` を A4 実寸(100%)で印刷して箱とマットに貼り、
  `output/tag_master.json` がタグ ID → 箱・面の対応表になります。貼付規約は [docs/operations.md](docs/operations.md) を参照。
- Firebase にプレイ記録を上げる場合は、サービスアカウント鍵をリポジトリ直下に `service-account.json` として置きます
  (gitignore 済み。**絶対にコミットしない**)。鍵が無ければクラウド連携は無効のままローカルで動作します。

## 起動

### 開発機(カメラなし)

```bash
HANOI_CV=mock make dev
```

サーバー(:8000)とフロント(:5173)が同時に起動します。

| URL | 画面 |
|---|---|
| http://localhost:5173/ | ディスプレイ(ゲーム画面) |
| http://localhost:5173/controller | コントローラ。iPad からは `http://<MacのIP>:5173/controller` |
| http://localhost:8000/healthz | サーバー死活確認 |

別ターミナルでモック CV の CLI を開き、キーボードで盤面を操作できます。

```bash
make mock
```

```
grab <box>       箱を掴む(box: large-1 / L1 / m2 / small-3 など)
place <A|B|C|W>  掴んでいる箱を塔A/B/C・待機エリア(W)に置く
board <盤面>     論理盤面を一括セット(例: board LMS//L)。残りは待機エリアへ
help / quit
```

### 本番(実カメラ)

```bash
make dev
```

環境変数なしの `make dev` は「実 CV + 本番アップロード(`service-account.json` がある場合のみ。無ければクラウド連携は無効)」で動きます。
カメラが接続されていないマシンでは実 CV の初期化に失敗するため、開発時は必ず `HANOI_CV=mock` を付けてください。
カメラをプレイヤー側(待機エリア側)に置く場合のみ `HANOI_CAMERA_SIDE=front make dev` とします。

### カメラ設営チェック

iPhone(連係カメラ)を三脚に固定して接続したら、本番起動の前に検出オーバーレイで画角・検出品質を確認します。

```bash
make camera-check          # カメラ番号を変える場合は make camera-check CAMERA=1
```

(`cd server && uv run python ../scripts/cv_poc.py --camera 0 --show` と同じ)

- 画角幅が約 75cm になるようカメラ距離を調整する(オーバーレイの px/mm 表示が約 2.56 になる位置)
- 静止検証: 全箱を置いて `mat=4/4`(マット四隅タグ)と各タグの margin を確認
- 追従検証: 中箱を掴んで塔間を速く動かし、箱単位の最大ギャップが 500ms 以下を目安に確認
- `q` キーで終了するとサマリと判定が表示される

最終確認は実サーバーで行います: `make dev` で起動し、サーバーログにキャリブレーション成立が出ること、
「カメラ側の設定と実測が食い違う」警告(`HANOI_CAMERA_SIDE` の設定ミス検知)が出ないことを確認します。

### 記録画面 SPA

```bash
cd cloud/record && npm run dev   # http://localhost:5173/records/demo で Firebase なしのデモ表示
```

詳細(エミュレータ接続・ビルド・デプロイ)は [cloud/record/README.md](cloud/record/README.md)。

## 検証

```bash
make check
```

- server: `ruff check` / `ruff format --check` / `mypy --strict` / `pytest`
- frontend, cloud/record: `eslint` / `prettier --check` / `tsc -b` / `vitest`

全セッションの完了条件はこの `make check` が通ることです。個別には `make check-server` / `make check-frontend` / `make check-cloud`。

注意: `make dev` 稼働中に `make check` を走らせると `uvicorn --reload` がサーバーを再起動し、ゲーム状態が idle に戻ります。

E2E(`make dev` 起動済みの状態で実行。実時間のタイマーを含むため約 90 秒):

```bash
cd frontend && node e2e/full-play.mjs
```

## 主な環境変数(サーバー)

| 変数 | 既定 | 意味 |
|---|---|---|
| `HANOI_CV` | `real` | `mock` でモック CV |
| `HANOI_CAMERA_SIDE` | `back` | `front` でカメラがプレイヤー側(3D 視点を 180° 反転) |
| `HANOI_MOCK_API` | `1` | `/api/mock/*` の有効化。本番は `0` |
| `HANOI_DB_PATH` | `output/plays.sqlite3` | プレイ記録のローカル SQLite |
| `HANOI_RECORD_URL_BASE` | `https://hanoi-cube.web.app/records/` | QR に載せる記録画面 URL の基底 |
| `HANOI_CV_CAMERA` / `HANOI_CV_VIDEO` | `0` / なし | カメラ番号 / 代わりに読む動画ファイル |
| `HANOI_CV_WIDTH` / `HANOI_CV_HEIGHT` | `1920` / `1080` | 撮影解像度 |
| `HANOI_TAG_MASTER` | `output/tag_master.json` | タグマスタのパス |
| `HANOI_CV_CALIBRATION` | `output/cv_calibration.json` | キャリブレーション永続化先(空文字で無効) |
| `HANOI_FIREBASE_CREDENTIALS` | リポジトリ直下 `service-account.json` を自動検出 | Firebase サービスアカウント鍵 |
| `HANOI_FIREBASE_PROJECT` | — | Firebase プロジェクト ID の明示 |
| `FIRESTORE_EMULATOR_HOST` | — | Firestore エミュレータ(例 `127.0.0.1:8080`) |

汎用の `GOOGLE_APPLICATION_CREDENTIALS` は意図的に参照しません(他案件の Firestore への誤接続を防ぐため)。

## スクリプト(`scripts/`)

いずれも `cd server && uv run python ../scripts/<名前>.py` で実行します。

| スクリプト | 用途 |
|---|---|
| `generate_tag_sheet.py` | AprilTag(tag36h11)印刷シート `output/apriltag_sheet.pdf` と `output/tag_master.json` を生成 |
| `reset_plays.py` | 本番開始前のプレイデータ初期化(ローカル SQLite 削除 + Firestore `plays` 全削除)。手順は [docs/operations.md](docs/operations.md) |
| `generate_score_ranking.py` | `docs/game/score_ranking.md` を事前計算テーブルから再生成 |
| `generate_all_patterns_play.py` | 全 512 盤面を含むデモ用プレイ記録を生成し Firestore へ投入(`--out` で JSON 出力のみ) |
| `cv_poc.py` / `cv_poc_synth.py` / `cv_poc_perf.py` | 実カメラ・合成画像・スループットの AprilTag 検出 PoC 計測(記録は [docs/cv_poc.md](docs/cv_poc.md)) |

## 本番前のデータクリア

開発・検証も本番と同じストア(ローカル SQLite と Firestore の `plays`)に書くため、
**本番開始直前に一度だけ**両方をセットで初期化します(2日目の朝はリセットしない。ランキングは2日間累積)。

```bash
# 1. サーバーを停止する(make dev を Ctrl-C)
# 2. リセット実行(リポジトリ直下の service-account.json を自動検出)
cd server && uv run python ../scripts/reset_plays.py
# 削除対象の件数が表示されるので、確認して yes を入力
# 3. サーバーを起動し直す(SQLite スキーマは起動時に自動作成)
```

- **片側だけの削除は禁止**(SQLite だけ残すと開発プレイがランキングに出続ける)。
  スクリプトは Firestore 未構成なら SQLite にも手を付けずにエラー終了する
- 途中失敗時は原因(ネットワーク・認証)を解消して再実行すれば残りが消える(再実行は安全)
- 詳細・エミュレータでのリハーサル手順は [docs/operations.md](docs/operations.md)

## デプロイ(記録画面)

```bash
cd cloud/record
VITE_FIREBASE_PROJECT_ID=<本番プロジェクトID> VITE_FIREBASE_API_KEY=<WebAPIキー> npm run build
cd .. && firebase deploy --only firestore,hosting
```

## Pyxel Cube 版(ブラウザ単体でプレイ)

カメラ・箱・iPad を使わず、ブラウザだけで遊べる派生版。`pyxel_app/` に閉じており、判定ロジックは `server/app/core/` を import するだけ。
公開 URL: https://daydelight-com.github.io/hanoi-cube/ (`main` への push で GitHub Actions が自動デプロイ)。
仕様は [docs/pyxel_app_specification.md](docs/pyxel_app_specification.md)、進め方は [docs/pyxel_app_development_plan.md](docs/pyxel_app_development_plan.md)。

### 遊び方

1. 公開 URL を開き、ロード後の「CLICK TO START」をクリック(この 1 クリックで効果音も有効になる)
2. タイトルで「スタート」。ルールはゲーム内の「ルール」(5 ページ)にまとまっている。右上の JA / EN で言語切替
3. 3-2-1-GO! のあと **60 秒**。箱をドラッグ&ドロップで 3 本の塔に並べ、「はんてい」を押すと
   その盤面が「ハノイの塔のルールで崩せる配置」なら手数に応じて得点。崩せない配置は「MISS」、判定済みの盤面は「ALREADY」(0 点)
4. 同じ盤面は 2 度得点できないので、判定したら並べ替えて次の盤面へ。タイムアップでスコア発表。自己ベストはブラウザに保存される

操作はマウス / タッチのみで完結する(補助キー: Enter=はんてい、Esc=タイトルへ、Q=終了〔ネイティブ版〕)。

Pyxel は未リリースの `cube` ブランチを使うため **`pip install pyxel` では動かない**。ビルド済み wheel を GitHub Release
[`pyxel-cube-runtime-2026-08-23`](https://github.com/daydelight-com/hanoi-cube/releases/tag/pyxel-cube-runtime-2026-08-23) で配布している
(macOS Apple Silicon 用。`pyxel_app/pyproject.toml` の `[tool.uv.sources]` がこの URL を指すので `uv sync` だけで入る。
Windows 用は未作成 → 仕様書 §8.1.1)。

```bash
cd pyxel_app && uv sync && cd ..      # pyxel(cube)・pydantic・開発ツールを導入
cd pyxel_app && uv run python main.py  # ネイティブで実行(Q で終了)
make pyxel-serve                       # ブラウザ版: site/ を組み立てて http://localhost:8081 で配信
make check-pyxel                       # ruff / mypy strict / pytest(make check にも含まれる)
```

ブラウザのコンソールに `Launch Pyxel 3.0.0 with Pyodide 314.0.2` と出ていれば固定ランタイム(`pyxel_app/runtime/`)を読めている。
ランタイムの更新(cube ブランチの再ビルド)は仕様書 §8.2 の担当者のみが行う。

## ドキュメント

- [docs/specification.md](docs/specification.md) — システム仕様書
- [docs/pyxel_app_specification.md](docs/pyxel_app_specification.md) — Pyxel Cube 版の仕様書・設計書(セットアップ手順 §8 を含む)
- [docs/contracts/](docs/contracts/) — モジュール間契約(board / ws-messages / cv-interface / game-core-api / firestore / screens)。Python/TS の写しと乖離した場合はこちらが正
- [docs/operations.md](docs/operations.md) — 設営(カメラ位置・タグ貼付規約)と本番リセット手順
- [docs/game/](docs/game/) — ゲームルールと得点表
- [docs/handoff/](docs/handoff/) — 開発セッションごとの引き継ぎメモ
- [CLAUDE.md](CLAUDE.md) — 開発時の規則(AI エージェント向け)
