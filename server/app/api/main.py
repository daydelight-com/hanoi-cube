"""FastAPIアプリのエントリポイント(S0では足場のみ。WS・状態機械はS2で実装)。"""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="Hanoi Cube Server")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
