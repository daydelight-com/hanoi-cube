"""mm → ワールド座標、塔・待機スロット座標(仕様書 §4.1)。Pyxel に依存しない。

数値は `frontend/src/three/layout.ts`(A3 横置き 420x297mm)の写し。変更する場合は両方を合わせる。

- マット座標系(cv-interface.md §2): 左手前隅が原点、x=右、y=奥、z=上(mm)
- ワールド座標系(Cube): マット中心が原点、x=右、y=上、z=手前(カメラ側)。単位は m 相当(mm x 1/100)
    world.x = (mat.x - W/2) * S / world.y = mat.z * S / world.z = -(mat.y - H/2) * S
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final

from app.core.board import Size, Tower
from board_state import (
    BOX_EDGE_MM,
    STAGING_SLOT_COUNT,
    TOWERS,
    BoardState,
    InStaging,
    Location,
    OnTower,
    size_of,
)

Vec = tuple[float, float, float]

# ---- layout.ts の定数(mm) ----
MAT_SIZE_MM: Final[tuple[float, float]] = (420.0, 297.0)
_W, _H = MAT_SIZE_MM
TOWER_X_MM: Final[dict[Tower, float]] = {"A": _W / 4, "B": _W / 2, "C": _W * 3 / 4}
TOWER_Y_MM: Final = _H * 0.7
STAGING_Y_MM: Final = _H * 0.2
STAGING_X0_MM: Final = _W * 0.1
STAGING_PITCH_MM: Final = _W * 0.1
# ↑ の待機エリア 3 定数は layout.ts / mock CV の参照値(数値一致テストの対象)。
# Pyxel 版の待機スロット配置には使わない: 42mm ピッチ一列では L 箱(75mm)が隣と重なるため、
# 2 段に分ける(P3 要判断 #1)。
#   手前段(y = 0.15H ≈ 45mm): L 列 3 スロット、ピッチ 85mm(箱 75 + 隙間 10)、マット中央に寄せる
#   奥段(y = 0.40H ≈ 119mm): M 列 3 スロット(ピッチ 58)+ S 列 3 スロット(ピッチ 38)、
#   列間 10mm、全体を中央寄せ
# 背の高い L を手前(カメラ側)に置くと、奥の塔やスロットを隠さない(L を奥段にすると塔 B の足元が
# L の上面に隠れる)。手前段 L の背面 = 45 + 37.5 = 82mm、奥段 M の前面 = 119 - 25 = 94mm、
# 奥段 M の背面 = 144mm、塔上 L の前面 = 208 - 37.5 = 170mm で、いずれも重ならない。
STAGING_FRONT_Y_MM: Final = _H * 0.15
STAGING_BACK_Y_MM: Final = _H * 0.40
_GAP_MM: Final = 8.0  # 同サイズ列内の箱の隙間
_GROUP_GAP_MM: Final = 10.0  # M 列と S 列の間


def _row_centers(edges: list[float], start_x: float) -> list[float]:
    xs: list[float] = []
    x = start_x
    for e in edges:
        xs.append(x + e / 2)
        x += e + _GAP_MM
    return xs


_L_EDGE, _M_EDGE, _S_EDGE = (BOX_EDGE_MM[s] for s in ("L", "M", "S"))
_L_PITCH_MM = _L_EDGE + _GAP_MM + 2.0  # 85mm(L は隙間を 2mm 広げる)
_FRONT_SPAN = (3 * _M_EDGE + 2 * _GAP_MM) + _GROUP_GAP_MM + (3 * _S_EDGE + 2 * _GAP_MM)
STAGING_L_X_MM: Final[tuple[float, ...]] = tuple(_W / 2 + (i - 1) * _L_PITCH_MM for i in range(3))
_FRONT_X0 = (_W - _FRONT_SPAN) / 2
STAGING_M_X_MM: Final[tuple[float, ...]] = tuple(_row_centers([_M_EDGE] * 3, _FRONT_X0))
STAGING_S_X_MM: Final[tuple[float, ...]] = tuple(
    _row_centers([_S_EDGE] * 3, _FRONT_X0 + 3 * _M_EDGE + 2 * _GAP_MM + _GROUP_GAP_MM)
)
# slot 0..8 → (x_mm, y_mm)。列の割り当ては board_state.staging_slots_for と同じ
# (L=0..2, M=3..5, S=6..8)
STAGING_SLOT_MM: Final[tuple[tuple[float, float], ...]] = (
    *((x, STAGING_FRONT_Y_MM) for x in STAGING_L_X_MM),
    *((x, STAGING_BACK_Y_MM) for x in STAGING_M_X_MM),
    *((x, STAGING_BACK_Y_MM) for x in STAGING_S_X_MM),
)

# ---- スケール(仕様書 §4.1「1/100 スケール」) ----
MM_TO_WORLD: Final = 0.01

# ドロップ先の距離しきい値(§4.4)。塔間隔 105mm の半分弱(cv/layout.py の TOWER_HALF_X_MM と同値)
DROP_THRESHOLD_MM: Final = _W / 8 - 5.0


def mm(value: float) -> float:
    """mm → ワールド単位。"""
    return value * MM_TO_WORLD


def mat_to_world(x_mm: float, y_mm: float, z_mm: float = 0.0) -> Vec:
    """マット座標(mm)→ ワールド座標(layout.ts の matPosToThree と同じ写像 + 1/100)。"""
    return (mm(x_mm - _W / 2), mm(z_mm), -mm(y_mm - _H / 2))


def world_to_mat(wx: float, wy: float, wz: float) -> Vec:
    """ワールド座標 → マット座標(mm)。mat_to_world の逆。"""
    return (wx / MM_TO_WORLD + _W / 2, -wz / MM_TO_WORLD + _H / 2, wy / MM_TO_WORLD)


def tower_position(tower: Tower) -> Vec:
    """塔の床面中心(ワールド)。"""
    return mat_to_world(TOWER_X_MM[tower], TOWER_Y_MM)


def staging_slot_position(slot: int) -> Vec:
    """待機スロットの床面中心(ワールド)。手前段に L 列、奥段に M 列 + S 列(`STAGING_SLOT_MM`)。"""
    if not 0 <= slot < STAGING_SLOT_COUNT:
        raise ValueError(f"staging slot out of range: {slot}")
    x_mm, y_mm = STAGING_SLOT_MM[slot]
    return mat_to_world(x_mm, y_mm)


def box_edge(size: Size) -> float:
    """箱の一辺(ワールド)。"""
    return mm(BOX_EDGE_MM[size])


def stack_height_mm(stack_sizes: list[Size]) -> float:
    return sum(BOX_EDGE_MM[s] for s in stack_sizes)


def box_center(state: BoardState, box_id: str) -> Vec:
    """箱の中心位置(ワールド)。塔上は下の箱の高さ分だけ持ち上がる。"""
    return box_center_at(state, box_id, state.location(box_id))


def box_center_at(state: BoardState, box_id: str, location: Location) -> Vec:
    """box_id が location にあるとしたときの中心位置(ワールド)。"""
    size = size_of(box_id)
    half = BOX_EDGE_MM[size] / 2
    if isinstance(location, InStaging):
        x, _, z = staging_slot_position(location.slot)
        return (x, mm(half), z)
    below = state.tower_stack(location.tower)[: location.level]
    below_sizes: list[Size] = [size_of(b) for b in below if b != box_id]
    base = stack_height_mm(below_sizes)
    x, _, z = tower_position(location.tower)
    return (x, mm(base + half), z)


def lifted_center(state: BoardState, box_id: str, floor_point: Vec) -> Vec:
    """ドラッグ中の箱の中心(§4.2: 床上の追従点に対し y を +1 箱分持ち上げる)。"""
    edge = box_edge(size_of(box_id))
    return (floor_point[0], edge * 1.5, floor_point[2])


# ---- ドロップ先 ----


@dataclass(frozen=True)
class TowerTarget:
    tower: Tower


@dataclass(frozen=True)
class StagingTarget:
    slot: int


DropTarget = TowerTarget | StagingTarget


def _dist_xz(a: Vec, b: Vec) -> float:
    return math.hypot(a[0] - b[0], a[2] - b[2])


def nearest_target(point: Vec, threshold_mm: float = DROP_THRESHOLD_MM) -> DropTarget | None:
    """床面上の点(ワールド)に最も近い塔または待機スロット。しきい値より遠ければ None(範囲外)。"""
    best: DropTarget | None = None
    best_d = mm(threshold_mm)
    for tower in TOWERS:
        d = _dist_xz(point, tower_position(tower))
        if d <= best_d:
            best, best_d = TowerTarget(tower), d
    for slot in range(STAGING_SLOT_COUNT):
        d = _dist_xz(point, staging_slot_position(slot))
        if d <= best_d:
            best, best_d = StagingTarget(slot), d
    return best


def target_of(location: Location) -> DropTarget:
    """所在 → それを含むドロップ先。"""
    if isinstance(location, OnTower):
        return TowerTarget(location.tower)
    return StagingTarget(location.slot)
