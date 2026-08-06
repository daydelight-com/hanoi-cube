"""WebSocketメッセージ型のPython写し(契約: docs/contracts/ws-messages.md, screens.md)。

TS写しは frontend/src/contracts/ws.ts。乖離したら契約mdが正。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

Lang = Literal["ja", "en"]
CameraSide = Literal["back", "front"]
ButtonName = Literal["left", "right", "enter"]
CountdownValue = Literal["3", "2", "1", "go"]
InputMode = Literal["buttons", "name"]
FlashResult = Literal["scored", "failed", "duplicate"]
JudgeResultKind = Literal["scored", "unclearable", "duplicate_same", "duplicate_mirror"]

ScreenId = Literal[
    "idle_title",
    "idle_ranking",
    "mode_select",
    "rule_dialog",
    "practice",
    "game_countdown",
    "game_play",
    "result",
    "ranking",
    "qr",
]

SfxId = Literal[
    "cursor",
    "decide",
    "back",
    "count",
    "go",
    "judge_success",
    "judge_fail",
    "judge_dup",
    "tick10",
    "timeup",
    "rank_tick",
    "fanfare",
    "key_touch",
    "pad_button",
    "pad_flash",
]


class RankingEntry(BaseModel):
    """ランキング1行(ws-messages.md §2)。"""

    rank: int
    name: str
    score: int
    fail_count: int
    play_id: str
    played_at: str


class JudgePayload(BaseModel):
    """judge メッセージの payload(ws-messages.md §2)。"""

    seq: int
    result: JudgeResultKind
    points: int
    min_moves: int | None
    board: str
    total_score: int
    fail_count: int


# ---- iPad → サーバー(ws-messages.md §6) ----


class ButtonPayload(BaseModel):
    button: ButtonName


class NameTextPayload(BaseModel):
    text: str


class InboundMessage(BaseModel):
    """受信メッセージの外形。未知の type は受信側で無視する(ws-messages.md)。"""

    type: str
    payload: dict[str, Any] = {}


# ---- サーバー → クライアントの送信単位 ----

Channel = Literal["display", "controller"]


@dataclass(frozen=True)
class Outbound:
    """状態機械が返す送信メッセージ。API層が該当チャンネルの全接続へ配る。"""

    channel: Channel
    type: str
    payload: dict[str, Any]

    def as_json(self) -> dict[str, Any]:
        return {"type": self.type, "payload": self.payload}
