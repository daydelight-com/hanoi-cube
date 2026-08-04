"""モックCV(contracts/cv-interface.md 準拠)のテスト。"""

import pytest
from app.cv.interface import BOX_IDS, CvBoardUpdate, CvFrame
from app.cv.mock import MockCv
from app.cv.mock_cli import resolve_box_id


def board_updates(mock: MockCv) -> list[CvBoardUpdate]:
    return [m for m in mock.poll() if isinstance(m, CvBoardUpdate)]


def test_initial_state_all_boxes_staged() -> None:
    mock = MockCv()
    messages = mock.poll()
    frames = [m for m in messages if isinstance(m, CvFrame)]
    assert len(frames) == 1
    frame = frames[0]
    assert frame.mat_corners_detected == 4
    assert [b.box_id for b in frame.boxes] == list(BOX_IDS)  # 常に9箱すべて
    assert all(b.area == "staging" for b in frame.boxes)


def test_grab_and_place_builds_board() -> None:
    mock = MockCv()
    mock.grab("large-1")
    (update,) = board_updates(mock)
    assert update.board == "//"
    assert "large-1" not in update.staging_box_ids  # 掴まれ中はどこにも属さない

    mock.place("A")
    mock.grab("medium-1")
    mock.place("A")
    mock.grab("small-1")
    mock.place("A")
    updates = board_updates(mock)
    assert updates[-1].board == "LMS//"
    assert updates[-1].legal
    assert updates[-1].violations == []


def test_place_illegal_stack_reports_violation() -> None:
    mock = MockCv()
    mock.grab("small-1")
    mock.place("B")
    mock.grab("large-1")
    mock.place("B")  # 小の上に大
    update = board_updates(mock)[-1]
    assert update.towers[1] == "SL"
    assert not update.legal
    assert [(v.tower, v.type) for v in update.violations] == [("B", "size_order")]


def test_duplicate_size_violation() -> None:
    mock = MockCv()
    for box in ("large-1", "large-2"):
        mock.grab(box)
        mock.place("C")
    update = board_updates(mock)[-1]
    assert not update.legal
    assert ("C", "duplicate_size") in [(v.tower, v.type) for v in update.violations]


def test_set_board_direct() -> None:
    mock = MockCv()
    mock.set_board("LMS//L")
    update = board_updates(mock)[-1]
    assert update.board == "LMS//L"
    assert update.legal
    assert len(update.staging_box_ids) == 5  # 9 - 4
    # 続けて別盤面へ(何度でも作り直せる)
    mock.set_board("L/MS/L")
    update = board_updates(mock)[-1]
    assert update.board == "L/MS/L"
    assert update.legal


def test_set_board_rejects_impossible_and_bad_format() -> None:
    mock = MockCv()
    with pytest.raises(ValueError):
        mock.set_board("LLL/L/")  # 大が4個必要(物理制約超え)
    with pytest.raises(ValueError):
        mock.set_board("LMS/L")  # 形式不正


def test_no_duplicate_board_update_when_unchanged() -> None:
    mock = MockCv()
    mock.set_board("LMS//L")
    assert len(board_updates(mock)) == 1
    assert board_updates(mock) == []  # 変化なしなら再emitしない
    mock.set_board("LMS//L")
    assert board_updates(mock) == []


def test_frame_positions_stack_heights() -> None:
    mock = MockCv()
    mock.set_board("LMS//")
    frame = next(m for m in mock.poll() if isinstance(m, CvFrame))
    by_id = {b.box_id: b for b in frame.boxes}
    assert by_id["large-1"].pos_mm[2] == 0.0
    assert by_id["medium-1"].pos_mm[2] == 75.0  # 大の上
    assert by_id["small-1"].pos_mm[2] == 125.0  # 大+中の上
    assert (by_id["large-1"].area, by_id["large-1"].level) == ("A", 0)
    assert (by_id["small-1"].area, by_id["small-1"].level) == ("A", 2)


def test_timestamps_monotonic() -> None:
    mock = MockCv()
    times = []
    for _ in range(3):
        frame = next(m for m in mock.poll() if isinstance(m, CvFrame))
        times.append(frame.t_ms)
    assert times == sorted(times) and len(set(times)) == 3


def test_resolve_box_id_shorthand() -> None:
    assert resolve_box_id("L1") == "large-1"
    assert resolve_box_id("m2") == "medium-2"
    assert resolve_box_id("small-3") == "small-3"
    with pytest.raises(ValueError):
        resolve_box_id("X1")
