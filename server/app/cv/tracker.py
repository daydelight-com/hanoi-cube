"""箱の追跡と論理盤面の構成(仕様§4.1-5〜6, §4.2)。純ロジック(カメラ・検出器非依存)。

ワーカー(worker.py)が毎フレームの箱観測(マット座標)を渡し、本モジュールが
  - ロスト保持: タグロスト中も最後の確定位置を LOST_HOLD_MS 保持して visible=false で送る
  - エリア分類: A/B/C/待機/None(移動中) と塔内の段(level)
  - 安定判定: 論理盤面が STABLE_MS 連続で同一になったら確定盤面として emit
を行い、cv-interface.md 準拠の CvFrame / CvBoardUpdate を返す。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

from app.core.board import format_board
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
from app.cv.layout import (
    MAT_SIZE_MM,
    STACK_GAP_TOL_MM,
    STAGING_PITCH_MM,
    STAGING_X0_MM,
    STAGING_Y_MAX_MM,
    STAGING_Y_MM,
    TOWER_HALF_X_MM,
    TOWER_HALF_Y_MM,
    TOWER_X_MM,
    TOWER_Y_MM,
)

LOST_HOLD_MS = 2000  # タグロスト時に最終確定位置を保持する時間(仕様§4.2)
STABLE_MS = 300  # 論理盤面の安定判定(仕様§4.1-6)
STABLE_MIN_FRAMES = 2  # 低fps時にも「連続で同一」の意味を保つ最少フレーム数

# 位置の平滑化(仕様§4.1-6)。連続観測中は指数移動平均でノイズを抑え、
# 大きく跳んだ場合(持ち替え・誤対応)は追従を優先して即座に置き換える
SMOOTHING_ALPHA = 0.5  # 新観測の重み
SMOOTHING_MAX_GAP_MS = 100  # これより観測が途切れたら平滑化をリセット
SMOOTHING_SNAP_MM = 100.0  # これ以上の変位は移動とみなして平滑化しない

# マット外への許容はみ出し(待機エリア判定用)。マット手前で持つ手の位置ゆらぎ対策
MAT_MARGIN_MM = 50.0

# 構造遮蔽の保持(仕様§4.2「直前までそのエリアで確定していた箱は動いていない」):
# 確定盤面で塔にあった箱は、上に別の箱が「接して載っている」間は2秒を超えても保持する。
# 「小の上に大」の違反配置では下の小箱がオーバーハングで恒久的に見えなくなるため、
# この推定が無いと違反検出が2秒で崩れる。覆い箱が持ち上げられて接触が切れたら
# (=本来タグが見えるはず)通常のロスト規則に戻す。
GHOST_SUPPORT_TOL_MM = 20.0  # 「接して載っている」とみなす z の許容(両側)
GHOST_OVERLAP_TOL_MM = 10.0  # 観測箱が保持スロットとこの量以上重なれば矛盾として解放

_SIZE_ORDER: dict[BoxSize, int] = {"large": 3, "medium": 2, "small": 1}
_TOWERS: tuple[str, str, str] = ("A", "B", "C")


def violations_for(stacks: dict[str, list[BoxSize]]) -> list[Violation]:
    """塔ごとのサイズ列(下から上)から配置ルール違反を列挙する(ルールブック§3)。"""
    violations: list[Violation] = []
    for tower, sizes in stacks.items():
        if any(
            _SIZE_ORDER[upper] >= _SIZE_ORDER[lower]
            for lower, upper in pairwise(sizes)
            if upper != lower
        ):
            violations.append(Violation(tower=tower, type="size_order"))  # type: ignore[arg-type]
        if len(set(sizes)) < len(sizes):
            violations.append(Violation(tower=tower, type="duplicate_size"))  # type: ignore[arg-type]
        if len(sizes) > 3:
            violations.append(Violation(tower=tower, type="overflow"))  # type: ignore[arg-type]
    return violations


@dataclass(frozen=True)
class BoxSighting:
    """1フレームでの1箱の観測(ワーカーが幾何解決した結果)。"""

    box_id: BoxId
    pos_mm: tuple[float, float, float]  # 底面中心
    seen_tag_ids: tuple[int, ...]
    yaw90_rad: float = 0.0  # 鉛直軸まわりの回転(mod 90°。geometry.box_estimate)


@dataclass
class _Track:
    pos_mm: tuple[float, float, float]
    last_seen_ms: int
    ever_seen: bool
    yaw_rad: float = 0.0  # 表示用ヨー(mod 90° の観測をフレーム間で展開した値)


def _default_pos(box_id: BoxId) -> tuple[float, float, float]:
    """一度も観測していない箱の表示用プレースホルダ位置(モックと同じ待機レイアウト)。"""
    slot = BOX_IDS.index(box_id)
    return (STAGING_X0_MM + slot * STAGING_PITCH_MM, STAGING_Y_MM, 0.0)


@dataclass
class _BoardSignature:
    towers: tuple[tuple[BoxId, ...], ...]
    staging: tuple[BoxId, ...]


class BoardTracker:
    """観測列から CvFrame / CvBoardUpdate を組み立てる状態機械。"""

    def __init__(self) -> None:
        self._tracks: dict[BoxId, _Track] = {
            box_id: _Track(pos_mm=_default_pos(box_id), last_seen_ms=-(10**9), ever_seen=False)
            for box_id in BOX_IDS
        }
        self._stable_since_ms: int | None = None
        self._stable_frames = 0
        self._stable_sig: _BoardSignature | None = None
        self._confirmed_sig: _BoardSignature | None = None
        self._last_board: CvBoardUpdate | None = None

    @property
    def last_board(self) -> CvBoardUpdate | None:
        return self._last_board

    def process(
        self,
        t_ms: int,
        sightings: Sequence[BoxSighting],
        mat_corners_detected: int,
        calibrated: bool,
    ) -> list[CvMessage]:
        """1フレーム分の観測を反映し、配信すべきメッセージを返す。

        calibrated=False の間(起動直後)は観測が得られないため、フレームのみ
        送って安定判定は進めない。
        """
        seen_now: dict[BoxId, BoxSighting] = {s.box_id: s for s in sightings}
        for box_id, sighting in seen_now.items():
            self._tracks[box_id] = self._updated_track(self._tracks[box_id], sighting, t_ms)

        present: dict[BoxId, tuple[float, float, float]] = {}
        for box_id, track in self._tracks.items():
            if track.ever_seen and t_ms - track.last_seen_ms <= LOST_HOLD_MS:
                present[box_id] = track.pos_mm
        self._add_structural_ghosts(present)

        area_level = self._classify(present)

        messages: list[CvMessage] = []
        if calibrated:
            messages.extend(self._update_stability(t_ms, area_level))
        messages.append(self._frame(t_ms, seen_now, area_level, mat_corners_detected))
        return messages

    # ---- 内部 ----

    @staticmethod
    def _updated_track(prev: _Track, sighting: BoxSighting, t_ms: int) -> _Track:
        """観測でトラックを更新する。連続観測中は位置を平滑化(仕様§4.1-6)。"""
        pos = sighting.pos_mm
        continuous = prev.ever_seen and t_ms - prev.last_seen_ms <= SMOOTHING_MAX_GAP_MS
        if continuous:
            dist = math.dist(prev.pos_mm, pos)
            if dist <= SMOOTHING_SNAP_MM:
                a = SMOOTHING_ALPHA
                pos = (
                    prev.pos_mm[0] * (1 - a) + pos[0] * a,
                    prev.pos_mm[1] * (1 - a) + pos[1] * a,
                    prev.pos_mm[2] * (1 - a) + pos[2] * a,
                )
        # ヨーは mod 90° の観測なので、前回値に最も近い同値類の代表を選ぶ
        # (正立付近のノイズで 1°⇔89° と表示が90°飛ぶのを防ぐ)
        quarter = math.pi / 2
        base = prev.yaw_rad if prev.ever_seen else 0.0
        k = round((base - sighting.yaw90_rad) / quarter)
        yaw = sighting.yaw90_rad + k * quarter
        return _Track(pos_mm=pos, last_seen_ms=t_ms, ever_seen=True, yaw_rad=yaw)

    @staticmethod
    def _in_tower(pos: tuple[float, float, float], tower: str) -> bool:
        return (
            abs(pos[0] - TOWER_X_MM[tower]) <= TOWER_HALF_X_MM
            and abs(pos[1] - TOWER_Y_MM) <= TOWER_HALF_Y_MM
        )

    def _add_structural_ghosts(self, present: dict[BoxId, tuple[float, float, float]]) -> None:
        """確定盤面で塔にあり、上の箱に覆われて見えない箱を保持位置で存在扱いにする。

        覆いが無くなれば(=本来タグが見えるはず)通常のロスト規則に戻り、
        観測箱が保持スロットに重なれば(=実際は取り除かれていた)矛盾として解放する。
        """
        if self._confirmed_sig is None:
            return
        for tower_index, tower in enumerate(_TOWERS):
            for box_id in self._confirmed_sig.towers[tower_index]:
                if box_id in present:
                    continue
                track = self._tracks[box_id]
                if not track.ever_seen:
                    continue
                z0 = track.pos_mm[2]
                z1 = z0 + BOX_EDGE_MM[BOX_SIZE_OF[box_id]]
                others = [
                    (other_pos[2], other_pos[2] + BOX_EDGE_MM[BOX_SIZE_OF[other_id]])
                    for other_id, other_pos in present.items()
                    if other_id != box_id and self._in_tower(other_pos, tower)
                ]
                # 接触条件(|上箱の底 - 自分の天面| <= tol)。単に上方にあるだけでは
                # 支持とみなさない(覆いを持ち上げたらタグが見えるはずなので解放する)
                supported = any(abs(oz0 - z1) <= GHOST_SUPPORT_TOL_MM for oz0, _ in others)
                contradicted = any(
                    min(z1, oz1) - max(z0, oz0) > GHOST_OVERLAP_TOL_MM for oz0, oz1 in others
                )
                if supported and not contradicted:
                    present[box_id] = track.pos_mm

    def _classify(
        self, present: dict[BoxId, tuple[float, float, float]]
    ) -> dict[BoxId, tuple[Area | None, int | None]]:
        """存在推定中の箱をエリア分類し、塔は積み順(level)まで解決する。"""
        result: dict[BoxId, tuple[Area | None, int | None]] = {}
        tower_candidates: dict[str, list[tuple[BoxId, tuple[float, float, float]]]] = {
            t: [] for t in _TOWERS
        }
        for box_id, pos in present.items():
            x, y, z = pos
            tower = next(
                (
                    t
                    for t in _TOWERS
                    if abs(x - TOWER_X_MM[t]) <= TOWER_HALF_X_MM
                    and abs(y - TOWER_Y_MM) <= TOWER_HALF_Y_MM
                ),
                None,
            )
            in_staging = (
                y <= STAGING_Y_MAX_MM
                and y >= -MAT_MARGIN_MM
                and -MAT_MARGIN_MM <= x <= MAT_SIZE_MM[0] + MAT_MARGIN_MM
                and z <= STACK_GAP_TOL_MM  # 接地している(持ち上げ中は移動中扱い)
            )
            if tower is not None:
                tower_candidates[tower].append((box_id, pos))
            elif in_staging:
                result[box_id] = ("staging", None)
            else:
                result[box_id] = (None, None)

        for tower, candidates in tower_candidates.items():
            candidates.sort(key=lambda item: item[1][2])  # z昇順
            expected_z = 0.0
            level = 0
            for box_id, pos in candidates:
                if abs(pos[2] - expected_z) <= STACK_GAP_TOL_MM:
                    result[box_id] = (tower, level)  # type: ignore[assignment]
                    expected_z += BOX_EDGE_MM[BOX_SIZE_OF[box_id]]
                    level += 1
                else:
                    result[box_id] = (None, None)  # 宙に浮いている(移動中)
        return result

    def _signature(
        self, area_level: dict[BoxId, tuple[Area | None, int | None]]
    ) -> _BoardSignature:
        towers: list[tuple[BoxId, ...]] = []
        for tower in _TOWERS:
            stack = sorted(
                (
                    (level, box_id)
                    for box_id, (area, level) in area_level.items()
                    if area == tower and level is not None
                ),
            )
            towers.append(tuple(box_id for _, box_id in stack))
        staging = tuple(
            sorted(
                (box_id for box_id, (area, _) in area_level.items() if area == "staging"),
                key=BOX_IDS.index,
            )
        )
        return _BoardSignature(towers=tuple(towers), staging=staging)

    def _update_stability(
        self, t_ms: int, area_level: dict[BoxId, tuple[Area | None, int | None]]
    ) -> list[CvMessage]:
        sig = self._signature(area_level)
        if sig != self._stable_sig:
            self._stable_sig = sig
            self._stable_since_ms = t_ms
            self._stable_frames = 1
            return []
        self._stable_frames += 1
        assert self._stable_since_ms is not None
        if (
            t_ms - self._stable_since_ms < STABLE_MS
            or self._stable_frames < STABLE_MIN_FRAMES
            or sig == self._confirmed_sig
        ):
            return []
        self._confirmed_sig = sig
        stacks = {tower: [BOX_SIZE_OF[b] for b in sig.towers[i]] for i, tower in enumerate(_TOWERS)}
        towers_str = tuple(
            "".join(SIZE_CHAR[BOX_SIZE_OF[b]] for b in sig.towers[i]) for i in range(len(_TOWERS))
        )
        tower_box_ids = (list(sig.towers[0]), list(sig.towers[1]), list(sig.towers[2]))
        # 公開内容が前回の確定盤面と同一なら再送しない(契約§3「確定盤面が変化したときのみ」)。
        # 個体まで比較する: 同サイズの箱を塔間で入れ替えただけでもサイズ列は変わらないが、
        # クリア条件2は箱の個体で判定する(ルールブック§5)ため別の盤面として送る必要がある
        last = self._last_board
        if (
            last is not None
            and last.tower_box_ids == tower_box_ids
            and last.staging_box_ids == list(sig.staging)
        ):
            return []
        violations = violations_for(stacks)
        update = CvBoardUpdate(
            t_ms=t_ms,
            towers=(towers_str[0], towers_str[1], towers_str[2]),
            board=format_board(towers_str),
            legal=not violations,
            violations=violations,
            staging_box_ids=list(sig.staging),
            tower_box_ids=tower_box_ids,
        )
        self._last_board = update
        return [update]

    def _frame(
        self,
        t_ms: int,
        seen_now: dict[BoxId, BoxSighting],
        area_level: dict[BoxId, tuple[Area | None, int | None]],
        mat_corners_detected: int,
    ) -> CvFrame:
        boxes: list[BoxObservation] = []
        for box_id in BOX_IDS:
            track = self._tracks[box_id]
            area, level = area_level.get(box_id, (None, None))
            sighting = seen_now.get(box_id)
            half = track.yaw_rad / 2
            boxes.append(
                BoxObservation(
                    box_id=box_id,
                    size=BOX_SIZE_OF[box_id],
                    pos_mm=track.pos_mm,
                    quat=(0.0, 0.0, math.sin(half), math.cos(half)),  # 鉛直軸まわりのヨーのみ
                    area=area,
                    level=level,
                    visible=sighting is not None,
                    seen_tag_ids=list(sighting.seen_tag_ids) if sighting else [],
                )
            )
        return CvFrame(t_ms=t_ms, mat_corners_detected=mat_corners_detected, boxes=boxes)
