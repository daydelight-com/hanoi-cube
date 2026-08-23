# Hanoi Cube Pyxel 版 開発計画書

仕様: [pyxel_app_specification.md](pyxel_app_specification.md)(本計画書はその実装手順)。
本体の計画 [development_plan.md](development_plan.md) の §5(セッションの進め方)・§6(品質ゲート)はそのまま適用する。
セッション番号は本体の S 系列と区別して **P 系列**(P1, P2, ...)とし、handoff は `docs/handoff/P{n}.md` に書く。

## 1. 基本方針

1. **既存を壊さない。** `server/` `frontend/` `cloud/` `docs/contracts/` は変更しない。Pyxel 版は `pyxel_app/` に閉じ、
   判定ロジック(`server/app/core/`)は import するだけ。どうしても本体側の変更が必要になったら handoff に「要判断」として
   記録し、本体の合意を取ってから別セッションで行う。
2. **ランタイムは固定。** Pyxel cube ブランチからビルドした wheel を `pyxel_app/runtime/` にコミットし、
   CDN や Web Launcher は使わない。cube の更新は P 系列の通常セッションでは行わず、§6 の「ランタイム更新」手順でのみ行う。
3. **Pyxel 非依存層を厚くする。** 盤面の所在・ドラッグ状態機械・判定集計・座標変換は純 Python で書き pytest で回す。
   Pyxel に触る層(描画・入力取得)は薄いラッパーに留める(仕様書 §6.1)。
4. **毎セッション「ブラウザで動く」を確認する。** ネイティブ実行で開発し、終了前に `make pyxel-site` → ローカル HTTP → ブラウザ確認を必須とする
   (Pyodide 固有の問題を早期に踏むため)。
5. セッションは半日以内の粒度。依存のないものは並行可(P2 と P4 の一部など)。

## 2. 前提(P1 着手前にユーザーが決めること)

仕様書 §11 の要判断のうち、着手前に確定が必要なもの。未回答ならデフォルトで進める。

| # | 論点 | デフォルト |
|---|---|---|
| #2 | 日本語 UI | **決定: 最初から日本語 UI(JA/EN 切替)で作る。** BDF フォントを同梱し P5 で実装。フォント選定・ライセンス確認は P1 で済ませる |
| #8 | ネイティブ wheel の配布 | **決定: ビルド済み wheel を GitHub Release `pyxel-cube-runtime-<日付>` に添付して配布する。** まず macOS(Apple Silicon)用。Windows 用は Windows 開発者が参加した時点で CI(`windows-2022`)で作る |
| #9 | Windows での WASM ビルド | 行わない(Mac または CI) |

環境: ランタイム更新担当の Mac に Rust nightly-2026-07-14・cmake・emsdk 5.0.3・`~/workspace/pyxel-cube`(cube ブランチ)が
揃っていること(S27 で整備済み)。他の開発者は仕様書 §8.1 のみ。

## 3. 成果物の配置

```
pyxel_app/
├── main.py  screens/  scene/  input/  session.py  board_state.py  sfx.py  assets/
├── runtime/            固定ランタイム(P1 でコミット)
├── web/index.html
├── tests/
└── pyproject.toml      ruff / mypy strict / pytest(server と同じ設定を写す)
scripts/build_pyxel_site.py          site/ を組み立てる(Windows でも動くよう Python で書く)
.github/workflows/pyxel-pages.yml    main への push で Pages にデプロイ
Makefile                             pyxel-site / check-pyxel を追加(check に組み込む)
```

## 4. セッション計画

### フェーズ A: 土台(P1〜P2)

| # | セッション | 成果物 | 完了条件(DoD) |
|---|---|---|---|
| P1 | 足場・ランタイム固定・配信 | `pyxel_app/` の骨組み(`main.py` はサンプル c01 相当の回転キューブ)、`runtime/`(5 種 + `VERSION.md`)、`pyproject.toml`、`scripts/build_pyxel_site.py`、`make pyxel-site` / `make check-pyxel`、`.github/workflows/pyxel-pages.yml`、Pages のソースを GitHub Actions に切替、ネイティブ wheel(macOS)を Release に添付、README に開発者向け導線、**日本語 BDF フォントの選定・ライセンス確認・`assets/` への同梱と表示テスト** | **`https://daydelight-com.github.io/hanoi-cube/` で cube のキューブが回る**。`make check` に `pyxel_app/` の ruff/mypy/pytest が含まれ通る。`python pyxel_app/main.py` がネイティブで動く。`packages="pydantic"` で `from app.core import engine` が Pyodide 上で成功する(起動時に import して画面に `core OK` を表示)。**ブラウザで日本語(例:「ハノイキューブ」)が描画される** |
| P2 | 盤面モデル・座標系(Pyxel 非依存) | `board_state.py`(9 箱の所在 → 盤面文字列、配置ルール検証、塔の top 判定)、`scene/layout.py`(`layout.ts` の mm 定数を写し → ワールド座標、塔・待機スロット座標)、`input/drag.py`(仕様書 §4.5 の状態機械)、`scene/picking.py`(画面座標 → レイ、マット平面交点、最近傍スロット) | 全 512 合法盤面で「所在 → 文字列 → `board_index` → 復元」一致。配置ルール違反 3 種(大を小の上 / 同サイズ重複 / 4 個目)を拒否。ドラッグ状態機械の全分岐(legal / illegal / 範囲外 / top 以外を掴む)をテスト。ピッキングは既知の行列で中央・四隅を検証。`layout.ts` との数値一致テスト |

### フェーズ B: 3D とプレイ(P3〜P4)

| # | セッション | 成果物 | 完了条件 |
|---|---|---|---|
| P3 | 3D 盤面 + ドラッグ&ドロップ | `scene/board_scene.py`(Node ツリー: Mat / Box×9 / Highlight、Collider、指数平滑化 λ=12)、Pyxel のマウス入力を `drag.py` に流す結線、ドロップ候補のハイライト(緑/赤)、配置音・失敗音(暫定) | **ブラウザで 9 箱を塔・待機エリア間で自由に動かせ、違反は戻る**。塔の一番上以外は掴めない。M1 Mac / Chrome で 60fps(下回れば解像度を下げて記録)。iPhone Safari でタッチドラッグが動く |
| P4 | 判定・得点・ゲーム画面 | `session.py`(judged 集合・得点・失敗数・判定回数・`time.monotonic()` タイマー)、ゲーム画面 HUD(SCORE / TIME / MISS)、3-2-1-GO、JUDGE ボタンとクールダウン、判定フィードバック(+N / MISS / ALREADY)、タイムアップ → リザルト(仮) | **60 秒のプレイが成立し得点が入る**。`session` に既存 `StateMachine` と同じ判定列を流して score / fail_count / judged 集合が一致する照合テスト。タイムアップ境界(直前の判定は有効)とクールダウンのテスト。ドラッグ中は判定不可 |

### フェーズ C: 画面一式と公開品質(P5〜P6)

| # | セッション | 成果物 | 完了条件 |
|---|---|---|---|
| P5 | タイトル / ルール / リザルト + 効果音 + 日本語 UI | `screens/`(Screen 基底 + title / rules(4 ページ)/ result)、クリック遷移、効果音 7 種(`sfx.py`)、自己ベスト(`localStorage`、要判断 #6)、基調色 `#438532` のパレット差し替え、**文言の JA/EN 辞書(既存 `frontend/src/i18n/` の文言を流用)とタイトル画面の言語切替ボタン、日本語フォントでの HUD レイアウト調整** | **全画面がクリックだけで繋がる**(キーボード不要)。ボタン矩形の当たり判定テスト。最初のクリックで音声が解放され以降の効果音が鳴る。リロードしても自己ベストが残る。**全画面が日本語で表示され、切替で英語にも切り替わる(辞書の欠落キーをテストで検出)** |
| P6 | 通し磨き・実機確認・公開 | 演出調整(数字の点滅・+N のアニメ)、ロード中表示、対応ブラウザ確認(Chrome / Safari macOS・iOS / Edge Windows)、README の遊び方、仕様書 §8 の Windows 手順を Windows 開発者が実走して修正 | 3 ブラウザ + iPhone で通しプレイ 3 回ずつ問題なし。初回ロード 5 秒以内(回線 50Mbps)。仕様書・計画書と実装のずれを解消して handoff に記録 |

### フェーズ D: 第2段(任意。ユーザー判断で着手)

| # | セッション | 成果物 | 備考 |
|---|---|---|---|
| P7 | ランキング | Firebase JS SDK を `index.html` で読み込み、Pyodide の `js` モジュール経由で Firestore に保存・取得 | 既存 `contracts/firestore.md` との整合とセキュリティルールの確認が必要。本体側の合意を取る |
| P8 | 練習モード / 箱のテクスチャ化 | 制限時間なしモード、`Mesh` による面テクスチャ | 要判断 #1 / #10 |

## 5. セッションの進め方(P 系列の追加事項)

本体の §5 に加えて:

- 開始時に読むもの: `CLAUDE.md` → 直前の `docs/handoff/P{n-1}.md` → 仕様書 `pyxel_app_specification.md` の該当節 → 必要な契約(`board.md` `game-core-api.md`)。
- **終了前にブラウザ確認**: `make pyxel-serve`(`site/` 組み立て + `:8081` 配信)で動作を見る。コンソールに `Launch Pyxel 3.0.0` と出ていること。
- `/finish` の `make check` には `check-pyxel` が含まれる(P1 で組み込む)。
- Pyodide でだけ起きる問題(import 失敗・ファイル読み込み・`time` の挙動)は handoff の「既知の問題」に必ず残す。

## 6. ランタイム更新(通常セッションとは別扱い)

cube ブランチの更新を取り込むとき(新 API が必要になった / 重大バグの修正が入った)のみ実施する。
手順は仕様書 §8.2。必ず次を守る:

1. 専用セッションで行い、アプリの変更と混ぜない(コミットも分ける)。
2. 更新前後で P6 の通しプレイを再実行し、API 変更による破壊を確認する。
3. `runtime/VERSION.md` を更新し、handoff に「ランタイム更新」として記録する。
4. ネイティブ wheel も同時に作り直して Release に添付する(WASM と版を揃える)。

## 7. 品質ゲート(P 系列)

| 対象 | 基準 |
|---|---|
| Python(`pyxel_app/`) | ruff(lint+format)、mypy strict、pytest。server と同じ設定を写す |
| Pyxel 非依存層 | `board_state` は全 512 盤面、`drag` は全遷移、`session` は既存 `StateMachine` との照合 |
| Pyxel 依存層 | ブラウザ手動確認(各セッション末)。`make pyxel-site` の成果物に必須 5 種 + `.pyxapp` が揃うことを CI でチェック |
| 公開 | P6 で 3 ブラウザ + iPhone の通し。Pages の URL がデプロイ後 2 分以内に更新される |

「Pyxel のコールバックの中にゲームロジックを書く」「描画クラスが盤面文字列を組み立てる」は密結合として不合格(本体 §6 と同じ)。

## 8. リスクと逃げ道

| リスク | 兆候 | 逃げ道 |
|---|---|---|
| **cube の API が変わり動かなくなる** | ランタイム更新後に `AttributeError` 等 | ランタイムを固定しているので「更新しない」が第一選択。更新が必要なら §6 の手順で隔離 |
| ソフトウェアレンダリングが遅い(特に iPhone) | P3 で 30fps 未満 | 解像度 320×240 → 256×192、影・ハイライトの簡略化、箱の面数削減(立方体なので最小) |
| 画面→レイのピッキングがずれる | P3 で掴めない・隣の箱を掴む | 代替案: 箱ごとに画面上の投影矩形を計算して 2D 当たり判定にする(精度は落ちるが確実) |
| Pyodide で pydantic のロードが遅い・失敗する | P1 の `core OK` が出ない / ロード 10 秒超 | `app/core` の pydantic 依存を外す提案を本体側に出す(要判断 #3)。それまでは `packages` 指定で凌ぐ |
| `.pyxapp` 内からの `precompute.json` 読み込み失敗 | P1 で `FileNotFoundError` | `load_table()` に頼らず JSON をパッケージ内に同梱して `importlib.resources` 相当の方法で読む(`_core` 配下に置けば相対パスで届く) |
| Windows 開発者の環境構築で詰まる | 仕様書 §8 の手順が通らない | ネイティブ wheel(Windows)を CI の `windows-2022` で作って Release に置く。WASM ビルドは Mac/CI に限定 |
| GitHub Pages のサイズ・キャッシュ | wheel 更新後も古い版が読まれる | wheel のファイル名に版(3.0.0)が入っているのでファイル名が変われば自然に切り替わる。同名更新は避ける |

## 9. スケジュール目安

本番は終了済みのため固定の締切はない。各セッション半日として **P1〜P6 で 3〜4 日**。
P1 → P2 → P3 → P4 → P5 → P6 の順が基本。P2 は Pyxel 非依存なので P1 と並行可。
