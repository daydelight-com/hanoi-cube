"""9 箱の所在(塔 or 待機スロット)→ 盤面文字列、配置ルール検証、塔の top 判定。

仕様書 §4.2 / §4.4 / §4.6。

Pyxel に依存しない。盤面文字列のユーティリティは `app.core.board`(既存)を import して使う。
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Final

from app.core.board import (
    Size,
    Tower,
    board_index,
    format_board,
    is_legal_board,
    parse_board,
)

SIZES: Final[tuple[Size, Size, Size]] = ("L", "M", "S")
TOWERS: Final[tuple[Tower, Tower, Tower]] = ("A", "B", "C")
BOX_EDGE_MM: Final[Mapping[Size, float]] = {"L": 75.0, "M": 50.0, "S": 30.0}
MAX_STACK: Final = 3
BOXES_PER_SIZE: Final = 3

# 箱 ID: サイズ文字 + 1〜3("L1" .. "S3")。各サイズ 3 個、計 9 個
BOX_IDS: Final[tuple[str, ...]] = tuple(f"{size}{n}" for size in SIZES for n in (1, 2, 3))
STAGING_SLOT_COUNT: Final = len(BOX_IDS)


def size_of(box_id: str) -> Size:
    """箱 ID からサイズ文字を得る。"""
    if box_id not in BOX_IDS:
        raise ValueError(f"unknown box id: {box_id!r}")
    size: Size = box_id[0]  # type: ignore[assignment]
    return size


def _require_box(box_id: str) -> str:
    if box_id not in BOX_IDS:
        raise ValueError(f"unknown box id: {box_id!r}")
    return box_id


def _require_tower(tower: str) -> Tower:
    if tower not in TOWERS:
        raise ValueError(f"unknown tower: {tower!r}")
    return tower


def staging_slots_for(size: Size) -> tuple[int, int, int]:
    """サイズごとの待機スロット列(仕様書 §4.1「サイズごとに 3 列」)。L=0..2, M=3..5, S=6..8。"""
    base = SIZES.index(size) * BOXES_PER_SIZE
    return (base, base + 1, base + 2)


def slot_size(slot: int) -> Size:
    """待機スロット番号が属するサイズ列。"""
    if not 0 <= slot < STAGING_SLOT_COUNT:
        raise ValueError(f"staging slot out of range: {slot}")
    return SIZES[slot // BOXES_PER_SIZE]


@dataclass(frozen=True)
class OnTower:
    """塔上の所在。level は下から 0 始まり。"""

    tower: Tower
    level: int


@dataclass(frozen=True)
class InStaging:
    """待機エリアの所在。slot は 0〜8。"""

    slot: int


Location = OnTower | InStaging


class RejectReason(Enum):
    """塔への配置を拒否する理由(仕様書 §4.4、ルールブック §3)。"""

    TOWER_FULL = "tower_full"  # 4 個目
    SAME_SIZE = "same_size"  # 同じサイズが同じ塔にある
    LARGER_ON_SMALLER = "larger_on_smaller"  # 大を小の上


class IllegalPlacementError(ValueError):
    def __init__(self, reason: RejectReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class BoardState:
    """9 箱の所在を持つ可変モデル。塔上の配置は常に合法盤面に保たれる。"""

    def __init__(self, locations: Mapping[str, Location]) -> None:
        if set(locations) != set(BOX_IDS):
            raise ValueError("locations must cover exactly the 9 box ids")
        self._loc: dict[str, Location] = dict(locations)
        self._check_consistent()

    # ---- 生成 ----

    @classmethod
    def initial(cls) -> BoardState:
        """ゲーム開始時: 全箱が待機エリア(サイズ列の順)。"""
        locs: dict[str, Location] = {}
        for size in SIZES:
            for n, slot in enumerate(staging_slots_for(size), start=1):
                locs[f"{size}{n}"] = InStaging(slot)
        return cls(locs)

    @classmethod
    def from_board(cls, board: str) -> BoardState:
        """盤面文字列から復元する。塔に無い箱はサイズ列の空きスロットへ置く。

        同サイズの箱は区別が無いので、塔 A→B→C の順に若い番号を割り当てる。
        """
        if not is_legal_board(board):
            raise ValueError(f"illegal board: {board!r}")
        locs: dict[str, Location] = {}
        next_n: dict[Size, int] = dict.fromkeys(SIZES, 1)
        for tower, stack in zip(TOWERS, parse_board(board), strict=True):
            for level, ch in enumerate(stack):
                size: Size = ch  # type: ignore[assignment]
                locs[f"{size}{next_n[size]}"] = OnTower(tower, level)
                next_n[size] += 1
        for size in SIZES:
            slots = iter(staging_slots_for(size))
            for n in range(next_n[size], BOXES_PER_SIZE + 1):
                locs[f"{size}{n}"] = InStaging(next(slots))
        return cls(locs)

    # ---- 参照 ----

    def location(self, box_id: str) -> Location:
        return self._loc[_require_box(box_id)]

    def locations(self) -> Mapping[str, Location]:
        return dict(self._loc)

    def __iter__(self) -> Iterator[str]:
        return iter(BOX_IDS)

    def tower_stack(self, tower: Tower) -> list[str]:
        """塔上の箱 ID を下から上の順に返す。"""
        stack = sorted(
            (
                (loc.level, box_id)
                for box_id, loc in self._loc.items()
                if isinstance(loc, OnTower) and loc.tower == tower
            ),
        )
        return [box_id for _, box_id in stack]

    def tower_string(self, tower: Tower) -> str:
        return "".join(size_of(b) for b in self.tower_stack(tower))

    def board_string(self) -> str:
        """盤面文字列(待機エリアの箱は含まない)。§4.4 のガードにより常に合法。"""
        board = format_board([self.tower_string(t) for t in TOWERS])
        assert is_legal_board(board), board
        return board

    def board_index(self) -> int:
        return board_index(self.board_string())

    def top_of(self, tower: Tower) -> str | None:
        """塔の一番上の箱 ID。空塔は None。"""
        stack = self.tower_stack(tower)
        return stack[-1] if stack else None

    def is_pickable(self, box_id: str) -> bool:
        """掴める箱か(§4.2): 待機エリアの箱は全部、塔上は一番上だけ。"""
        loc = self._loc[_require_box(box_id)]
        if isinstance(loc, InStaging):
            return True
        return self.top_of(loc.tower) == box_id

    def staging_occupancy(self) -> dict[int, str]:
        return {loc.slot: box_id for box_id, loc in self._loc.items() if isinstance(loc, InStaging)}

    def free_staging_slot(
        self, size: Size, preferred: int | None = None, fallback: int | None = None
    ) -> int:
        """size の列の空きスロット。preferred → fallback → 列の若い順で最初に空いているもの。"""
        occupied = self.staging_occupancy()
        candidates = staging_slots_for(size)
        for wanted in (preferred, fallback):
            if wanted is not None and wanted in candidates and wanted not in occupied:
                return wanted
        for slot in candidates:
            if slot not in occupied:
                return slot
        raise RuntimeError(f"no free staging slot for size {size}")  # 不変条件上起きない

    # ---- 配置ルール ----

    def check_place(self, box_id: str, tower: Tower) -> RejectReason | None:
        """box_id を tower の一番上に置けるか。置けるなら None、置けないなら理由。

        掴んでいる箱自身が同じ塔の top にある場合は、いったん外した状態で判定する。
        """
        size = size_of(box_id)
        stack = [b for b in self.tower_stack(_require_tower(tower)) if b != box_id]
        if len(stack) >= MAX_STACK:
            return RejectReason.TOWER_FULL
        if any(size_of(b) == size for b in stack):
            return RejectReason.SAME_SIZE
        if stack and BOX_EDGE_MM[size] > BOX_EDGE_MM[size_of(stack[-1])]:
            return RejectReason.LARGER_ON_SMALLER
        return None

    def can_place(self, box_id: str, tower: Tower) -> bool:
        return self.check_place(box_id, tower) is None

    # ---- 更新 ----

    def place_on_tower(self, box_id: str, tower: Tower) -> OnTower:
        """box_id を tower の一番上に移す。違反時は IllegalPlacementError(盤面は変化しない)。"""
        reason = self.check_place(box_id, tower)
        if reason is not None:
            raise IllegalPlacementError(reason)
        self._detach(box_id)
        loc = OnTower(tower, len(self.tower_stack(tower)))
        self._loc[box_id] = loc
        return loc

    def place_in_staging(self, box_id: str, preferred: int | None = None) -> InStaging:
        """box_id を待機エリア(同サイズ列の空きスロット)へ移す。常に成功する。"""
        current = self._loc[_require_box(box_id)]
        self._detach(box_id)
        # 指定スロットが使えなければ元のスロット(待機にいた場合)→ 列の若い空き、の順
        fallback = current.slot if isinstance(current, InStaging) else None
        loc = InStaging(self.free_staging_slot(size_of(box_id), preferred, fallback))
        self._loc[box_id] = loc
        return loc

    def move(self, box_id: str, location: Location) -> None:
        """所在を直接書き換える(復元用)。整合性を検証する。"""
        backup = dict(self._loc)
        self._loc[_require_box(box_id)] = location
        try:
            self._check_consistent()
        except ValueError:
            self._loc = backup
            raise

    # ---- 内部 ----

    def _detach(self, box_id: str) -> None:
        loc = self._loc[box_id]
        if isinstance(loc, OnTower) and self.top_of(loc.tower) != box_id:
            raise ValueError(f"{box_id} is not on top of tower {loc.tower}")
        self._loc[box_id] = _DETACHED

    def _check_consistent(self) -> None:
        # 待機スロットの重複・サイズ列の一致
        seen_slots: set[int] = set()
        for box_id, loc in self._loc.items():
            if isinstance(loc, OnTower):
                _require_tower(loc.tower)
            elif isinstance(loc, InStaging):
                if loc.slot in seen_slots:
                    raise ValueError(f"staging slot {loc.slot} used twice")
                if slot_size(loc.slot) != size_of(box_id):
                    raise ValueError(f"{box_id} in wrong staging column {loc.slot}")
                seen_slots.add(loc.slot)
        # 塔: level が 0..n-1 で連続し、盤面が合法
        for tower in TOWERS:
            levels = sorted(
                loc.level
                for loc in self._loc.values()
                if isinstance(loc, OnTower) and loc.tower == tower
            )
            if levels != list(range(len(levels))):
                raise ValueError(f"tower {tower} levels not contiguous: {levels}")
        board = format_board([self.tower_string(t) for t in TOWERS])
        if not is_legal_board(board):
            raise ValueError(f"illegal board: {board}")


# 一時的に「どこにも無い」印。_detach と再配置の間でのみ使う(外部には露出しない)
_DETACHED: Location = InStaging(-1)
