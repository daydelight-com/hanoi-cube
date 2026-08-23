"""ドラッグの状態機械(仕様書 §4.5)。Pyxel に依存しない。

```
Idle --(press on pickable box)--> Dragging --(release, legal)--> Idle(盤面更新)
                                    |
                                    +--(release, illegal / 範囲外)--> Idle(元位置へ戻す)
```

Pyxel 依存層(P3 の `board_scene.py`)は、マウス座標 → レイ → 当たった箱 ID / 床面の点 → ドロップ先
を求めて `press()` / `release()` に渡す。効果音や演出は戻り値 `DropOutcome` を見て呼び出し側が行う。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from board_state import BoardState, IllegalPlacementError, Location, RejectReason
from scene.layout import DropTarget, StagingTarget, TowerTarget


class DragState(Enum):
    IDLE = "idle"
    DRAGGING = "dragging"


class DropResult(Enum):
    PLACED = "placed"  # 盤面更新(配置音)
    RETURNED_ILLEGAL = "returned_illegal"  # 配置ルール違反(失敗音)
    RETURNED_OUT_OF_RANGE = "returned_out_of_range"  # しきい値外・ウィンドウ外(失敗音)


@dataclass(frozen=True)
class DropOutcome:
    result: DropResult
    box_id: str
    location: Location  # 確定した所在(戻った場合は元の位置)
    reason: RejectReason | None = None

    @property
    def placed(self) -> bool:
        return self.result is DropResult.PLACED


class DragController:
    """1 つの `BoardState` に対するドラッグ操作。"""

    def __init__(self, state: BoardState) -> None:
        self.board = state
        self._box_id: str | None = None
        self._origin: Location | None = None

    # ---- 状態 ----

    @property
    def state(self) -> DragState:
        return DragState.DRAGGING if self._box_id is not None else DragState.IDLE

    @property
    def is_dragging(self) -> bool:
        return self._box_id is not None

    @property
    def dragging_box(self) -> str | None:
        return self._box_id

    @property
    def origin(self) -> Location | None:
        """ドラッグ開始時の所在(戻し先)。"""
        return self._origin

    def can_judge(self) -> bool:
        """判定ボタンを押せるか(§4.5: Dragging 中は不可)。"""
        return not self.is_dragging

    # ---- 遷移 ----

    def press(self, box_id: str | None) -> bool:
        """mouse down。掴める箱(§4.2)なら Dragging に入り True。それ以外は Idle のまま False。"""
        if self.is_dragging or box_id is None or not self.board.is_pickable(box_id):
            return False
        self._box_id = box_id
        self._origin = self.board.location(box_id)
        return True

    def preview(self, target: DropTarget | None) -> bool | None:
        """ハイライト用: target に置けるなら True、置けないなら False、範囲外/非ドラッグは None。"""
        if self._box_id is None or target is None:
            return None
        if isinstance(target, StagingTarget):
            return True
        return self.board.can_place(self._box_id, target.tower)

    def release(self, target: DropTarget | None) -> DropOutcome | None:
        """mouse up。target が None(しきい値外・ウィンドウ外)なら元位置へ戻す。Idle なら None。"""
        box_id, origin = self._box_id, self._origin
        if box_id is None or origin is None:
            return None
        self._box_id = self._origin = None
        if target is None:
            return DropOutcome(DropResult.RETURNED_OUT_OF_RANGE, box_id, origin)
        if isinstance(target, StagingTarget):
            loc = self.board.place_in_staging(box_id, preferred=target.slot)
            return DropOutcome(DropResult.PLACED, box_id, loc)
        try:
            loc_t = self.board.place_on_tower(box_id, target.tower)
        except IllegalPlacementError as e:
            return DropOutcome(DropResult.RETURNED_ILLEGAL, box_id, origin, e.reason)
        return DropOutcome(DropResult.PLACED, box_id, loc_t)

    def cancel(self) -> DropOutcome | None:
        """ウィンドウ外で mouse up した場合など(§4.5): illegal 扱いで元位置へ戻す。"""
        return self.release(None)


__all__ = [
    "DragController",
    "DragState",
    "DropOutcome",
    "DropResult",
    "DropTarget",
    "StagingTarget",
    "TowerTarget",
]
