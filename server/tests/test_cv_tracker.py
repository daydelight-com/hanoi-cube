"""BoardTracker(実CVの盤面構成・ロスト保持・安定判定)のテスト。

時刻は全て注入して決定的に検証する。33ms刻み=約30fps相当。
"""

from __future__ import annotations

import pytest
from app.cv.interface import BOX_IDS, CvBoardUpdate, CvFrame, CvMessage
from app.cv.layout import STAGING_Y_MM, TOWER_X_MM, TOWER_Y_MM
from app.cv.tracker import LOST_HOLD_MS, STABLE_MS, BoardTracker, BoxSighting

DT = 33


def sight(box_id: str, x: float, y: float, z: float = 0.0) -> BoxSighting:
    assert box_id in BOX_IDS
    index = BOX_IDS.index(box_id)
    return BoxSighting(
        box_id=box_id,
        pos_mm=(x, y, z),
        seen_tag_ids=(index * 6,),
    )


def tower_sight(box_id: str, tower: str, z: float) -> BoxSighting:
    return sight(box_id, TOWER_X_MM[tower], TOWER_Y_MM, z)


def staging_sight(box_id: str, slot: int = 0) -> BoxSighting:
    return sight(box_id, 60.0 + slot * 60.0, STAGING_Y_MM)


class Driver:
    def __init__(self) -> None:
        self.tracker = BoardTracker()
        self.now = 0

    def feed(
        self,
        sightings: list[BoxSighting],
        *,
        repeat: int = 1,
        mat: int = 4,
        calibrated: bool = True,
    ) -> list[CvMessage]:
        messages: list[CvMessage] = []
        for _ in range(repeat):
            self.now += DT
            messages += self.tracker.process(self.now, sightings, mat, calibrated)
        return messages

    def feed_until_stable(self, sightings: list[BoxSighting]) -> list[CvBoardUpdate]:
        # 安定判定(STABLE_MS)を満たすのに十分な回数流す
        messages = self.feed(sightings, repeat=STABLE_MS // DT + 2)
        return [m for m in messages if isinstance(m, CvBoardUpdate)]


def frames(messages: list[CvMessage]) -> list[CvFrame]:
    return [m for m in messages if isinstance(m, CvFrame)]


def boards(messages: list[CvMessage]) -> list[CvBoardUpdate]:
    return [m for m in messages if isinstance(m, CvBoardUpdate)]


def box_in_frame(frame: CvFrame, box_id: str) -> dict[str, object]:
    for box in frame.boxes:
        if box.box_id == box_id:
            return box.model_dump()
    raise AssertionError(box_id)


def test_uncalibrated_emits_frames_only() -> None:
    d = Driver()
    messages = d.feed([], repeat=20, calibrated=False, mat=0)
    assert not boards(messages)
    fs = frames(messages)
    assert len(fs) == 20
    assert all(len(f.boxes) == 9 for f in fs)
    assert all(not b.visible and b.area is None for f in fs for b in f.boxes)


def test_initial_confirmed_board_all_staging() -> None:
    d = Driver()
    sightings = [staging_sight(b, i) for i, b in enumerate(BOX_IDS)]
    updates = d.feed_until_stable(sightings)
    assert len(updates) == 1
    up = updates[0]
    assert up.board == "//"
    assert up.legal
    assert up.staging_box_ids == list(BOX_IDS)
    # 以後同じ盤面を流し続けても再送しない
    assert not d.feed_until_stable(sightings)


def test_stability_window_suppresses_transients() -> None:
    d = Driver()
    base = [staging_sight("large-1", 0)]
    assert d.feed_until_stable(base)
    # 0.3秒未満だけ塔Aに現れてすぐ戻る → 確定盤面は変化しない
    transient = [tower_sight("large-1", "A", 0.0)]
    messages = d.feed(transient, repeat=3)
    messages += d.feed(base, repeat=STABLE_MS // DT + 2)
    assert not boards(messages)


def test_move_to_tower_confirms_after_stable() -> None:
    d = Driver()
    assert d.feed_until_stable([staging_sight("large-1", 0)])
    updates = d.feed_until_stable([tower_sight("large-1", "A", 0.0)])
    assert [u.board for u in updates] == ["L//"]
    assert updates[0].towers == ("L", "", "")
    assert updates[0].staging_box_ids == []


def test_stack_levels_and_board_string() -> None:
    d = Driver()
    sightings = [
        tower_sight("large-1", "A", 0.0),
        tower_sight("medium-1", "A", 75.0),
        tower_sight("small-1", "A", 125.0),
        tower_sight("large-2", "C", 0.0),
    ]
    updates = d.feed_until_stable(sightings)
    assert [u.board for u in updates] == ["LMS//L"]
    frame = frames(d.feed(sightings))[0]
    assert box_in_frame(frame, "large-1")["level"] == 0
    assert box_in_frame(frame, "medium-1")["level"] == 1
    assert box_in_frame(frame, "small-1")["level"] == 2
    assert box_in_frame(frame, "large-2")["level"] == 0


def test_illegal_stack_reports_violation() -> None:
    d = Driver()
    sightings = [
        tower_sight("small-1", "B", 0.0),
        tower_sight("large-1", "B", 30.0),
    ]
    updates = d.feed_until_stable(sightings)
    assert len(updates) == 1
    up = updates[0]
    assert not up.legal
    assert up.towers == ("", "SL", "")
    assert [(v.tower, v.type) for v in up.violations] == [("B", "size_order")]


def test_duplicate_and_overflow_violations() -> None:
    d = Driver()
    sightings = [
        tower_sight("large-1", "A", 0.0),
        tower_sight("large-2", "A", 75.0),
        tower_sight("medium-1", "A", 150.0),
        tower_sight("small-1", "A", 200.0),
    ]
    updates = d.feed_until_stable(sightings)
    types = {(v.tower, v.type) for v in updates[0].violations}
    assert types == {("A", "duplicate_size"), ("A", "overflow")}


def test_floating_box_not_counted_in_tower() -> None:
    d = Driver()
    sightings = [
        tower_sight("large-1", "A", 0.0),
        tower_sight("medium-1", "A", 120.0),  # 大(75mm)の上面から45mm浮いている
    ]
    updates = d.feed_until_stable(sightings)
    assert [u.board for u in updates] == ["L//"]
    frame = frames(d.feed(sightings))[0]
    assert box_in_frame(frame, "medium-1")["area"] is None
    assert box_in_frame(frame, "medium-1")["level"] is None


def test_lost_hold_keeps_area_then_releases() -> None:
    d = Driver()
    sightings = [tower_sight("large-1", "A", 0.0), staging_sight("small-1", 2)]
    assert d.feed_until_stable(sightings)

    # large-1 のタグが完全ロスト(遮蔽)。保持時間内は盤面が変わらない
    remaining = [staging_sight("small-1", 2)]
    held_frames = LOST_HOLD_MS // DT  # 2秒ぶん
    messages = d.feed(remaining, repeat=held_frames)
    assert not boards(messages)
    first = frames(messages)[0]
    assert box_in_frame(first, "large-1")["visible"] is False
    assert box_in_frame(first, "large-1")["area"] == "A"  # 保持位置で塔に留まる

    # 保持時間を超えると盤面から外れ、安定後に確定盤面が更新される
    updates = d.feed_until_stable(remaining)
    assert [u.board for u in updates] == ["//"]
    frame = frames(d.feed(remaining))[0]
    assert box_in_frame(frame, "large-1")["area"] is None


def test_reappear_during_hold_is_seamless() -> None:
    d = Driver()
    sightings = [tower_sight("large-1", "A", 0.0)]
    assert d.feed_until_stable(sightings)
    d.feed([], repeat=30)  # 1秒ロスト(保持内)
    messages = d.feed(sightings, repeat=STABLE_MS // DT + 2)
    assert not boards(messages)  # 盤面は一度も変わっていない


def test_structural_ghost_persists_while_covered() -> None:
    """確定盤面で塔にあった箱は、上の箱に覆われている間は2秒を超えても保持される
    (仕様§4.2。「小の上に大」ではオーバーハングで下の箱が恒久的に見えなくなる)。"""
    d = Driver()
    assert d.feed_until_stable([tower_sight("small-2", "C", 0.0)])

    # 小箱がロストし、大箱が上(z=30)に載って見える
    covered = [tower_sight("large-2", "C", 30.0)]
    updates = d.feed_until_stable(covered)
    assert [u.board for u in updates] == ["//SL"]
    assert not updates[0].legal

    # ロスト保持(2秒)の3倍流しても違反盤面が保持される
    messages = d.feed(covered, repeat=3 * LOST_HOLD_MS // DT)
    assert not boards(messages)
    frame = frames(messages)[-1]
    ghost = box_in_frame(frame, "small-2")
    assert ghost["area"] == "C"
    assert ghost["level"] == 0
    assert ghost["visible"] is False


def test_structural_ghost_released_on_contradiction() -> None:
    """保持スロットに観測箱が重なったら(実際は取り除かれていた)ゴーストを解放する。"""
    d = Driver()
    assert d.feed_until_stable([tower_sight("small-2", "C", 0.0)])
    covered = [tower_sight("large-2", "C", 30.0)]
    assert d.feed_until_stable(covered)
    d.feed(covered, repeat=3 * LOST_HOLD_MS // DT)

    # 大箱が接地して観測される(=小箱は実はもう無い)
    grounded = [tower_sight("large-2", "C", 0.0)]
    updates = d.feed_until_stable(grounded)
    assert [u.board for u in updates] == ["//L"]
    assert updates[0].legal


def test_structural_ghost_released_when_uncovered() -> None:
    """覆いが無くなれば(本来タグが見えるはず)通常のロスト規則に戻って解放される。"""
    d = Driver()
    assert d.feed_until_stable([tower_sight("small-2", "C", 0.0)])
    covered = [tower_sight("large-2", "C", 30.0)]
    assert d.feed_until_stable(covered)
    d.feed(covered, repeat=3 * LOST_HOLD_MS // DT)

    # 両方とも視界から消える(まとめて持ち去られた等)
    updates: list[CvBoardUpdate] = []
    for _ in range(2 * LOST_HOLD_MS // DT):
        updates += boards(d.feed([]))
    assert [u.board for u in updates] == ["//"]


def test_structural_ghost_released_when_cover_lifted() -> None:
    """覆い箱が持ち上げられて接触が切れたら(本来タグが見えるはず)ゴーストを解放する。"""
    d = Driver()
    assert d.feed_until_stable([tower_sight("small-2", "C", 0.0)])
    covered = [tower_sight("large-2", "C", 30.0)]
    assert d.feed_until_stable(covered)
    d.feed(covered, repeat=3 * LOST_HOLD_MS // DT)

    # 大箱を真上に持ち上げる(小箱は見えないまま=実は一緒に持ち去られた等)
    lifted = [tower_sight("large-2", "C", 150.0)]
    updates = d.feed_until_stable(lifted)
    assert [u.board for u in updates] == ["//"]


def test_identity_swap_reemits_board_with_new_box_ids() -> None:
    """同サイズの個体を入れ替えたら、盤面文字列が同じでも再emitする(契約§3)。

    クリア条件2は箱の個体で見る(ルールブック§5)ため、サイズ列だけで再送を
    抑止するとサーバーが入れ替え前の箱構成のまま判定してしまう。
    """
    d = Driver()
    initial = [tower_sight("large-1", "A", 0.0), tower_sight("large-2", "C", 0.0)]
    first = d.feed_until_stable(initial)
    assert [u.board for u in first] == ["L//L"]
    assert first[0].tower_box_ids == (["large-1"], [], ["large-2"])

    # large-1 と large-2 を入れ替える(盤面文字列・待機は不変だが個体は動いている)
    swapped = [tower_sight("large-2", "A", 0.0), tower_sight("large-1", "C", 0.0)]
    second = d.feed_until_stable(swapped)
    assert [u.board for u in second] == ["L//L"]
    assert second[0].tower_box_ids == (["large-2"], [], ["large-1"])


def test_unchanged_board_is_not_reemitted() -> None:
    """個体も含めて同一なら再emitしない(契約§3「確定盤面が変化したときのみ」)。"""
    d = Driver()
    sightings = [tower_sight("large-1", "A", 0.0), tower_sight("large-2", "C", 0.0)]
    assert [u.board for u in d.feed_until_stable(sightings)] == ["L//L"]
    assert not d.feed_until_stable(sightings)


def test_stability_boundary_exact_ms() -> None:
    """安定判定は「同一盤面が STABLE_MS 以上」で確定する(直前は確定しない)。"""
    tracker = BoardTracker()
    s = [tower_sight("large-1", "A", 0.0)]
    assert not boards(tracker.process(0, s, 4, True))
    assert not boards(tracker.process(STABLE_MS - 1, s, 4, True))
    assert [u.board for u in boards(tracker.process(STABLE_MS, s, 4, True))] == ["L//"]


def test_lost_hold_boundary_exact_ms() -> None:
    """ロスト保持はちょうど LOST_HOLD_MS までエリアを保ち、超えたら外れる。"""
    tracker = BoardTracker()
    s = [tower_sight("large-1", "A", 0.0)]
    tracker.process(0, s, 4, True)
    frame_at_limit = frames(tracker.process(LOST_HOLD_MS, [], 4, True))[0]
    assert box_in_frame(frame_at_limit, "large-1")["area"] == "A"
    frame_after = frames(tracker.process(LOST_HOLD_MS + 1, [], 4, True))[0]
    assert box_in_frame(frame_after, "large-1")["area"] is None


def test_lifted_box_in_staging_area_is_moving() -> None:
    """待機エリア上空で持ち上げた箱は staging に数えない(契約§3: 掴まれ中は含めない)。"""
    d = Driver()
    frame = frames(d.feed([sight("medium-2", 300.0, 80.0, 100.0)]))[0]
    assert box_in_frame(frame, "medium-2")["area"] is None


def test_yaw_quat_unwraps_at_pi_boundary() -> None:
    """±180°境界のヨー観測は前回値に近い代表へ展開され、表示が一回転しない。"""
    import math

    d = Driver()

    def with_yaw(yaw_deg: float) -> BoxSighting:
        base = sight("large-1", 150.0, 280.0, 0.0)
        return BoxSighting(
            box_id=base.box_id,
            pos_mm=base.pos_mm,
            seen_tag_ids=base.seen_tag_ids,
            yaw_rad=math.radians(yaw_deg),
        )

    def frame_yaw_deg(messages: list[CvMessage]) -> float:
        box = box_in_frame(frames(messages)[0], "large-1")
        qz, qw = box["quat"][2], box["quat"][3]  # type: ignore[index]
        return math.degrees(2 * math.atan2(qz, qw))

    assert frame_yaw_deg(d.feed([with_yaw(178.0)])) == pytest.approx(178.0, abs=0.1)
    # -179° の観測(=178° から +3° のノイズ)は 181° として連続に扱われる
    assert frame_yaw_deg(d.feed([with_yaw(-179.0)])) == pytest.approx(181.0, abs=0.1)


def test_flipped_box_quat_composition() -> None:
    """up_face+ヨーの観測が quat(Rz(yaw)@基準姿勢)として CvFrame に反映される。"""
    import math

    d = Driver()
    base = sight("large-1", 150.0, 280.0, 0.0)
    obs = BoxSighting(
        box_id=base.box_id,
        pos_mm=base.pos_mm,
        seen_tag_ids=base.seen_tag_ids,
        up_face=6,
        yaw_rad=math.radians(90.0),
    )
    box = box_in_frame(frames(d.feed([obs]))[0], "large-1")
    quat = box["quat"]
    assert isinstance(quat, tuple)
    # Rz(90°) ⊗ Rx(180°) = (√2/2, √2/2, 0, 0)
    expected = (math.sqrt(0.5), math.sqrt(0.5), 0.0, 0.0)
    err = max(abs(a - b) for a, b in zip(quat, expected, strict=True))
    assert err < 1e-6


def test_frame_passthrough_fields() -> None:
    d = Driver()
    messages = d.feed([staging_sight("medium-2", 1)], mat=3)
    frame = frames(messages)[0]
    assert frame.mat_corners_detected == 3
    box = box_in_frame(frame, "medium-2")
    assert box["visible"] is True
    assert box["seen_tag_ids"] == [24]
    assert box["area"] == "staging"
