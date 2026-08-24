"""1 プレイの判定・得点・時間の集計(仕様書 §5、§6.4)。Pyxel に依存しない。

```
start(now) --> COUNTDOWN(3 秒: 「3」「2」「1」) --> PLAYING(60 秒。入場時に「GO」) --> FINISHED
```

時刻は `time.monotonic()` ベースの秒(float)を呼び出し側が毎回渡す(フレーム数で数えない)。
判定は `judge()` に盤面文字列と押下時刻を渡す。既存 `server/app/state/machine.py` の
`_judge_action()` / `_apply_judgement()` と同じ規則で集計する(要判断 #7: 切り出しまではここに写し、
テストで `StateMachine` と照合する)。

- scored: 得点加算、`judged_keys` / `judged_boards` へ追加
- unclearable: `fail_count += 1`
- duplicate_same / duplicate_mirror: 両集合へ追加(0 点、失敗にも数えない)
- 判定後 `JUDGE_COOLDOWN_SEC` はクールダウン。タイムアップ(`deadline`)以降の押下は無効、直前は有効
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Literal

from app.core.board import is_legal_board
from app.core.engine import Judgement, judge
from app.core.precompute import PrecomputeTable

COUNTDOWN_STEP_SEC: Final = 1.0
COUNTDOWN_STEPS: Final = 3  # 「3」「2」「1」。「GO」はプレイ開始と同時
GAME_SEC: Final = 60.0
JUDGE_COOLDOWN_SEC: Final = 0.5
GO_DISPLAY_SEC: Final = 1.0  # 「GO」を出す長さ(演出のみ。判定可否には関係しない)
LAST_SECONDS_WARNING: Final = 10  # 残り 10 秒で赤点滅(§3.4)
WARNING_BLINK_HZ: Final = 4  # 赤点滅の切替回数 / 秒(赤 0.25 秒 → 白 0.25 秒の交互)

JudgeResult = Literal["scored", "unclearable", "duplicate_same", "duplicate_mirror"]


class Phase(Enum):
    IDLE = "idle"  # start() 前
    COUNTDOWN = "countdown"
    PLAYING = "playing"
    FINISHED = "finished"


class JudgeRejection(Enum):
    """判定が受け付けられなかった理由(呼び出し側は音も演出も出さない)。"""

    NOT_PLAYING = "not_playing"  # カウントダウン中 / 終了後 / 未開始
    TIME_UP = "time_up"  # 押下時刻が deadline 以降
    COOLDOWN = "cooldown"
    ILLEGAL_BOARD = "illegal_board"  # 盤面文字列が合法でない(通常は起きない)


@dataclass(frozen=True)
class JudgeRecord:
    """1 回の判定(リザルトの「最高得点盤面」用)。"""

    seq: int
    board: str
    elapsed_sec: float
    result: JudgeResult
    points: int
    min_moves: int | None


class SessionEvent(Enum):
    """`poll()` が返す時間起因のイベント(効果音・演出のトリガ)。"""

    COUNTDOWN_TICK = "countdown_tick"  # 「3」「2」「1」の表示が変わった
    GO = "go"  # プレイ開始
    TIME_UP = "time_up"


@dataclass
class GameSession:
    """1 プレイの状態。`start()` 後は毎フレーム `poll(now)` を呼ぶ。"""

    table: PrecomputeTable
    countdown_sec: float = COUNTDOWN_STEPS * COUNTDOWN_STEP_SEC
    game_sec: float = GAME_SEC
    cooldown_sec: float = JUDGE_COOLDOWN_SEC

    score: int = 0
    fail_count: int = 0
    judge_count: int = 0
    judged_keys: set[str] = field(default_factory=set)
    judged_boards: set[str] = field(default_factory=set)
    records: list[JudgeRecord] = field(default_factory=list)

    _phase: Phase = Phase.IDLE
    _countdown_started_at: float = 0.0
    _started_at: float = 0.0
    _deadline: float = 0.0
    _last_judge_at: float | None = None
    _countdown_shown: int = 0  # poll() が最後に通知したカウントダウン段(3, 2, 1)
    _go_emitted: bool = False
    _time_up_emitted: bool = False

    # ---- 開始・フェーズ ----

    def start(self, now: float) -> None:
        """カウントダウンを開始する。集計はリセットされる。"""
        self.score = 0
        self.fail_count = 0
        self.judge_count = 0
        self.judged_keys = set()
        self.judged_boards = set()
        self.records = []
        self._last_judge_at = None
        self._phase = Phase.COUNTDOWN
        self._countdown_started_at = now
        self._started_at = now + self.countdown_sec
        self._deadline = self._started_at + self.game_sec
        self._countdown_shown = 0
        self._go_emitted = False
        self._time_up_emitted = False

    @property
    def started_at(self) -> float:
        """プレイ開始(「GO」)の時刻。カウントダウン中は予定時刻。"""
        return self._started_at

    @property
    def deadline(self) -> float:
        return self._deadline

    def phase(self, now: float) -> Phase:
        if self._phase is Phase.IDLE:
            return Phase.IDLE
        if now < self._started_at:
            return Phase.COUNTDOWN
        if now < self._deadline:
            return Phase.PLAYING
        return Phase.FINISHED

    def is_over(self, now: float) -> bool:
        return self.phase(now) is Phase.FINISHED

    def poll(self, now: float) -> list[SessionEvent]:
        """時間起因のイベントを(発生順に、1 回ずつ)返す。毎フレーム呼ぶ。"""
        events: list[SessionEvent] = []
        if self._phase is Phase.IDLE:
            return events
        value = self.countdown_value(now)
        if value is not None and value != self._countdown_shown:
            self._countdown_shown = value
            events.append(SessionEvent.COUNTDOWN_TICK)
        if now >= self._started_at and not self._go_emitted:
            self._go_emitted = True
            events.append(SessionEvent.GO)
        if now >= self._deadline and not self._time_up_emitted:
            self._time_up_emitted = True
            events.append(SessionEvent.TIME_UP)
        return events

    # ---- 表示用 ----

    def countdown_value(self, now: float) -> int | None:
        """カウントダウン中の表示数字(3 → 2 → 1)。カウントダウン中でなければ None。"""
        if self.phase(now) is not Phase.COUNTDOWN:
            return None
        elapsed = now - self._countdown_started_at
        return max(1, COUNTDOWN_STEPS - math.floor(elapsed / COUNTDOWN_STEP_SEC))

    def countdown_age(self, now: float) -> float | None:
        """現在のカウントダウン数字が出てからの経過秒(ポップ演出用)。カウントダウン外は None。"""
        if self.countdown_value(now) is None:
            return None
        elapsed = now - self._countdown_started_at
        return elapsed - math.floor(elapsed / COUNTDOWN_STEP_SEC) * COUNTDOWN_STEP_SEC

    def show_go(self, now: float) -> bool:
        """「GO!」を表示する期間(プレイ開始直後 `GO_DISPLAY_SEC`)。"""
        return self._phase is not Phase.IDLE and 0.0 <= now - self._started_at < GO_DISPLAY_SEC

    def remaining_sec(self, now: float) -> float:
        """残り時間(秒)。カウントダウン中は満タン、終了後は 0。"""
        if self._phase is Phase.IDLE:
            return self.game_sec
        return min(self.game_sec, max(0.0, self._deadline - now))

    def remaining_display(self, now: float) -> str:
        """`M:SS` 表示。秒単位に切り上げる(1:00 → 0:59 → ... → 0:00。§6.4)。"""
        total = math.ceil(self.remaining_sec(now) - 1e-9)
        return f"{total // 60}:{total % 60:02d}"

    def in_warning(self, now: float) -> bool:
        """残り 10 秒以内(数字を赤点滅させる)。"""
        return self.phase(now) is Phase.PLAYING and self.remaining_sec(now) <= LAST_SECONDS_WARNING

    def warning_blink(self, now: float) -> bool:
        """赤点滅の「いま赤」フェーズか。deadline 基準なので交互周期が壁時計に依らず安定する。"""
        if not self.in_warning(now):
            return False
        return int((self._deadline - now) * WARNING_BLINK_HZ) % 2 == 0

    def cooldown_remaining(self, now: float) -> float:
        if self._last_judge_at is None:
            return 0.0
        return max(0.0, self._last_judge_at + self.cooldown_sec - now)

    # ---- 判定 ----

    def can_judge(self, now: float) -> JudgeRejection | None:
        """判定を受け付けられるか。受け付けられないなら理由、受け付けられるなら None。"""
        if self._phase is Phase.IDLE or now < self._started_at:
            return JudgeRejection.NOT_PLAYING
        if now >= self._deadline:
            return JudgeRejection.TIME_UP
        if self.cooldown_remaining(now) > 0.0:
            return JudgeRejection.COOLDOWN
        return None

    def judge(self, board: str, now: float) -> Judgement | JudgeRejection:
        """盤面を判定して集計する。`now` は JUDGE の押下時刻(タイムアップ直前なら有効)。"""
        rejection = self.can_judge(now)
        if rejection is not None:
            return rejection
        if not is_legal_board(board):
            return JudgeRejection.ILLEGAL_BOARD
        judgement = judge(board, self.judged_keys, self.judged_boards, self.table)
        self._last_judge_at = now
        self.judge_count += 1
        self._apply_judgement(board, judgement)
        self.records.append(
            JudgeRecord(
                seq=self.judge_count,
                board=board,
                elapsed_sec=now - self._started_at,
                result=judgement.result,
                points=judgement.points,
                min_moves=judgement.min_moves,
            )
        )
        return judgement

    def _apply_judgement(self, raw_board: str, judgement: Judgement) -> None:
        # server/app/state/machine.py `StateMachine._apply_judgement()` と同じ規則
        if judgement.result == "scored":
            self.score += judgement.points
            self.judged_keys.add(judgement.canonical_key)
            self.judged_boards.add(raw_board)
        elif judgement.result == "unclearable":
            self.fail_count += 1
        else:  # duplicate_same / duplicate_mirror も両集合へ(game-core-api.md §2)
            self.judged_keys.add(judgement.canonical_key)
            self.judged_boards.add(raw_board)

    # ---- リザルト用 ----

    @property
    def best(self) -> JudgeRecord | None:
        """今回の最高得点盤面(同点は先に判定したもの)。得点した判定が無ければ None。"""
        scored = [r for r in self.records if r.result == "scored"]
        if not scored:
            return None
        return max(scored, key=lambda r: (r.points, -r.seq))
