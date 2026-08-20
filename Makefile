# Hanoi Cube 開発タスク。全セッションの完了条件は `make check` が通ること。

.PHONY: check check-server check-frontend check-cloud dev dev-server dev-frontend mock camera-check

check: check-server check-frontend check-cloud

check-server:
	cd server && uv run ruff check . && uv run ruff format --check . && uv run mypy && uv run pytest -q

check-frontend:
	cd frontend && npm run --silent check

check-cloud:
	cd cloud/record && npm run --silent check

# サーバー(:8000)+フロント(:5173)を同時起動
dev:
	$(MAKE) -j2 dev-server dev-frontend

dev-server:
	cd server && uv run uvicorn app.api.main:app --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

# モックCV: キーボード操作で盤面を作り cv-interface 準拠の出力を確認する
mock:
	cd server && uv run python -m app.cv.mock_cli

# カメラ設営チェック: 検出オーバーレイを表示(qで終了、サマリと判定が出る)。
# カメラ番号を変える場合は `make camera-check CAMERA=1`
CAMERA ?= 0
camera-check:
	cd server && uv run python ../scripts/cv_poc.py --camera $(CAMERA) --show
