"""状態機械のテスト(契約: docs/contracts/screens.md)。

遷移表(§3)の全26行を行番号付きテストで網羅する(S2のDoD)。
時刻・ID・保存日時はすべて注入し、決定的に検証する。
"""

from __future__ import annotations

from itertools import count
from typing import cast

import pytest
from app.api.messages import Outbound
from app.core.precompute import PrecomputeTable, load_table
from app.cv.interface import BoxId, CvBoardUpdate
from app.state.machine import (
    GAME_MS,
    IDLE_RANKING_SCROLL_MIN_MS,
    IDLE_RANKING_TAIL_MS,
    JUDGE_COOLDOWN_MS,
    NAME_MAX_CHARS,
    QR_GUARD_MS,
    RANKING_GUARD_MS,
    RULE_PAGE_COUNT,
    TITLE_MS,
    StateMachine,
)
from app.state.sqlite_store import SqliteStore
from app.state.store import MemoryStore

# S1テスト済みの検証値: L/MS/L=60点(4箱*15手)、LMS//=21点(3箱*7手)、
# //LMS はその鏡像、LMS/MS/L はクリア不可
SCORED_BOARD = "L/MS/L"
SCORED_POINTS = 60
MIRROR_A = "LMS//"
MIRROR_A_POINTS = 21
MIRROR_B = "//LMS"
UNCLEARABLE_BOARD = "LMS/MS/L"


@pytest.fixture(scope="module")
def table() -> PrecomputeTable:
    return load_table()


_BOX_NAME = {"L": "large", "M": "medium", "S": "small"}


def board_update(board: str, *, legal: bool = True, t_ms: int = 0) -> CvBoardUpdate:
    """盤面文字列から CvBoardUpdate を作る。箱の個体は出現順に 1..3 を割り当てる。"""
    towers = board.split("/")
    serial = {"L": 0, "M": 0, "S": 0}

    def box_ids(tower: str) -> list[BoxId]:
        ids = []
        for size in tower:
            serial[size] += 1
            ids.append(cast(BoxId, f"{_BOX_NAME[size]}-{serial[size]}"))
        return ids

    a, b, c = towers
    return CvBoardUpdate(
        t_ms=t_ms,
        towers=(a, b, c),
        board=board,
        legal=legal,
        tower_box_ids=(box_ids(a), box_ids(b), box_ids(c)),
    )


class Driver:
    """時刻を持ち回って状態機械を操作するテストヘルパー。"""

    def __init__(
        self, table: PrecomputeTable, store: MemoryStore | SqliteStore | None = None
    ) -> None:
        self.store = store or MemoryStore()
        ids = count(1)
        self.machine = StateMachine(
            table,
            self.store,
            now_ms=0,
            id_factory=lambda: f"play-{next(ids)}",
            played_at_factory=lambda: "2026-08-04T10:00:00+09:00",
        )
        self.now = 0

    @property
    def screen(self) -> str:
        return self.machine.screen

    def press(self, button: str) -> list[Outbound]:
        return self.machine.on_button(button, self.now)  # type: ignore[arg-type]

    def advance(self, ms: int) -> list[Outbound]:
        self.now += ms
        return self.machine.tick(self.now)

    def set_board(self, board: str, *, legal: bool = True) -> list[Outbound]:
        return self.machine.on_cv_message(board_update(board, legal=legal, t_ms=self.now), self.now)

    # ---- 画面までのナビゲーション ----

    def to_mode_select(self) -> None:
        assert self.screen == "idle_title"
        self.press("enter")

    def to_practice(self) -> None:
        self.to_mode_select()
        self.press("right")  # focus=practice
        self.press("enter")
        assert self.screen == "practice"

    def to_game_play(self) -> None:
        self.to_mode_select()
        self.press("right")
        self.press("right")  # focus=game
        self.press("enter")
        assert self.screen == "game_countdown"
        self.advance(3_000)  # 3→2→1→GO
        assert self.screen == "game_play"

    def to_result(self) -> None:
        self.to_game_play()
        self.advance(GAME_MS)
        assert self.screen == "result"

    def to_ranking(self, name: str = "たろう") -> None:
        self.to_result()
        self.machine.on_name_text(name, self.now)
        self.machine.on_name_done(self.now)
        self.press("enter")  # focus=decide
        assert self.screen == "ranking"


@pytest.fixture
def d(table: PrecomputeTable) -> Driver:
    return Driver(table)


def sent(out: list[Outbound], type_: str) -> list[Outbound]:
    return [o for o in out if o.type == type_]


def screen_of(out: list[Outbound]) -> str:
    msgs = sent(out, "screen")
    assert msgs, f"no screen message in {[o.type for o in out]}"
    screen = msgs[-1].payload["screen"]
    assert isinstance(screen, str)
    return screen


# ---- 遷移表 §3 ----


def test_row1_idle_title_timeout_to_idle_ranking(d: Driver) -> None:
    assert d.advance(TITLE_MS - 1) == []
    out = d.advance(1)
    assert screen_of(out) == "idle_ranking"
    assert sent(out, "ranking")  # 表示用に ranking も配信


def test_row2_idle_title_enter_to_mode_select(d: Driver) -> None:
    out = d.press("enter")
    assert screen_of(out) == "mode_select"
    assert sent(out, "screen")[-1].payload["ctx"] == {"focus": "rules"}


def test_row3_idle_ranking_timeout_to_idle_title(d: Driver) -> None:
    d.advance(TITLE_MS)
    assert d.screen == "idle_ranking"
    duration = IDLE_RANKING_SCROLL_MIN_MS + IDLE_RANKING_TAIL_MS  # 0件時
    assert d.advance(duration - 1) == []
    assert screen_of(d.advance(1)) == "idle_title"


def test_row4_idle_ranking_enter_to_idle_title(d: Driver) -> None:
    d.advance(TITLE_MS)
    assert d.screen == "idle_ranking"
    assert screen_of(d.press("enter")) == "idle_title"


def test_row5_mode_select_focus_moves_and_wraps(d: Driver) -> None:
    d.to_mode_select()
    out = d.press("left")  # 左端からはループして lang へ
    assert sent(out, "screen")[-1].payload["ctx"]["focus"] == "lang"
    out = d.press("right")  # 右端からはループして rules へ
    assert sent(out, "screen")[-1].payload["ctx"]["focus"] == "rules"
    focuses = []
    for _ in range(4):
        out = d.press("right")
        focuses.append(sent(out, "screen")[-1].payload["ctx"]["focus"])
    assert focuses == ["practice", "game", "lang", "rules"]  # 1周してrulesへ戻る
    out = d.press("left")
    assert sent(out, "screen")[-1].payload["ctx"]["focus"] == "lang"


def test_row6_mode_select_enter_rules_to_rule_dialog(d: Driver) -> None:
    d.to_mode_select()
    out = d.press("enter")  # focus=rules
    assert screen_of(out) == "rule_dialog"
    assert sent(out, "screen")[-1].payload["ctx"] == {
        "from": "mode_select",
        "page": 0,
        "page_count": RULE_PAGE_COUNT,
    }


def test_row7_mode_select_enter_practice_initializes(d: Driver) -> None:
    d.to_mode_select()
    d.press("right")
    out = d.press("enter")
    assert screen_of(out) == "practice"
    assert sent(out, "screen")[-1].payload["ctx"] == {"score": 0, "selection": None}


def test_row8_mode_select_enter_game_to_countdown(d: Driver) -> None:
    d.to_mode_select()
    d.press("right")
    d.press("right")
    out = d.press("enter")
    assert screen_of(out) == "game_countdown"
    assert sent(out, "countdown")[0].payload == {"value": "3"}


def test_row9_mode_select_lang_toggle_broadcasts(d: Driver) -> None:
    d.to_mode_select()
    for _ in range(3):
        d.press("right")  # focus=lang
    out = d.press("enter")
    langs = sent(out, "lang")
    assert {(o.channel, o.payload["lang"]) for o in langs} == {
        ("display", "en"),
        ("controller", "en"),
    }
    assert d.screen == "mode_select"
    out = d.press("enter")  # 再トグルで ja へ
    assert all(o.payload["lang"] == "ja" for o in sent(out, "lang"))


def test_row10_rule_dialog_page_moves_and_clamps(d: Driver) -> None:
    d.to_mode_select()
    d.press("enter")
    assert d.press("left") == []  # page=0 でクランプ
    pages = []
    for _ in range(RULE_PAGE_COUNT):
        out = d.press("right")
        if out:
            pages.append(sent(out, "screen")[-1].payload["ctx"]["page"])
    assert pages == [1, 2, 3, 4]  # 最終ページでクランプ


def test_row11_rule_dialog_close_returns_to_caller(d: Driver) -> None:
    d.to_mode_select()
    d.press("enter")
    out = d.press("enter")  # 閉じる
    assert screen_of(out) == "mode_select"
    # 呼び出し元のfocusは保持される(rules のまま)
    assert sent(out, "screen")[-1].payload["ctx"] == {"focus": "rules"}


def test_row12_practice_arrow_activates_selection(d: Driver) -> None:
    d.to_practice()
    out = d.press("left")
    assert sent(out, "screen")[-1].payload["ctx"]["selection"] == "back"
    out = d.press("right")
    assert sent(out, "screen")[-1].payload["ctx"]["selection"] == "help"
    assert d.press("right") == []  # 変化なしは無視


def test_row13_practice_box_moved_clears_selection(d: Driver) -> None:
    d.to_practice()
    d.press("left")
    out = d.set_board("S//")
    assert sent(out, "board")  # 盤面はディスプレイへ転送
    assert sent(out, "screen")[-1].payload["ctx"]["selection"] is None


def test_row14_practice_back_to_mode_select(d: Driver) -> None:
    d.to_practice()
    d.press("left")  # selection=back
    assert screen_of(d.press("enter")) == "mode_select"


def test_row15_practice_help_to_rule_dialog_and_back(d: Driver) -> None:
    d.to_practice()
    d.set_board(SCORED_BOARD)
    d.press("enter")  # スコアを作っておく
    d.press("right")  # selection=help
    out = d.press("enter")
    assert screen_of(out) == "rule_dialog"
    assert sent(out, "screen")[-1].payload["ctx"]["from"] == "practice"
    out = d.press("enter")  # 閉じる → practice(スコア保持)
    assert screen_of(out) == "practice"
    assert sent(out, "screen")[-1].payload["ctx"]["score"] == SCORED_POINTS


def test_row16_practice_judge_scored(d: Driver) -> None:
    d.to_practice()
    d.set_board(SCORED_BOARD)
    out = d.press("enter")
    judge = sent(out, "judge")[0]
    assert judge.channel == "display"
    assert judge.payload["result"] == "scored"
    assert judge.payload["points"] == SCORED_POINTS
    assert judge.payload["total_score"] == SCORED_POINTS
    assert judge.payload["seq"] == 1
    flash = sent(out, "flash")[0]
    assert (flash.channel, flash.payload) == ("controller", {"result": "scored"})
    assert sent(out, "screen")[-1].payload["ctx"]["score"] == SCORED_POINTS


def test_row16_practice_judge_guards(d: Driver) -> None:
    d.to_practice()
    assert d.press("enter") == []  # 確定盤面なし
    d.set_board("SL//", legal=False)
    assert d.press("enter") == []  # 盤面 legal=false
    d.set_board(SCORED_BOARD)
    assert sent(d.press("enter"), "judge")
    assert d.press("enter") == []  # クールダウン内(連打)
    d.advance(JUDGE_COOLDOWN_MS)
    out = d.press("enter")  # クールダウン明けは判定される(duplicate_same)
    assert sent(out, "judge")[0].payload["result"] == "duplicate_same"


def test_row17_countdown_sequence_then_game_play(d: Driver) -> None:
    d.to_mode_select()
    d.press("right")
    d.press("right")
    d.press("enter")
    assert sent(d.advance(999), "countdown") == []
    assert sent(d.advance(1), "countdown")[0].payload == {"value": "2"}
    assert sent(d.advance(1_000), "countdown")[0].payload == {"value": "1"}
    out = d.advance(1_000)
    assert sent(out, "countdown")[0].payload == {"value": "go"}
    assert screen_of(out) == "game_play"  # GOと同時に計測開始
    assert sent(out, "timer")[0].payload == {"remaining_ms": GAME_MS}


def test_countdown_buttons_ignored(d: Driver) -> None:
    d.to_mode_select()
    d.press("right")
    d.press("right")
    d.press("enter")
    assert d.press("enter") == []
    assert d.press("left") == []
    assert d.press("right") == []


def test_row18_game_judge_scored_duplicate_and_fail(d: Driver) -> None:
    d.to_game_play()
    d.set_board(MIRROR_A)
    out = d.press("enter")
    assert sent(out, "judge")[0].payload["result"] == "scored"
    assert sent(out, "judge")[0].payload["points"] == MIRROR_A_POINTS
    d.advance(1_000)
    d.set_board(MIRROR_B)  # 鏡像は重複(0点)
    out = d.press("enter")
    judge = sent(out, "judge")[0]
    assert judge.payload["result"] == "duplicate_mirror"
    assert judge.payload["points"] == 0
    assert judge.payload["min_moves"] == 7  # duplicate でも min_moves は入る
    assert sent(out, "flash")[0].payload == {"result": "duplicate"}
    d.advance(1_000)
    d.set_board(UNCLEARABLE_BOARD)
    out = d.press("enter")
    assert sent(out, "judge")[0].payload["result"] == "unclearable"
    assert sent(out, "judge")[0].payload["fail_count"] == 1
    assert sent(out, "flash")[0].payload == {"result": "failed"}


def test_row18_game_judge_time_guard(d: Driver) -> None:
    d.to_game_play()
    d.set_board(SCORED_BOARD)
    d.advance(GAME_MS - 1)  # 残り1ms(tickは timeup 前まで)
    assert d.screen == "game_play"
    assert sent(d.press("enter"), "judge")  # timeup 前の押下は有効
    assert d.screen == "game_play"


def test_row18_game_arrows_ignored(d: Driver) -> None:
    d.to_game_play()
    assert d.press("left") == []
    assert d.press("right") == []


def test_row19_timeup_to_result(d: Driver) -> None:
    d.to_game_play()
    out = d.advance(1_000)
    assert sent(out, "timer")[0].payload == {"remaining_ms": GAME_MS - 1_000}
    out = d.advance(GAME_MS - 1_000)
    assert sent(out, "timer")[-1].payload == {"remaining_ms": 0}
    assert screen_of(out) == "result"
    ctx = sent(out, "screen")[-1].payload["ctx"]
    assert ctx == {
        "score": 0,
        "fail_count": 0,
        "rank": 1,
        "name_text": "",
        "focus": "decide",
        "input_mode": "name",
    }
    mode = sent(out, "input_mode")[0]  # iPadをname入力モードへ
    assert (mode.channel, mode.payload) == ("controller", {"mode": "name", "name_text": ""})
    assert d.press("enter") == []  # timeup 後の enter は無効(name確定条件も未満)


def test_row20_name_text_mirrors_and_truncates(d: Driver) -> None:
    d.to_result()
    out = d.machine.on_name_text("あいうえおかきくけこさし", d.now)
    assert out[0].channel == "display"
    assert out[0].type == "name"
    assert out[0].payload == {"text": "あいうえおかきくけこ"}
    assert len(out[0].payload["text"]) == NAME_MAX_CHARS


def test_row21_name_done_returns_to_buttons(d: Driver) -> None:
    d.to_result()
    out = d.machine.on_name_done(d.now)
    mode = sent(out, "input_mode")[0]
    assert mode.payload["mode"] == "buttons"
    assert sent(out, "screen")[-1].payload["ctx"]["input_mode"] == "buttons"
    assert sent(out, "screen")[-1].payload["ctx"]["focus"] == "decide"


def test_row22_result_focus_toggle_buttons_mode_only(d: Driver) -> None:
    d.to_result()
    assert d.press("left") == []  # nameモード中の矢印は無効
    d.machine.on_name_done(d.now)
    out = d.press("left")
    assert sent(out, "screen")[-1].payload["ctx"]["focus"] == "input"
    out = d.press("right")
    assert sent(out, "screen")[-1].payload["ctx"]["focus"] == "decide"


def test_row23_result_enter_input_reopens_keyboard(d: Driver) -> None:
    d.to_result()
    d.machine.on_name_text("たろう", d.now)
    d.machine.on_name_done(d.now)
    d.press("left")  # focus=input
    out = d.press("enter")
    mode = sent(out, "input_mode")[0]
    assert mode.payload == {"mode": "name", "name_text": "たろう"}  # 現在値で初期化


def test_row24_result_decide_saves_and_goes_ranking(d: Driver) -> None:
    d.to_result()
    d.machine.on_name_done(d.now)
    assert d.press("enter") == []  # 0文字は無効
    d.press("left")
    d.press("enter")  # 再入力モードへ
    d.machine.on_name_text("たろう", d.now)
    d.machine.on_name_done(d.now)
    out = d.press("enter")
    assert screen_of(out) == "ranking"
    ctx = sent(out, "screen")[-1].payload["ctx"]
    assert ctx["highlight_play_id"] == "play-1"
    assert ctx["entries"][0]["name"] == "たろう"
    assert sent(out, "ranking")
    # result 退場時に iPad を buttons へ戻す(ws-messages.md §5)
    mode = sent(out, "input_mode")[0]
    assert (mode.channel, mode.payload["mode"]) == ("controller", "buttons")
    assert d.store.play("play-1") is not None


def test_row25_ranking_enter_guard_3s(d: Driver) -> None:
    d.to_ranking()
    assert d.press("enter") == []
    d.advance(RANKING_GUARD_MS - 1)
    assert d.press("enter") == []
    d.advance(1)
    out = d.press("enter")
    assert screen_of(out) == "qr"
    ctx = sent(out, "screen")[-1].payload["ctx"]
    assert ctx["play_id"] == "play-1"
    assert ctx["url"].endswith("/play-1")


def test_row26_qr_enter_guard_5s_and_lang_reset(d: Driver) -> None:
    d.to_mode_select()
    for _ in range(3):
        d.press("right")
    d.press("enter")  # lang=en にして本番プレイへ
    assert str(d.machine.lang) == "en"
    d.press("left")  # focus=game へ戻す
    d.press("enter")
    d.advance(3_000)
    d.advance(GAME_MS)
    d.machine.on_name_text("A", d.now)
    d.machine.on_name_done(d.now)
    d.press("enter")
    d.advance(RANKING_GUARD_MS)
    d.press("enter")  # → qr
    assert d.screen == "qr"
    assert d.press("enter") == []
    d.advance(QR_GUARD_MS - 1)
    assert d.press("enter") == []
    d.advance(1)
    out = d.press("enter")
    assert screen_of(out) == "idle_title"
    assert str(d.machine.lang) == "ja"  # 言語リセット
    assert {(o.channel, o.payload["lang"]) for o in sent(out, "lang")} == {
        ("display", "ja"),
        ("controller", "ja"),
    }


# ---- 無効ボタン(表にない組は無視。screens.md §2) ----


def test_invalid_buttons_ignored(d: Driver) -> None:
    assert d.press("left") == []  # idle_title
    assert d.press("right") == []
    d.advance(TITLE_MS)  # → idle_ranking
    assert d.press("left") == []
    assert d.press("right") == []


def test_ranking_and_qr_arrows_ignored(d: Driver) -> None:
    d.to_ranking()
    assert d.press("left") == []
    assert d.press("right") == []
    d.advance(RANKING_GUARD_MS)
    d.press("enter")
    assert d.press("left") == []  # qr
    assert d.press("right") == []


def test_name_events_ignored_outside_result(d: Driver) -> None:
    assert d.machine.on_name_text("x", d.now) == []
    assert d.machine.on_name_done(d.now) == []


# ---- 本番プレイの記録(screens.md §4-4) ----


def test_game_judgement_history_recorded(d: Driver) -> None:
    d.to_game_play()
    d.set_board(MIRROR_A)
    d.press("enter")  # seq1 scored
    d.advance(1_000)
    d.set_board(MIRROR_B)
    d.press("enter")  # seq2 duplicate_mirror (dup_of_seq=1)
    d.advance(1_000)
    d.set_board(UNCLEARABLE_BOARD)
    d.press("enter")  # seq3 unclearable
    d.advance(GAME_MS)
    d.machine.on_name_text("たろう", d.now)
    d.machine.on_name_done(d.now)
    d.press("enter")
    record = d.store.play("play-1")
    assert record is not None
    assert record.score == MIRROR_A_POINTS
    assert record.fail_count == 1
    assert [(j.seq, j.result, j.dup_of_seq) for j in record.judgements] == [
        (1, "scored", None),
        (2, "duplicate_mirror", 1),
        (3, "unclearable", None),
    ]
    assert record.judgements[0].elapsed_ms == 0
    assert record.judgements[1].elapsed_ms == 1_000
    assert record.judgements[1].min_moves == 7
    # 記録画面で同サイズの個体を見分けるため、判定時の箱の個体も残す(firestore.md §1)
    assert record.judgements[0].tower_box_ids == (
        ["large-1", "medium-1", "small-1"],
        [],
        [],
    )
    assert record.judgements[1].tower_box_ids == ([], [], ["large-1", "medium-1", "small-1"])


def test_same_size_swap_is_duplicate(d: Driver) -> None:
    """重複判定はサイズと並びのみで行う(ルールブック§6)。個体の入れ替えは得点にならない。"""
    d.to_game_play()
    swappable = "LMS/LM/LMS"  # クリア可能(3手・8箱=24点)。同サイズの入れ替え余地がある
    d.machine.on_cv_message(board_update(swappable, t_ms=d.now), d.now)
    out = d.press("enter")
    assert sent(out, "judge")[0].payload["result"] == "scored"
    assert sent(out, "judge")[0].payload["points"] == 24

    d.advance(1_000)
    # 盤面文字列は同じまま、A塔とC塔の小を入れ替える(CVは別の確定盤面として送る)
    swapped = board_update(swappable, t_ms=d.now)
    a, _b, c = swapped.tower_box_ids
    a[2], c[2] = c[2], a[2]
    d.machine.on_cv_message(swapped, d.now)
    out = d.press("enter")
    assert sent(out, "judge")[0].payload["result"] == "duplicate_same"
    assert sent(out, "judge")[0].payload["points"] == 0


def test_practice_not_recorded(d: Driver) -> None:
    d.to_practice()
    d.set_board(SCORED_BOARD)
    d.press("enter")
    assert d.store.ranking() == []


def test_game_resets_play_state_from_practice(d: Driver) -> None:
    d.to_practice()
    d.set_board(SCORED_BOARD)
    d.press("enter")
    d.press("left")
    d.press("enter")  # back → mode_select
    d.press("right")
    d.press("right")
    d.press("enter")  # → game_countdown
    d.advance(3_000)
    d.advance(JUDGE_COOLDOWN_MS)
    out = d.press("enter")  # 練習と同じ盤面でも scored になる(集合リセット)
    assert sent(out, "judge")[0].payload["result"] == "scored"
    assert sent(out, "judge")[0].payload["total_score"] == SCORED_POINTS


# ---- スナップショット(再接続復元。DoD) ----


def test_display_snapshot_restores_state(d: Driver) -> None:
    d.set_board(SCORED_BOARD)
    d.to_practice()
    d.set_board(MIRROR_A)
    d.press("enter")
    snap = d.machine.display_snapshot()
    assert snap["screen"] == "practice"
    assert snap["ctx"]["score"] == MIRROR_A_POINTS
    assert snap["lang"] == "ja"
    assert snap["board"] is not None
    assert snap["board"]["board"] == MIRROR_A
    assert "kind" not in snap["board"]


def test_display_snapshot_board_none_before_first_update(d: Driver) -> None:
    assert d.machine.display_snapshot()["board"] is None


def test_controller_snapshot_in_result_name_mode(d: Driver) -> None:
    d.to_result()
    d.machine.on_name_text("たろう", d.now)
    snap = d.machine.controller_snapshot()
    assert snap == {
        "screen": "result",
        "lang": "ja",
        "input_mode": "name",
        "name_text": "たろう",
    }
    d.machine.on_name_done(d.now)
    assert d.machine.controller_snapshot()["input_mode"] == "buttons"


def test_controller_snapshot_outside_result(d: Driver) -> None:
    snap = d.machine.controller_snapshot()
    assert snap == {"screen": "idle_title", "lang": "ja", "input_mode": "buttons", "name_text": ""}


# ---- ランキング・順位 ----


def test_provisional_rank_uses_fail_count_as_tiebreak(table: PrecomputeTable) -> None:
    store = MemoryStore()
    d = Driver(table, store)
    d.to_game_play()
    d.set_board(MIRROR_A)
    d.press("enter")  # 21点・失敗0
    d.advance(GAME_MS)
    d.machine.on_name_text("いちばん", d.now)
    d.machine.on_name_done(d.now)
    d.press("enter")
    # 2人目: 同点だが失敗1
    d2 = Driver(table, store)
    d2.to_game_play()
    d2.set_board(MIRROR_A)
    d2.press("enter")
    d2.advance(1_000)
    d2.set_board(UNCLEARABLE_BOARD)
    d2.press("enter")
    d2.advance(GAME_MS)
    ctx_rank = d2.machine.display_snapshot()["ctx"]["rank"]
    assert ctx_rank == 2  # 同点・失敗多で下位
    entries = store.ranking()
    assert [e.name for e in entries] == ["いちばん"]


def test_provisional_rank_exact_tie_ranks_below_earlier_play(table: PrecomputeTable) -> None:
    # score・fail_count が完全同点なら played_at 昇順(先勝ち)で新しいプレイが下位
    store = MemoryStore()
    d = Driver(table, store)
    d.to_game_play()
    d.set_board(MIRROR_A)
    d.press("enter")
    d.advance(GAME_MS)
    d.machine.on_name_text("せんこう", d.now)
    d.machine.on_name_done(d.now)
    d.press("enter")
    d2 = Driver(table, store)
    d2.to_game_play()
    d2.set_board(MIRROR_A)
    d2.press("enter")
    d2.advance(GAME_MS)
    assert d2.machine.display_snapshot()["ctx"]["rank"] == 2
