"""screens.ui のテスト(矩形の当たり判定・押下エッジ)。"""

from __future__ import annotations

from screens.ui import Button, ClickEdge, Rect


def test_rect_contains_is_half_open() -> None:
    r = Rect(10, 20, 30, 40)
    assert r.contains(10, 20)
    assert r.contains(39, 59)
    assert not r.contains(40, 59)
    assert not r.contains(39, 60)
    assert not r.contains(9, 20)
    assert (r.cx, r.cy) == (25, 40)


def test_button_hit() -> None:
    b = Button(Rect(0, 0, 10, 10), "X")
    assert b.hit(5, 5) and not b.hit(10, 10)


def test_click_edge_only_on_press() -> None:
    edge = ClickEdge()
    assert edge.feed(1, 2, False) is None
    assert edge.feed(1, 2, True) == (1, 2)
    assert edge.feed(3, 4, True) is None  # 押しっぱなし
    assert edge.feed(3, 4, False) is None
    assert edge.feed(5, 6, True) == (5, 6)


def test_click_edge_ignores_button_already_held_at_creation() -> None:
    edge = ClickEdge()
    assert edge.feed(1, 2, True) is None  # 生成時から押されていた
    assert edge.feed(1, 2, True) is None
    assert edge.feed(1, 2, False) is None
    assert edge.feed(1, 2, True) == (1, 2)
