"""ポインタ(マウス / タッチ)座標をドラッグ状態機械へ流す結線(仕様書 §4.3〜§4.5)。

Pyxel に依存しない。

Pyxel 依存層(`main.py`)は毎フレーム `feed(x, y, held, inside)` を呼ぶだけでよい。
押下・解放のエッジ検出、ピッキング(`SceneQuery.pick_box`)、床面追従点(`SceneQuery.floor_point`)、
ドロップ先の決定(`layout.nearest_target`)、ハイライトの可否(`DragController.preview`)をここで行う。
効果音や演出は戻り値 `DropOutcome` を見て呼び出し側が行う。
"""

from __future__ import annotations

from typing import Protocol

from board_state import BoardState, InStaging, size_of, staging_slots_for
from input.drag import DragController, DropOutcome
from scene import layout
from scene.layout import DropTarget, StagingTarget

Vec = tuple[float, float, float]


class SceneQuery(Protocol):
    """3D シーンへの問い合わせ(`scene/board_scene.py` が実装する)。"""

    def pick_box(self, sx: float, sy: float) -> str | None:
        """画面座標のレイが最初に当たる箱 ID。無ければ None。"""
        ...

    def floor_point(self, sx: float, sy: float) -> Vec | None:
        """画面座標のレイとマット平面(y=0)の交点。平行・後方なら None。"""
        ...


class PointerDriver:
    """1 つの `DragController` をポインタ座標で駆動する。"""

    def __init__(self, drag: DragController, query: SceneQuery) -> None:
        self.drag = drag
        self.query = query
        self._held = False
        self._floor: Vec | None = None  # 最後に求まった床面追従点(レイが床を外れた間は保持)
        self._target: DropTarget | None = None
        self._preview: bool | None = None

    # ---- 参照(描画側が読む) ----

    @property
    def board(self) -> BoardState:
        return self.drag.board

    @property
    def dragging_box(self) -> str | None:
        return self.drag.dragging_box

    @property
    def target(self) -> DropTarget | None:
        """現在のドロップ候補(範囲外なら None)。"""
        return self._target

    @property
    def preview(self) -> bool | None:
        """候補に置けるなら True(緑)、置けないなら False(赤)、候補なしなら None。"""
        return self._preview

    @property
    def lifted_position(self) -> Vec | None:
        """ドラッグ中の箱の中心位置(§4.2: 床上の追従点 + 1 箱分)。ドラッグ中でなければ None。"""
        box_id = self.drag.dragging_box
        if box_id is None or self._floor is None:
            return None
        return layout.lifted_center(self.board, box_id, self._floor)

    # ---- 入力 ----

    def feed(self, sx: float, sy: float, held: bool, inside: bool = True) -> DropOutcome | None:
        """毎フレーム呼ぶ。ボタンの押下/解放エッジを検出して press / move / release を行う。

        `inside=False`(ポインタがウィンドウ外)のまま解放されたら範囲外扱いで戻す(§4.5)。
        """
        outcome: DropOutcome | None = None
        if held and not self._held:
            self.press(sx, sy)
        elif held:
            self.move(sx, sy)
        elif self._held:
            outcome = self.release(sx, sy) if inside else self.leave()
        self._held = held
        return outcome

    def press(self, sx: float, sy: float) -> bool:
        """mouse down。掴める箱の上なら Dragging に入る。"""
        if not self.drag.press(self.query.pick_box(sx, sy)):
            return False
        self._floor = self._floor_or_origin(sx, sy)
        self._update_target()
        return True

    def move(self, sx: float, sy: float) -> None:
        """ドラッグ中のポインタ移動。床面追従点とドロップ候補を更新する。"""
        if not self.drag.is_dragging:
            return
        point = self.query.floor_point(sx, sy)
        if point is not None:
            self._floor = point
        self._update_target()

    def release(self, sx: float, sy: float) -> DropOutcome | None:
        """mouse up。最寄りの塔 / スロット(しきい値内)へドロップする。"""
        if not self.drag.is_dragging:
            return None
        self.move(sx, sy)
        return self._finish(self.drag.release(self._target))

    def leave(self) -> DropOutcome | None:
        """ウィンドウ外で解放された(§4.5): 元位置へ戻す。"""
        return self._finish(self.drag.cancel())

    # ---- 内部 ----

    def _floor_or_origin(self, sx: float, sy: float) -> Vec:
        point = self.query.floor_point(sx, sy)
        if point is not None:
            return point
        box_id = self.drag.dragging_box
        assert box_id is not None
        x, _, z = layout.box_center(self.board, box_id)
        return (x, 0.0, z)

    def _update_target(self) -> None:
        target = layout.nearest_target(self._floor) if self._floor is not None else None
        self._target = self._resolve_staging(target)
        self._preview = self.drag.preview(self._target)

    def _resolve_staging(self, target: DropTarget | None) -> DropTarget | None:
        """待機スロットは実際に箱が収まるスロット(自サイズ列の空き)に置き換える。

        ハイライトが「置ける場所」を指し、埋まっているスロットや他サイズ列を指さないようにする
        (`BoardState.place_in_staging` と同じ解決規則: 指定 → 元スロット → 列の若い空き)。
        """
        box_id = self.drag.dragging_box
        if not isinstance(target, StagingTarget) or box_id is None:
            return target
        # ドラッグ中の箱はまだ元スロットにいるので、自分を除いた占有で判定する
        occupied = {slot for slot, b in self.board.staging_occupancy().items() if b != box_id}
        candidates = staging_slots_for(size_of(box_id))
        if target.slot in candidates and target.slot not in occupied:
            return target
        origin = self.drag.origin
        if isinstance(origin, InStaging):
            return StagingTarget(origin.slot)
        return StagingTarget(next(s for s in candidates if s not in occupied))

    def _finish(self, outcome: DropOutcome | None) -> DropOutcome | None:
        self._floor = None
        self._target = None
        self._preview = None
        return outcome
