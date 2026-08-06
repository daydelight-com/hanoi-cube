"""サーバー状態機械(契約: docs/contracts/screens.md の遷移表を実装)。

全メソッドは単調増加のミリ秒時刻 now_ms を受け取り、送信すべきメッセージ
(Outbound のリスト)を返す純粋寄りの設計。実時間・WS・CVポーリングはAPI層
(app/api/ws.py)が担い、テストは時刻を注入して遷移表を決定的に検証する。
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal

from app.api.messages import (
    ButtonName,
    CountdownValue,
    FlashResult,
    InputMode,
    JudgePayload,
    Lang,
    Outbound,
    ScreenId,
)
from app.core.engine import Judgement, judge
from app.core.precompute import PrecomputeTable
from app.cv.interface import CvBoardUpdate
from app.state.store import JudgementRecord, PlayRecord, PlayStore

# タイマー定数(仕様§5)。idle_ranking の表示時間はクライアント演出に依存するため
# 行数比例+クランプの暫定値(S4で調整。handoff/S2.md 要判断参照)
TITLE_MS = 5_000
IDLE_RANKING_ROW_MS = 1_000
IDLE_RANKING_SCROLL_MIN_MS = 2_000
IDLE_RANKING_SCROLL_MAX_MS = 27_000
IDLE_RANKING_TAIL_MS = 3_000  # 1位表示+3秒
COUNTDOWN_STEP_MS = 1_000
GAME_MS = 60_000
JUDGE_COOLDOWN_MS = 500
RANKING_GUARD_MS = 3_000
QR_GUARD_MS = 5_000
NAME_MAX_CHARS = 10
RULE_PAGE_COUNT = 5

# 記録画面URLの基底(S9で確定。プレイIDを連結してQRに載せる)
DEFAULT_RECORD_URL_BASE = "https://hanoi-cube.example.com/records/"

ModeFocus = Literal["rules", "practice", "game", "lang"]
_MODE_FOCUS_ORDER: tuple[ModeFocus, ...] = ("rules", "practice", "game", "lang")
_COUNTDOWN_VALUES: tuple[CountdownValue, ...] = ("3", "2", "1", "go")

_FLASH_OF: dict[str, FlashResult] = {
    "scored": "scored",
    "unclearable": "failed",
    "duplicate_same": "duplicate",
    "duplicate_mirror": "duplicate",
}


def _default_played_at() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class StateMachine:
    """screens.md の遷移表(§3)・判定アクション(§4)・ctx型(§5)の実装。"""

    def __init__(
        self,
        table: PrecomputeTable,
        store: PlayStore,
        *,
        now_ms: int = 0,
        record_url_base: str = DEFAULT_RECORD_URL_BASE,
        id_factory: Callable[[], str] = lambda: str(uuid.uuid4()),
        played_at_factory: Callable[[], str] = _default_played_at,
    ) -> None:
        self._table = table
        self._store = store
        self._record_url_base = record_url_base
        self._id_factory = id_factory
        self._played_at_factory = played_at_factory

        self.screen: ScreenId = "idle_title"
        self.lang: Lang = "ja"
        self._last_board: CvBoardUpdate | None = None
        self._entered_ms = now_ms

        # mode_select / rule_dialog
        self._mode_focus: ModeFocus = "rules"
        self._rule_from: Literal["mode_select", "practice"] = "mode_select"
        self._rule_page = 0

        # practice / game 共通のプレイ状態
        self._score = 0
        self._fail_count = 0
        self._seq = 0
        self._judged_keys: set[str] = set()
        self._judged_boards: set[str] = set()
        self._scored_seq_by_key: dict[str, int] = {}
        self._judgements: list[JudgementRecord] = []
        self._last_judge_ms: int | None = None

        # practice
        self._selection: Literal["back", "help"] | None = None

        # game
        self._play_id = ""
        self._countdown_k = 0  # 消化済みカウントダウン段数(0=「3」表示中)
        self._play_start_ms = 0
        self._timer_k = 1  # 次に配信する timer の秒数インデックス
        self._remaining_ms = GAME_MS

        # result / ranking / qr
        self._name_text = ""
        self._result_focus: Literal["input", "decide"] = "decide"
        self._input_mode: InputMode = "name"
        self._rank = 1
        self._highlight_play_id: str | None = None
        self._idle_ranking_ms = TITLE_MS

    # ---- 入力イベント ----

    def on_button(self, button: ButtonName, now_ms: int) -> list[Outbound]:
        """iPadボタン。遷移表にない組は無視する(音・演出も出さない)。"""
        handlers: dict[ScreenId, Callable[[ButtonName, int], list[Outbound]]] = {
            "idle_title": self._button_idle_title,
            "idle_ranking": self._button_idle_ranking,
            "mode_select": self._button_mode_select,
            "rule_dialog": self._button_rule_dialog,
            "practice": self._button_practice,
            "game_play": self._button_game_play,
            "result": self._button_result,
            "ranking": self._button_ranking,
            "qr": self._button_qr,
        }
        handler = handlers.get(self.screen)
        if handler is None:  # game_countdown は全ボタン無効
            return []
        return handler(button, now_ms)

    def on_name_text(self, text: str, now_ms: int) -> list[Outbound]:
        """名前入力の変化(result のみ有効)。10文字に切り詰める。"""
        if self.screen != "result":
            return []
        self._name_text = text[:NAME_MAX_CHARS]
        return [Outbound("display", "name", {"text": self._name_text})]

    def on_name_done(self, now_ms: int) -> list[Outbound]:
        """ソフトウェアキーボードの完了(行21)。"""
        if self.screen != "result":
            return []
        self._input_mode = "buttons"
        self._result_focus = "decide"
        return [self._input_mode_msg(), self._screen_msg()]

    def on_cv_message(self, update: CvBoardUpdate, now_ms: int) -> list[Outbound]:
        """確定盤面の更新。practice の選択解除(行13)にも使う。

        CvBoardUpdate は盤面変化時のみ届く(cv-interface.md §3)ため、
        受信そのものを box_moved イベントとみなす。
        """
        self._last_board = update
        out = [Outbound("display", "board", update.model_dump(mode="json", exclude={"kind"}))]
        if self.screen == "practice" and self._selection is not None:
            self._selection = None
            out.append(self._screen_msg())
        return out

    def tick(self, now_ms: int) -> list[Outbound]:
        """タイマー起因の遷移・配信。API層が短い周期で呼ぶ。"""
        if self.screen == "idle_title":
            if now_ms - self._entered_ms >= TITLE_MS:
                return self._enter_idle_ranking(now_ms)
        elif self.screen == "idle_ranking":
            if now_ms - self._entered_ms >= self._idle_ranking_ms:
                return self._enter_idle_title(now_ms)
        elif self.screen == "game_countdown":
            return self._tick_countdown(now_ms)
        elif self.screen == "game_play":
            return self._tick_game(now_ms)
        return []

    # ---- スナップショット(再接続復元。ws-messages.md §3) ----

    def display_snapshot(self) -> dict[str, Any]:
        board = self._last_board
        return {
            "screen": self.screen,
            "ctx": self._ctx(),
            "lang": self.lang,
            "board": None if board is None else board.model_dump(mode="json", exclude={"kind"}),
        }

    def controller_snapshot(self) -> dict[str, Any]:
        return {
            "screen": self.screen,
            "lang": self.lang,
            "input_mode": self._controller_input_mode(),
            "name_text": self._name_text if self.screen == "result" else "",
        }

    # ---- ボタン処理(画面別) ----

    def _button_idle_title(self, button: ButtonName, now_ms: int) -> list[Outbound]:
        if button == "enter":  # 行2
            return self._enter_mode_select(now_ms)
        return []

    def _button_idle_ranking(self, button: ButtonName, now_ms: int) -> list[Outbound]:
        if button == "enter":  # 行4
            return self._enter_idle_title(now_ms)
        return []

    def _button_mode_select(self, button: ButtonName, now_ms: int) -> list[Outbound]:
        if button in ("left", "right"):  # 行5(端はループ。S5で確定)
            i = _MODE_FOCUS_ORDER.index(self._mode_focus)
            j = (i + (1 if button == "right" else -1)) % len(_MODE_FOCUS_ORDER)
            self._mode_focus = _MODE_FOCUS_ORDER[j]
            return [self._screen_msg()]
        if self._mode_focus == "rules":  # 行6
            return self._enter_rule_dialog(now_ms, from_="mode_select")
        if self._mode_focus == "practice":  # 行7
            self._reset_play()
            return self._enter_practice(now_ms)
        if self._mode_focus == "game":  # 行8
            self._reset_play()
            self._play_id = self._id_factory()
            return self._enter_game_countdown(now_ms)
        # 行9: 言語トグル+全体配信
        self.lang = "en" if self.lang == "ja" else "ja"
        return self._lang_msgs()

    def _button_rule_dialog(self, button: ButtonName, now_ms: int) -> list[Outbound]:
        if button in ("left", "right"):  # 行10(クランプ)
            delta = 1 if button == "right" else -1
            page = max(0, min(RULE_PAGE_COUNT - 1, self._rule_page + delta))
            if page == self._rule_page:
                return []
            self._rule_page = page
            return [self._screen_msg()]
        # 行11: 閉じて呼び出し元へ(呼び出し元の状態は保持)
        if self._rule_from == "practice":
            return self._enter_practice(now_ms)
        return self._enter_mode_select(now_ms, keep_focus=True)

    def _button_practice(self, button: ButtonName, now_ms: int) -> list[Outbound]:
        if button in ("left", "right"):  # 行12: 選択状態の有効化+focus移動
            selection: Literal["back", "help"] = "back" if button == "left" else "help"
            if selection == self._selection:
                return []
            self._selection = selection
            return [self._screen_msg()]
        if self._selection == "back":  # 行14
            return self._enter_mode_select(now_ms)
        if self._selection == "help":  # 行15
            return self._enter_rule_dialog(now_ms, from_="practice")
        return self._judge_action(now_ms)  # 行16

    def _button_game_play(self, button: ButtonName, now_ms: int) -> list[Outbound]:
        if button != "enter":
            return []
        if now_ms >= self._play_start_ms + GAME_MS:  # 残時間>0 のガード(行18)
            return []
        return self._judge_action(now_ms)

    def _button_result(self, button: ButtonName, now_ms: int) -> list[Outbound]:
        if button in ("left", "right"):  # 行22: buttonsモードのみ
            if self._input_mode != "buttons":
                return []
            focus: Literal["input", "decide"] = "input" if button == "left" else "decide"
            if focus == self._result_focus:
                return []
            self._result_focus = focus
            return [self._screen_msg()]
        if self._result_focus == "input":  # 行23: 再入力
            self._input_mode = "name"
            return [self._input_mode_msg(), self._screen_msg()]
        # 行24: 決定(1〜10文字のときのみ)
        if not 1 <= len(self._name_text) <= NAME_MAX_CHARS:
            return []
        record = PlayRecord(
            play_id=self._play_id,
            name=self._name_text,
            score=self._score,
            fail_count=self._fail_count,
            played_at=self._played_at_factory(),
            judgements=list(self._judgements),
        )
        self._store.save_play(record)  # クラウドアップロードキュー投入はS9で追加
        self._highlight_play_id = self._play_id
        return self._enter_ranking(now_ms)

    def _button_ranking(self, button: ButtonName, now_ms: int) -> list[Outbound]:
        if button != "enter" or now_ms - self._entered_ms < RANKING_GUARD_MS:  # 行25
            return []
        return self._enter_qr(now_ms)

    def _button_qr(self, button: ButtonName, now_ms: int) -> list[Outbound]:
        if button != "enter" or now_ms - self._entered_ms < QR_GUARD_MS:  # 行26
            return []
        return self._enter_idle_title(now_ms)

    # ---- 判定アクション(screens.md §4、行16・18共通) ----

    def _judge_action(self, now_ms: int) -> list[Outbound]:
        board = self._last_board
        if board is None or not board.legal:
            return []
        if self._last_judge_ms is not None and now_ms - self._last_judge_ms < JUDGE_COOLDOWN_MS:
            return []
        judgement = judge(board.board, self._judged_keys, self._judged_boards, self._table)
        self._last_judge_ms = now_ms
        self._seq += 1
        self._apply_judgement(board.board, judgement)
        if self.screen == "game_play":  # 本番のみ判定履歴を記録(§4-4)
            dup_of_seq = None
            if judgement.result in ("duplicate_same", "duplicate_mirror"):
                dup_of_seq = self._scored_seq_by_key.get(judgement.canonical_key)
            self._judgements.append(
                JudgementRecord(
                    seq=self._seq,
                    board=board.board,
                    elapsed_ms=now_ms - self._play_start_ms,
                    result=judgement.result,
                    points=judgement.points,
                    min_moves=judgement.min_moves,
                    dup_of_seq=dup_of_seq,
                    tower_box_ids=board.tower_box_ids,
                )
            )
        payload = JudgePayload(
            seq=self._seq,
            result=judgement.result,
            points=judgement.points,
            min_moves=judgement.min_moves,
            board=board.board,
            total_score=self._score,
            fail_count=self._fail_count,
        )
        return [
            Outbound("display", "judge", payload.model_dump(mode="json")),
            Outbound("controller", "flash", {"result": _FLASH_OF[judgement.result]}),
            self._screen_msg(),
        ]

    def _apply_judgement(self, raw_board: str, judgement: Judgement) -> None:
        if judgement.result == "scored":
            self._score += judgement.points
            self._judged_keys.add(judgement.canonical_key)
            self._judged_boards.add(raw_board)
            self._scored_seq_by_key[judgement.canonical_key] = self._seq
        elif judgement.result == "unclearable":
            self._fail_count += 1  # 同点時の順位第2キー(ルールブック§6)
        else:  # duplicate_same / duplicate_mirror も両集合へ追加(game-core-api.md §2)
            self._judged_keys.add(judgement.canonical_key)
            self._judged_boards.add(raw_board)

    def _reset_play(self) -> None:
        self._score = 0
        self._fail_count = 0
        self._seq = 0
        self._judged_keys = set()
        self._judged_boards = set()
        self._scored_seq_by_key = {}
        self._judgements = []
        self._last_judge_ms = None
        self._selection = None

    # ---- タイマー処理 ----

    def _tick_countdown(self, now_ms: int) -> list[Outbound]:
        out: list[Outbound] = []
        elapsed = now_ms - self._entered_ms
        while self._countdown_k < 3 and elapsed >= (self._countdown_k + 1) * COUNTDOWN_STEP_MS:
            self._countdown_k += 1
            value = _COUNTDOWN_VALUES[self._countdown_k]
            out.append(Outbound("display", "countdown", {"value": value}))
            if value == "go":  # 行17: GOと同時に計測開始(仕様§5.6)
                out += self._enter_game_play(self._entered_ms + 3 * COUNTDOWN_STEP_MS)
                break
        return out

    def _tick_game(self, now_ms: int) -> list[Outbound]:
        out: list[Outbound] = []
        while self.screen == "game_play" and now_ms - self._play_start_ms >= self._timer_k * 1_000:
            remaining = GAME_MS - self._timer_k * 1_000
            self._remaining_ms = remaining
            self._timer_k += 1
            out.append(Outbound("display", "timer", {"remaining_ms": remaining}))
            if remaining <= 0:  # 行19: 結果確定
                out += self._enter_result(now_ms)
        return out

    # ---- 画面入場 ----

    def _enter(self, screen: ScreenId, now_ms: int) -> None:
        self.screen = screen
        self._entered_ms = now_ms

    def _enter_idle_title(self, now_ms: int) -> list[Outbound]:
        self._enter("idle_title", now_ms)
        out: list[Outbound] = []
        if self.lang != "ja":  # 入場時に言語をjaへリセット(仕様§5.13)
            self.lang = "ja"
            out += self._lang_msgs()
        out.append(self._screen_msg())
        return out

    def _enter_idle_ranking(self, now_ms: int) -> list[Outbound]:
        self._enter("idle_ranking", now_ms)
        entries = self._store.ranking()
        scroll = min(
            IDLE_RANKING_SCROLL_MAX_MS,
            max(IDLE_RANKING_SCROLL_MIN_MS, len(entries) * IDLE_RANKING_ROW_MS),
        )
        self._idle_ranking_ms = scroll + IDLE_RANKING_TAIL_MS
        return [
            self._screen_msg(),
            self._ranking_msg(highlight=None),
        ]

    def _enter_mode_select(self, now_ms: int, *, keep_focus: bool = False) -> list[Outbound]:
        if not keep_focus:
            self._mode_focus = "rules"
        self._enter("mode_select", now_ms)
        return [self._screen_msg()]

    def _enter_rule_dialog(
        self, now_ms: int, *, from_: Literal["mode_select", "practice"]
    ) -> list[Outbound]:
        self._rule_from = from_
        self._rule_page = 0
        self._enter("rule_dialog", now_ms)
        return [self._screen_msg()]

    def _enter_practice(self, now_ms: int) -> list[Outbound]:
        self._enter("practice", now_ms)
        return [self._screen_msg()]

    def _enter_game_countdown(self, now_ms: int) -> list[Outbound]:
        self._countdown_k = 0
        self._enter("game_countdown", now_ms)
        return [self._screen_msg(), Outbound("display", "countdown", {"value": "3"})]

    def _enter_game_play(self, now_ms: int) -> list[Outbound]:
        self._play_start_ms = now_ms
        self._timer_k = 1
        self._remaining_ms = GAME_MS
        self._enter("game_play", now_ms)
        return [self._screen_msg(), Outbound("display", "timer", {"remaining_ms": GAME_MS})]

    def _enter_result(self, now_ms: int) -> list[Outbound]:
        self._rank = self._store.provisional_rank(self._score, self._fail_count)
        self._name_text = ""
        self._result_focus = "decide"
        self._input_mode = "name"  # 入場時にiPadをname入力モードへ(行19)
        self._enter("result", now_ms)
        return [self._screen_msg(), self._input_mode_msg()]

    def _enter_ranking(self, now_ms: int) -> list[Outbound]:
        # result 退場時は iPad を buttons へ戻す(ws-messages.md §5「リザルト入退場」)
        self._input_mode = "buttons"
        self._enter("ranking", now_ms)
        return [
            self._screen_msg(),
            self._ranking_msg(highlight=self._highlight_play_id),
            self._input_mode_msg(),
        ]

    def _enter_qr(self, now_ms: int) -> list[Outbound]:
        self._enter("qr", now_ms)
        return [self._screen_msg()]

    # ---- メッセージ構築 ----

    def _ctx(self) -> dict[str, Any]:
        """画面別 ctx(screens.md §5)。"""
        if self.screen == "idle_ranking":
            return {"entries": [e.model_dump(mode="json") for e in self._store.ranking()]}
        if self.screen == "mode_select":
            return {"focus": self._mode_focus}
        if self.screen == "rule_dialog":
            return {"from": self._rule_from, "page": self._rule_page, "page_count": RULE_PAGE_COUNT}
        if self.screen == "practice":
            return {"score": self._score, "selection": self._selection}
        if self.screen == "game_countdown":
            return {"value": _COUNTDOWN_VALUES[self._countdown_k]}
        if self.screen == "game_play":
            return {
                "score": self._score,
                "fail_count": self._fail_count,
                "remaining_ms": self._remaining_ms,
            }
        if self.screen == "result":
            return {
                "score": self._score,
                "fail_count": self._fail_count,
                "rank": self._rank,
                "name_text": self._name_text,
                "focus": self._result_focus,
                "input_mode": self._input_mode,
            }
        if self.screen == "ranking":
            return {
                "entries": [e.model_dump(mode="json") for e in self._store.ranking()],
                "highlight_play_id": self._highlight_play_id,
            }
        if self.screen == "qr":
            return {"url": self._record_url_base + self._play_id, "play_id": self._play_id}
        return {}  # idle_title

    def _screen_msg(self) -> Outbound:
        return Outbound("display", "screen", {"screen": self.screen, "ctx": self._ctx()})

    def _lang_msgs(self) -> list[Outbound]:
        return [
            Outbound("display", "lang", {"lang": self.lang}),
            Outbound("controller", "lang", {"lang": self.lang}),
        ]

    def _input_mode_msg(self) -> Outbound:
        return Outbound(
            "controller",
            "input_mode",
            {"mode": self._input_mode, "name_text": self._name_text},
        )

    def _ranking_msg(self, *, highlight: str | None) -> Outbound:
        return Outbound(
            "display",
            "ranking",
            {
                "entries": [e.model_dump(mode="json") for e in self._store.ranking()],
                "highlight_play_id": highlight,
            },
        )

    def _controller_input_mode(self) -> InputMode:
        if self.screen == "result":
            return self._input_mode
        return "buttons"
