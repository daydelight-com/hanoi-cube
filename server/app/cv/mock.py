"""モックCV: キーボード操作で論理盤面を作り、cv-interface 準拠の検出結果を出す。

実CV(S8)との差し替え可能性を保証する縮退経路でもある(development_plan.md §8)。
本番でCVが不安定な場合はこのモックをスタッフ操作に切り替えて興行を成立させるため、
S0以降も削除しない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import pairwise

from app.core.board import format_board, parse_board
from app.cv.interface import (
    BOX_EDGE_MM,
    BOX_IDS,
    BOX_SIZE_OF,
    SIZE_CHAR,
    Area,
    BoxId,
    BoxObservation,
    BoxSize,
    CvBoardUpdate,
    CvFrame,
    CvMessage,
    Violation,
)

# モックが合成するマット座標系レイアウト(mm)。実CVではキャリブレーションで決まる
MAT_SIZE_MM = (600.0, 400.0)
TOWER_X_MM: dict[str, float] = {"A": 150.0, "B": 300.0, "C": 450.0}
TOWER_Y_MM = 280.0
STAGING_Y_MM = 80.0
STAGING_X0_MM = 60.0
STAGING_PITCH_MM = 60.0
HELD_POS_MM = (300.0, 180.0, 120.0)  # 掴んでいる箱の合成位置(宙に浮かせる)

_SIZE_ORDER: dict[BoxSize, int] = {"large": 3, "medium": 2, "small": 1}
_TOWERS: tuple[str, str, str] = ("A", "B", "C")


@dataclass
class _State:
    stacks: dict[str, list[BoxId]] = field(
        default_factory=lambda: {"A": [], "B": [], "C": []}
    )  # 塔ごとの box_id 列(下から上)
    staging: list[BoxId] = field(default_factory=lambda: list(BOX_IDS))  # 待機エリアの box_id
    held: BoxId | None = None


class MockCv:
    """cv-interface.md 準拠の CvSource 実装(キーボード/プログラム操作)。"""

    def __init__(self) -> None:
        self._state = _State()
        self._t_ms = 0
        self._pending: list[CvMessage] = []
        self._last_board: CvBoardUpdate | None = None
        # 初期盤面(全箱待機)も確定盤面として初回 poll() で配信する(cv-interface.md §3)
        self._emit_board_if_changed()

    # ---- 操作(モックCLI・テストから呼ぶ) ----

    def grab(self, box_id: str) -> None:
        """箱を掴む。塔の途中の箱も掴める(上の箱は下に詰める)。"""
        if box_id not in BOX_IDS:
            raise ValueError(f"unknown box: {box_id}")
        box = box_id  # in チェックで BoxId に絞り込まれる
        if self._state.held is not None:
            raise ValueError(f"already holding {self._state.held}")
        for stack in self._state.stacks.values():
            if box in stack:
                stack.remove(box)
                break
        else:
            self._state.staging.remove(box)
        self._state.held = box
        self._emit_board_if_changed()

    def place(self, target: str) -> None:
        """掴んでいる箱を塔 A/B/C または待機エリア(W)に置く。違反配置も許す。"""
        held = self._state.held
        if held is None:
            raise ValueError("not holding any box")
        if target in _TOWERS:
            self._state.stacks[target].append(held)
        elif target == "W":
            self._state.staging.append(held)
        else:
            raise ValueError(f"invalid target: {target!r} (expected A/B/C/W)")
        self._state.held = None
        self._emit_board_if_changed()

    def set_board(self, board: str) -> None:
        """論理盤面を一括セットする。盤面に使わない箱は待機エリアへ。

        塔文字列は任意の [LMS]* を受け付ける(違反盤面のテスト用)。
        各サイズ3個の物理制約は超えられない。
        """
        towers = parse_board(board)
        pool: dict[str, list[BoxId]] = {"L": [], "M": [], "S": []}
        for box_id in BOX_IDS:
            pool[SIZE_CHAR[BOX_SIZE_OF[box_id]]].append(box_id)
        stacks: dict[str, list[BoxId]] = {}
        for name, tower in zip(_TOWERS, towers, strict=True):
            stack: list[BoxId] = []
            for ch in tower:
                if not pool[ch]:
                    raise ValueError(f"board {board!r} needs more than 3 boxes of size {ch}")
                stack.append(pool[ch].pop(0))
            stacks[name] = stack
        self._state = _State(
            stacks=stacks,
            staging=[b for sizes in pool.values() for b in sizes],
            held=None,
        )
        self._emit_board_if_changed()

    # ---- CvSource ----

    def poll(self) -> list[CvMessage]:
        self._t_ms += 33  # 約30fps相当で時刻を進める
        # 先に発生した確定盤面イベント → 最新フレーム の時系列順で返す
        messages: list[CvMessage] = [*self._pending, self._frame()]
        self._pending.clear()
        return messages

    @property
    def last_board(self) -> CvBoardUpdate | None:
        """最新の確定盤面(スナップショット用)。"""
        return self._last_board

    # ---- 内部 ----

    def _frame(self) -> CvFrame:
        boxes = []
        for tower, stack in self._state.stacks.items():
            z = 0.0
            for level, box_id in enumerate(stack):
                boxes.append(
                    self._observe(box_id, tower, level, (TOWER_X_MM[tower], TOWER_Y_MM, z))
                )
                z += BOX_EDGE_MM[BOX_SIZE_OF[box_id]]
        for slot, box_id in enumerate(self._state.staging):
            pos = (STAGING_X0_MM + slot * STAGING_PITCH_MM, STAGING_Y_MM, 0.0)
            boxes.append(self._observe(box_id, "staging", None, pos))
        if self._state.held is not None:
            boxes.append(self._observe(self._state.held, None, None, HELD_POS_MM))
        boxes.sort(key=lambda b: BOX_IDS.index(b.box_id))
        return CvFrame(t_ms=self._t_ms, mat_corners_detected=4, boxes=boxes)

    def _observe(
        self,
        box_id: BoxId,
        area: Area | str | None,
        level: int | None,
        pos: tuple[float, float, float],
    ) -> BoxObservation:
        index = BOX_IDS.index(box_id)
        return BoxObservation(
            box_id=box_id,
            size=BOX_SIZE_OF[box_id],
            pos_mm=pos,
            area=area,  # type: ignore[arg-type]
            level=level,
            visible=True,
            seen_tag_ids=[index * 6, index * 6 + 1],  # 面1・面2のタグ(モックの合成値)
        )

    def _emit_board_if_changed(self) -> None:
        def tower_str(name: str) -> str:
            return "".join(SIZE_CHAR[BOX_SIZE_OF[b]] for b in self._state.stacks[name])

        towers = (tower_str("A"), tower_str("B"), tower_str("C"))
        violations = self._violations()
        update = CvBoardUpdate(
            t_ms=self._t_ms,
            towers=towers,
            board=format_board(towers),
            legal=not violations,
            violations=violations,
            staging_box_ids=sorted(self._state.staging, key=BOX_IDS.index),
        )
        last = self._last_board
        if last is not None and (last.towers, last.staging_box_ids) == (
            update.towers,
            update.staging_box_ids,
        ):
            return
        self._last_board = update
        self._pending.append(update)

    def _violations(self) -> list[Violation]:
        violations: list[Violation] = []
        for tower, stack in self._state.stacks.items():
            sizes = [BOX_SIZE_OF[b] for b in stack]
            if any(
                _SIZE_ORDER[upper] >= _SIZE_ORDER[lower]
                for lower, upper in pairwise(sizes)
                if upper != lower
            ):
                violations.append(Violation(tower=tower, type="size_order"))  # type: ignore[arg-type]
            if len(set(sizes)) < len(sizes):
                violations.append(Violation(tower=tower, type="duplicate_size"))  # type: ignore[arg-type]
            if len(stack) > 3:
                violations.append(Violation(tower=tower, type="overflow"))  # type: ignore[arg-type]
        return violations
