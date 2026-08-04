"""WebSocketエンドポイントと配信ハブ(契約: docs/contracts/ws-messages.md)。

- /ws/display: 表示専用。接続直後に snapshot を送る。
- /ws/controller: iPad。接続直後に snapshot、以降 button / name_text / name_done を受ける。
- 約30fpsのループでモック/実CVを poll し、frame は boxes として転送、
  盤面更新とタイマーは状態機械へ渡して結果を配信する。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from app.api.messages import ButtonPayload, InboundMessage, NameTextPayload, Outbound
from app.cv.interface import CvBoardUpdate, CvFrame, CvSource
from app.state.machine import StateMachine
from app.state.store import PlayStore

POLL_INTERVAL_S = 1 / 30


def now_ms() -> int:
    """状態機械に渡す単調増加時刻(ms)。"""
    return int(time.monotonic() * 1000)


class Hub:
    """チャンネル別のWS接続集合と配信。"""

    def __init__(self) -> None:
        self.display: set[WebSocket] = set()
        self.controller: set[WebSocket] = set()

    def _targets(self, channel: str) -> set[WebSocket]:
        return self.display if channel == "display" else self.controller

    async def broadcast(self, outbounds: list[Outbound]) -> None:
        for outbound in outbounds:
            data = outbound.as_json()
            targets = self._targets(outbound.channel)
            for ws in list(targets):
                try:
                    await ws.send_json(data)
                except Exception:
                    targets.discard(ws)


@dataclass
class GameServer:
    """アプリ全体で共有する実行時状態(app.state.game に載せる)。"""

    machine: StateMachine
    hub: Hub
    cv: CvSource
    store: PlayStore
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def dispatch(self, outbounds: list[Outbound]) -> None:
        if outbounds:
            await self.hub.broadcast(outbounds)


async def run_loop(server: GameServer) -> None:
    """CVポーリング+タイマーtickの常駐ループ。"""
    while True:
        async with server.lock:
            now = now_ms()
            outbounds: list[Outbound] = []
            for message in server.cv.poll():
                if isinstance(message, CvFrame):
                    outbounds.append(
                        Outbound(
                            "display",
                            "boxes",
                            {
                                "t_ms": message.t_ms,
                                "boxes": [b.model_dump(mode="json") for b in message.boxes],
                            },
                        )
                    )
                elif isinstance(message, CvBoardUpdate):
                    outbounds += server.machine.on_cv_message(message, now)
            outbounds += server.machine.tick(now)
            await server.dispatch(outbounds)
        await asyncio.sleep(POLL_INTERVAL_S)


router = APIRouter()


@router.websocket("/ws/display")
async def ws_display(websocket: WebSocket) -> None:
    server: GameServer = websocket.app.state.game
    await websocket.accept()
    async with server.lock:
        # 登録前に snapshot を送り、最初の受信メッセージが必ず snapshot になるようにする
        await websocket.send_json(
            {"type": "snapshot", "payload": server.machine.display_snapshot()}
        )
        server.hub.display.add(websocket)
    try:
        while True:
            await websocket.receive_text()  # ディスプレイ→サーバーのメッセージはない(無視)
    except WebSocketDisconnect:
        pass
    finally:
        server.hub.display.discard(websocket)


@router.websocket("/ws/controller")
async def ws_controller(websocket: WebSocket) -> None:
    server: GameServer = websocket.app.state.game
    await websocket.accept()
    async with server.lock:
        await websocket.send_json(
            {"type": "snapshot", "payload": server.machine.controller_snapshot()}
        )
        server.hub.controller.add(websocket)
    try:
        while True:
            raw = await websocket.receive_json()
            # 時間ガード(timeup直前のenter等)は受信時刻で判定する(screens.md §3)
            received_ms = now_ms()
            try:
                inbound = InboundMessage.model_validate(raw)
            except ValidationError:
                continue  # 外形不正は無視
            async with server.lock:
                await server.dispatch(_handle_inbound(server.machine, inbound, received_ms))
    except WebSocketDisconnect:
        pass
    finally:
        server.hub.controller.discard(websocket)


def _handle_inbound(machine: StateMachine, inbound: InboundMessage, now: int) -> list[Outbound]:
    """iPad→サーバーのメッセージを状態機械へ渡す。未知の type は無視(ws-messages.md)。"""
    try:
        if inbound.type == "button":
            button = ButtonPayload.model_validate(inbound.payload).button
            return machine.on_button(button, now)
        if inbound.type == "name_text":
            text = NameTextPayload.model_validate(inbound.payload).text
            return machine.on_name_text(text, now)
        if inbound.type == "name_done":
            return machine.on_name_done(now)
    except ValidationError:
        return []
    return []
