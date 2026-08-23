# Pyxel Cube 固定ランタイム

source: https://github.com/kitao/pyxel/tree/cube @ f731329 (2026-08-12)
built:  2026-08-23 macOS 26.6 / Apple Silicon, rust nightly-2026-07-14 (rustc 1.99.0-nightly daf2e5e18), emscripten 5.0.3, Pyodide 314.0.2

同梱物(5 種。どれか欠けるとブラウザで真っ白のまま止まる):

| ファイル | 用途 |
|---|---|
| `pyxel.js` | ローダー。`PYXEL_WHEEL_PATH` が同ディレクトリの wheel を指す |
| `pyxel.css` | キャンバスのスタイル |
| `import_hook.py` | Pyodide 上で `import` を HTTP 取得に置き換える |
| `images/`(7 ファイル) | 起動ロゴ・タッチ開始画像。無いと `load` 待ちで停止 |
| `pyxel-3.0.0-cp311-abi3-emscripten_5_0_3_wasm32.whl` | cube ブランチの WASM wheel |

更新手順は `docs/pyxel_app_specification.md` §8.2。通常セッションでは更新しない(計画書 §6)。
