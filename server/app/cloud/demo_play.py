"""全512盤面を判定履歴に持つデモ用プレイ記録の生成(scripts/generate_all_patterns_play.py の本体)。

記録画面(`cloud/record/`)で全パターンの表示・最短手順再生を確認するための合成データ。
実プレイではなく、判定エンジン(core/engine.py)の結果をそのまま並べたものである。

判定履歴の並び(ユーザー指定):

1. `scored` — 得点降順(同点は円盤数昇順→正準キーの辞書順。score_ranking.md と同じ順序)
2. `duplicate_mirror` — 上で得点したクラスの鏡像盤面。0点。同じクラス順で並べる
3. `unclearable` — クリア不可盤面(=失敗パターン)を最後にまとめる

`duplicate_same` は出現しない(同じ盤面文字列は1回しか置かないため)。

得点・重複・クリア可否の判定は engine.judge に委ね、ここでは順序と体裁だけを組み立てる。
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from app.cloud.reset import cloud_target_description
from app.cloud.uploader import make_firestore_client, play_document
from app.core.board import board_from_index, box_count, canonical_key, mirror_board
from app.core.engine import judge
from app.core.precompute import PrecomputeTable, load_table
from app.cv.interface import BOX_IDS, BoxId
from app.state.machine import GAME_MS  # elapsed_ms を本番と同じプレイ時間に収めるため
from app.state.store import JudgementRecord, PlayRecord

# プレイヤー名の長さ(firestore.md §1: 1〜10文字)
NAME_MIN_LEN = 1
NAME_MAX_LEN = 10

DEFAULT_PLAY_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_NAME = "ぜんパターン"
DEFAULT_PLAYED_AT = "2026-08-06T00:00:00+09:00"

_SIZE_TO_PREFIX = {"L": "large", "M": "medium", "S": "small"}


def tower_box_ids(board: str) -> tuple[list[BoxId], list[BoxId], list[BoxId]]:
    """盤面の各箱に個体IDを割り当てる(A→B→C、下から上の順に large-1, large-2, ...)。

    どの個体をどこに割り当てても盤面は同型なので、出現順の代表割り当てを使う
    (precompute.label_boxes と同じ考え方)。表示専用(firestore.md §1)。
    """
    serial = {"L": 1, "M": 1, "S": 1}
    towers: list[list[BoxId]] = []
    for tower in board.split("/"):
        ids: list[BoxId] = []
        for size in tower:
            box_id = f"{_SIZE_TO_PREFIX[size]}-{serial[size]}"
            if box_id not in BOX_IDS:  # 各サイズ3個を超えることは合法盤面では起きない
                raise ValueError(f"box overflow in board {board!r}: {box_id}")
            ids.append(box_id)
            serial[size] += 1
        towers.append(ids)
    return (towers[0], towers[1], towers[2])


def ordered_boards(table: PrecomputeTable) -> list[str]:
    """全512盤面を「得点降順 → 鏡像(重複) → クリア不可」の順に並べる。"""
    scored: list[tuple[int, int, str]] = []
    unclearable: list[str] = []
    for index in range(512):
        board = board_from_index(index)
        entry = table.entry(board)
        if not entry.clearable:
            unclearable.append(board)
        elif board == entry.canonical_key:  # クラス代表のみを得点側に置く
            assert entry.min_moves is not None
            boxes = box_count(board)
            scored.append((-boxes * entry.min_moves, boxes, board))
    scored.sort()
    representatives = [board for _, _, board in scored]
    # 左右対称な盤面は鏡像が自分自身なので重複判定は発生しない(代表1つで全盤面を尽くす)
    mirrors = [mirror_board(board) for board in representatives if mirror_board(board) != board]
    return representatives + mirrors + unclearable


def build_all_patterns_play(
    *,
    table: PrecomputeTable | None = None,
    play_id: str = DEFAULT_PLAY_ID,
    name: str = DEFAULT_NAME,
    played_at: str = DEFAULT_PLAYED_AT,
) -> PlayRecord:
    """全512盤面を判定履歴に持つプレイ記録を組み立てる。"""
    if not NAME_MIN_LEN <= len(name) <= NAME_MAX_LEN:
        raise ValueError(f"player_name must be {NAME_MIN_LEN}-{NAME_MAX_LEN} chars: {name!r}")
    table = table or load_table()
    boards = ordered_boards(table)
    judged_keys: set[str] = set()
    judged_boards: set[str] = set()
    scored_seq_by_key: dict[str, int] = {}
    judgements: list[JudgementRecord] = []
    score = 0
    fail_count = 0
    for seq, board in enumerate(boards, start=1):
        result = judge(board, judged_keys, judged_boards, table)
        if result.result == "scored":
            score += result.points
            scored_seq_by_key[result.canonical_key] = seq
        elif result.result == "unclearable":
            fail_count += 1  # 順位の第2キー(ルールブック§6)。重複は失敗に数えない
        if result.result != "unclearable":  # 判定済み集合に入るのは合法クリア判定のみ
            judged_keys.add(result.canonical_key)
            judged_boards.add(board)
        judgements.append(
            JudgementRecord(
                seq=seq,
                board=board,
                # 60秒のプレイ時間に均等割りして単調増加させる(合成データ)
                elapsed_ms=seq * GAME_MS // (len(boards) + 1),
                result=result.result,
                points=result.points,
                min_moves=result.min_moves,
                dup_of_seq=(
                    scored_seq_by_key.get(canonical_key(board))
                    if result.result.startswith("duplicate")
                    else None
                ),
                tower_box_ids=tower_box_ids(board),
            )
        )
    return PlayRecord(
        play_id=play_id,
        name=name,
        score=score,
        fail_count=fail_count,
        played_at=played_at,
        judgements=judgements,
    )


class PlaysSink(Protocol):
    """1プレイ分の書き込み先。失敗は例外で伝える。"""

    def upload(self, record: PlayRecord) -> None: ...


class FirestorePlaysSink:
    """Admin SDK 経由で plays/{play_id} に set() する(冪等)。"""

    def __init__(self) -> None:
        self._db = make_firestore_client()

    def upload(self, record: PlayRecord) -> None:
        self._db.collection("plays").document(record.play_id).set(play_document(record))


def run_cli(
    argv: list[str] | None = None,
    *,
    sink_factory: Callable[[], PlaysSink] = FirestorePlaysSink,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> int:
    """確認プロンプト付き CLI。返り値は終了コード。"""
    parser = argparse.ArgumentParser(
        prog="generate_all_patterns_play",
        description="全512盤面の判定履歴を持つデモ用プレイ記録を作って Firestore に投入する",
    )
    parser.add_argument("--play-id", default=DEFAULT_PLAY_ID, help="ドキュメントID(play_id)")
    parser.add_argument("--name", default=DEFAULT_NAME, help="プレイヤー名(1〜10文字)")
    parser.add_argument("--played-at", default=DEFAULT_PLAYED_AT, help="played_at(ISO8601)")
    parser.add_argument("--out", type=Path, help="投入せずにJSONを書き出すだけにする")
    args = parser.parse_args(argv)

    try:
        record = build_all_patterns_play(
            play_id=args.play_id, name=args.name, played_at=args.played_at
        )
    except ValueError as exc:
        print_fn(f"エラー: {exc}")
        return 2
    counts: dict[str, int] = {}
    for j in record.judgements:
        counts[j.result] = counts.get(j.result, 0) + 1
    print_fn(
        f"生成: {len(record.judgements)}判定 "
        f"(scored {counts.get('scored', 0)} / "
        f"duplicate_mirror {counts.get('duplicate_mirror', 0)} / "
        f"unclearable {counts.get('unclearable', 0)})"
    )
    print_fn(
        f"  play_id={record.play_id} name={record.name} score={record.score} "
        f"fail_count={record.fail_count}"
    )

    if args.out is not None:
        payload = json.dumps(play_document(record), ensure_ascii=False, indent=1)
        args.out.write_text(payload + "\n", encoding="utf-8")
        print_fn(f"書き出しました: {args.out}(投入はしていません)")
        return 0

    target = cloud_target_description()
    if target is None:
        print_fn(
            "エラー: Firestore の接続設定がありません。\n"
            "  本番:       リポジトリ直下に service-account.json を置く"
            "(または HANOI_FIREBASE_CREDENTIALS=<鍵のパス>)\n"
            "  エミュレータ: FIRESTORE_EMULATOR_HOST=127.0.0.1:8080"
            " HANOI_FIREBASE_PROJECT=demo-hanoi"
        )
        return 2
    print_fn(f"投入先: {target} — plays/{record.play_id} を set()(既存があれば上書き)")
    print_fn(
        f"注意: score={record.score} はランキング1位になります"
        f"(ランキングから消すには plays/{record.play_id} を削除)"
    )
    answer = input_fn('投入しますか? 実行するには "yes" と入力: ')
    if answer.strip() != "yes":
        print_fn("中止しました(何も書き込んでいません)")
        return 1
    try:
        sink_factory().upload(record)
    except Exception as exc:
        print_fn(f"エラー: 投入に失敗しました: {exc}")
        return 3
    print_fn(f"完了: plays/{record.play_id} を投入しました")
    if base := os.environ.get("HANOI_RECORD_URL_BASE"):
        print_fn(f"記録画面: {base}{record.play_id}")
    return 0
