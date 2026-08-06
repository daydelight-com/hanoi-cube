"""FastAPIアプリのエントリポイント(WSエンドポイント・状態機械の起動)。

CVソースは既定でモック(app/cv/mock.py)。HANOI_CV=real で実CV(app/cv/real.py、
カメラ+別プロセスワーカー)に切り替える。モックは本番の縮退経路として残す
(CLAUDE.md 規則6)。開発中はモック操作用のHTTPエンドポイント(/api/mock/*)で
盤面を動かせる。
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.api import ws
from app.api.messages import CameraSide
from app.api.ws import GameServer, Hub, run_loop
from app.cloud.uploader import Uploader, make_sink
from app.core.precompute import load_table
from app.cv.interface import CvSource
from app.cv.mock import MockCv
from app.state.machine import DEFAULT_RECORD_URL_BASE, StateMachine
from app.state.sqlite_store import SqliteStore

# ローカルDBの既定パス(仕様§7.1。output/ と *.sqlite3 はgitignore済み)
DEFAULT_DB_PATH = "output/plays.sqlite3"

logger = logging.getLogger(__name__)


def _camera_side() -> CameraSide:
    """環境変数 HANOI_CAMERA_SIDE を読む(back=カメラ奥側=既定 / front=カメラ待機エリア側)。"""
    raw = os.environ.get("HANOI_CAMERA_SIDE", "back")
    if raw == "front":
        return "front"
    if raw != "back":
        logger.warning("HANOI_CAMERA_SIDE が不正: %r。back として扱う", raw)
    return "back"


def _make_cv() -> CvSource:
    """環境変数 HANOI_CV でCVソースを選ぶ(mock=既定 / real=実CV)。"""
    if os.environ.get("HANOI_CV", "mock") == "real":
        # 実CV系の依存(opencv等)はモック運用時に読み込まない
        from app.cv.real import RealCv

        return RealCv()
    return MockCv()


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
        store = SqliteStore(os.environ.get("HANOI_DB_PATH", DEFAULT_DB_PATH))
        machine = StateMachine(
            table,
            store,
            now_ms=ws.now_ms(),
            record_url_base=os.environ.get("HANOI_RECORD_URL_BASE", DEFAULT_RECORD_URL_BASE),
        )
        server = GameServer(
            machine=machine, hub=Hub(), cv=_make_cv(), store=store, camera_side=_camera_side()
        )
        app.state.game = server
        task = asyncio.create_task(run_loop(server)) if start_loop else None
        # クラウドアップロード(未設定なら無効)。失敗してもゲームは止めない(仕様§3.2-1)
        sink = make_sink() if start_loop else None
        upload_task = asyncio.create_task(Uploader(store, sink).run()) if sink else None
        try:
            yield
        finally:
            for t in (task, upload_task):
                if t is not None:
                    t.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await t
            close = getattr(server.cv, "close", None)
            if callable(close):
                close()  # 実CVのワーカープロセスを止める
            store.close()

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
