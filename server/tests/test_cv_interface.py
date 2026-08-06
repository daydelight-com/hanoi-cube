"""CvBoardUpdate の整合性バリデータ(契約: docs/contracts/cv-interface.md §3)。

`tower_box_ids` は記録画面の表示専用だが、盤面と食い違ったまま流れると
判定履歴に誤った箱構成が残るため、モデル側で不整合を弾く。
"""

from __future__ import annotations

import pytest
from app.cv.interface import CvBoardUpdate


def test_tower_box_ids_must_match_towers() -> None:
    with pytest.raises(ValueError, match="does not match towers"):
        CvBoardUpdate(
            t_ms=0,
            towers=("LMS", "", ""),
            board="LMS//",
            legal=True,
            tower_box_ids=(["large-1", "medium-1"], [], []),  # 小が足りない
        )


def test_box_cannot_be_in_two_towers() -> None:
    with pytest.raises(ValueError, match="more than one area"):
        CvBoardUpdate(
            t_ms=0,
            towers=("L", "", "L"),
            board="L//L",
            legal=True,
            tower_box_ids=(["large-1"], [], ["large-1"]),
        )


def test_box_cannot_be_in_a_tower_and_staging() -> None:
    with pytest.raises(ValueError, match="more than one area"):
        CvBoardUpdate(
            t_ms=0,
            towers=("L", "", ""),
            board="L//",
            legal=True,
            staging_box_ids=["large-1"],
            tower_box_ids=(["large-1"], [], []),
        )


def test_illegal_stack_is_accepted_when_box_ids_agree() -> None:
    # 違反配置(小の上に大)でも towers と一致していれば型としては通す
    update = CvBoardUpdate(
        t_ms=0,
        towers=("SL", "", ""),
        board="SL//",
        legal=False,
        tower_box_ids=(["small-1", "large-1"], [], []),
    )
    assert update.tower_box_ids[0] == ["small-1", "large-1"]
