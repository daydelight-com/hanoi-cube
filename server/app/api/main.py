"""FastAPIアプリのエントリポイント(WSエンドポイント・状態機械の起動)。

CVソースは既定でモック(app/cv/mock.py)。実CV(S8)は CvSource 準拠の実装に
差し替える。開発中はモック操作用のHTTPエンドポイント(/api/mock/*)で盤面を動かせる。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.api import ws
from app.api.ws import GameServer, Hub, run_loop
from app.core.precompute import load_table
from app.cv.mock import MockCv
from app.state.machine import DEFAULT_RECORD_URL_BASE, StateMachine
from app.state.store import MemoryStore


class MockBoardRequest(BaseModel):
    board: str


class MockGrabRequest(BaseModel):
    box_id: str


class MockPlaceRequest(BaseModel):
    target: str


def create_app(*, start_loop: bool = True) -> FastAPI:
    """アプリを構築する。start_loop=False はテスト用(ループを起動しない)。"""

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        table = load_table()  # プロセス起動時に1回ロードして使い回す
        store = MemoryStore()
        machine = StateMachine(
            table,
            store,
            now_ms=ws.now_ms(),
            record_url_base=os.environ.get("HANOI_RECORD_URL_BASE", DEFAULT_RECORD_URL_BASE),
        )
        server = GameServer(machine=machine, hub=Hub(), cv=MockCv(), store=store)
        app.state.game = server
        task = asyncio.create_task(run_loop(server)) if start_loop else None
        try:
            yield
        finally:
            if task is not None:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="Hanoi Cube Server", lifespan=lifespan)
    app.include_router(ws.router)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/ranking")
    def ranking() -> dict[str, Any]:
        # クラウド優先+ローカルフォールバックはS9で実装。S2はローカルストアのみ
        server: GameServer = app.state.game
        return {"entries": [e.model_dump(mode="json") for e in server.store.ranking()]}

    def _mock(server: GameServer) -> MockCv:
        # 本番運用(S10)では HANOI_MOCK_API=0 で無効化する(LAN上の第三者による盤面操作対策)
        if os.environ.get("HANOI_MOCK_API", "1") == "0":
            raise HTTPException(status_code=403, detail="mock API is disabled")
        if not isinstance(server.cv, MockCv):
            raise HTTPException(status_code=409, detail="CV source is not the mock")
        return server.cv

    async def _mock_op(op: Callable[[MockCv], None]) -> dict[str, str]:
        # ポーリングループ(run_loop)と同じロックで排他し、確定盤面イベントの消失を防ぐ
        server: GameServer = app.state.game
        async with server.lock:
            try:
                op(_mock(server))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"status": "ok"}

    @app.post("/api/mock/board")
    async def mock_board(req: MockBoardRequest) -> dict[str, str]:
        # 開発用: モックCVの盤面を一括セット(cv-interface.md §4 の board コマンド相当)
        return await _mock_op(lambda cv: cv.set_board(req.board))

    @app.post("/api/mock/grab")
    async def mock_grab(req: MockGrabRequest) -> dict[str, str]:
        return await _mock_op(lambda cv: cv.grab(req.box_id))

    @app.post("/api/mock/place")
    async def mock_place(req: MockPlaceRequest) -> dict[str, str]:
        return await _mock_op(lambda cv: cv.place(req.target))

    return app


app = create_app()
