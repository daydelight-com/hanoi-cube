"""scene.layout のテスト: layout.ts との数値一致、mm → ワールド、最近傍スロット。"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from board_state import BoardState, InStaging, OnTower
from scene import layout
from scene.layout import (
    MM_TO_WORLD,
    StagingTarget,
    TowerTarget,
    box_center,
    box_center_at,
    lifted_center,
    mat_to_world,
    nearest_target,
    staging_slot_position,
    target_of,
    tower_position,
    world_to_mat,
)

LAYOUT_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "three" / "layout.ts"


def _approx(v: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(round(x, 9) for x in v)  # type: ignore[return-value]


def test_constants_match_layout_ts() -> None:
    """layout.ts の mm 定数を正規表現で読み取り、写しと一致することを確かめる。"""
    src = LAYOUT_TS.read_text(encoding="utf-8")
    m = re.search(r"MAT_SIZE_MM = \{ x: (\d+), y: (\d+) \}", src)
    assert m is not None
    assert (float(m[1]), float(m[2])) == layout.MAT_SIZE_MM
    w, h = layout.MAT_SIZE_MM
    # 各定数の導出式が layout.ts に現れ、同じ式で求めた値と一致する
    derived = {
        r"A: MAT_SIZE_MM\.x / 4": (layout.TOWER_X_MM["A"], w / 4),
        r"B: MAT_SIZE_MM\.x / 2": (layout.TOWER_X_MM["B"], w / 2),
        r"C: \(MAT_SIZE_MM\.x \* 3\) / 4": (layout.TOWER_X_MM["C"], w * 3 / 4),
        r"TOWER_Y_MM = MAT_SIZE_MM\.y \* 0\.7": (layout.TOWER_Y_MM, h * 0.7),
        r"STAGING_Y_MM = MAT_SIZE_MM\.y \* 0\.2": (layout.STAGING_Y_MM, h * 0.2),
        r"STAGING_X0_MM = MAT_SIZE_MM\.x \* 0\.1": (layout.STAGING_X0_MM, w * 0.1),
        r"STAGING_PITCH_MM = MAT_SIZE_MM\.x \* 0\.1": (layout.STAGING_PITCH_MM, w * 0.1),
    }
    for pattern, (actual, expected) in derived.items():
        assert re.search(pattern, src), pattern
        assert actual == expected, pattern


def test_numeric_values_a3() -> None:
    assert layout.TOWER_X_MM == {"A": 105.0, "B": 210.0, "C": 315.0}
    values = (layout.TOWER_Y_MM, layout.STAGING_Y_MM, layout.STAGING_X0_MM, layout.STAGING_PITCH_MM)
    assert values == pytest.approx((207.9, 59.4, 42.0, 42.0))


def test_mat_to_world_matches_layout_test_ts() -> None:
    """frontend/src/three/layout.test.ts の期待値 x 1/100。"""
    assert _approx(mat_to_world(210, 148.5, 0)) == (0.0, 0.0, 0.0)
    x, y, z = mat_to_world(0, 0, 0)
    assert (x, y, z) == pytest.approx((-2.10, 0.0, 1.485))
    x, y, z = mat_to_world(layout.TOWER_X_MM["C"], layout.TOWER_Y_MM, 75)
    assert (x, y, z) == pytest.approx((1.05, 0.75, -0.594))


def test_world_to_mat_roundtrip() -> None:
    for p in ((0.0, 0.0, 0.0), (123.4, 56.7, 89.0), (420.0, 297.0, 75.0)):
        assert world_to_mat(*mat_to_world(*p)) == pytest.approx(p)


def test_tower_and_slot_positions() -> None:
    assert tower_position("B") == pytest.approx((0.0, 0.0, -0.594))
    assert tower_position("A")[0] == pytest.approx(-1.05)
    assert staging_slot_position(0) == pytest.approx((-1.68, 0.0, 0.891))
    assert staging_slot_position(8)[0] == pytest.approx(-1.68 + 8 * 0.42)
    # 待機エリアは塔より手前(+z)
    assert staging_slot_position(4)[2] > tower_position("B")[2]
    with pytest.raises(ValueError):
        staging_slot_position(9)


def test_box_center_stacking() -> None:
    state = BoardState.from_board("LMS//")
    lx, ly, lz = box_center(state, "L1")
    assert (lx, lz) == pytest.approx(tower_position("A")[0::2])
    assert ly == pytest.approx(0.375)
    assert box_center(state, "M1")[1] == pytest.approx(0.75 + 0.25)
    assert box_center(state, "S1")[1] == pytest.approx(1.25 + 0.15)
    # 待機エリアの箱は床に接する
    assert box_center(state, "L2")[1] == pytest.approx(0.375)
    # S1 が塔上なので S2, S3 は S 列の若いスロット(6, 7)に入る
    sx, _, sz = staging_slot_position(7)
    assert box_center(state, "S3") == pytest.approx((sx, 0.15, sz))
    # 仮想位置: 自分を除いた高さで計算する
    assert box_center_at(state, "S1", OnTower("B", 0))[1] == pytest.approx(0.15)
    assert box_center_at(state, "S1", InStaging(7))[0] == pytest.approx(staging_slot_position(7)[0])


def test_lifted_center() -> None:
    state = BoardState.initial()
    assert lifted_center(state, "L1", (0.3, 0.0, 0.2)) == pytest.approx((0.3, 0.75 * 1.5, 0.2))


def test_nearest_target() -> None:
    assert nearest_target(tower_position("A")) == TowerTarget("A")
    assert nearest_target(staging_slot_position(5)) == StagingTarget(5)
    # 塔 A から 40mm 右 → まだ A(しきい値 47.5mm 以内)
    ax, _, az = tower_position("A")
    assert nearest_target((ax + 0.40, 0.0, az)) == TowerTarget("A")
    # 塔 A と B の中間(52.5mm)はどちらにも届かない
    assert nearest_target((ax + 0.525, 0.0, az)) is None
    # マット外
    assert nearest_target((5.0, 0.0, 5.0)) is None
    # しきい値を広げれば届く
    wide = nearest_target((ax + 0.525, 0.0, az), threshold_mm=60)
    assert wide in (TowerTarget("A"), TowerTarget("B"))
    # スロット間は 42mm なので隣との中点 21mm は近い方
    s0 = staging_slot_position(0)
    assert nearest_target((s0[0] + 0.20, 0.0, s0[2])) == StagingTarget(0)
    assert nearest_target((s0[0] + 0.22, 0.0, s0[2])) == StagingTarget(1)


def test_target_of() -> None:
    assert target_of(OnTower("C", 2)) == TowerTarget("C")
    assert target_of(InStaging(4)) == StagingTarget(4)


def test_scale() -> None:
    assert MM_TO_WORLD == 0.01
    assert layout.box_edge("L") == pytest.approx(0.75)
