"""モックCVの対話CLI(make mock)。

キーボード操作で「箱を掴む・塔/待機エリアに置く」を再現し、emitされる
cv-interface 準拠の CvMessage をJSONで表示する(契約: docs/contracts/cv-interface.md §4)。
"""

from __future__ import annotations

import sys

from app.cv.interface import BOX_IDS, CvBoardUpdate, CvMessage
from app.cv.mock import MockCv

HELP = """\
コマンド:
  grab <box>       箱を掴む(box: large-1 / L1 / m2 / small-3 など)
  place <A|B|C|W>  掴んでいる箱を塔A/B/C・待機エリア(W)に置く
  board <盤面>     論理盤面を一括セット(例: board LMS//L)。残りは待機エリアへ
  show             現在の状態を表示
  help             このヘルプ
  quit             終了
"""

_SHORT = {"L": "large", "M": "medium", "S": "small"}


def resolve_box_id(name: str) -> str:
    """L1 / m2 のような省略形も box_id に解決する。"""
    name = name.strip().lower()
    if name in BOX_IDS:
        return name
    if len(name) == 2 and name[0].upper() in _SHORT and name[1].isdigit():
        candidate = f"{_SHORT[name[0].upper()]}-{name[1]}"
        if candidate in BOX_IDS:
            return candidate
    raise ValueError(f"unknown box: {name!r}")


def print_messages(messages: list[CvMessage], *, frames: bool = False) -> None:
    for message in messages:
        if frames or isinstance(message, CvBoardUpdate):
            print(message.model_dump_json())


def show_state(mock: MockCv) -> None:
    board = mock.last_board
    if board is None:
        print("(盤面未確定)")
        return
    print(f"盤面: {board.board!r}  legal={board.legal}")
    for tower, stack in zip(("A", "B", "C"), board.towers, strict=True):
        print(f"  塔{tower}: {stack or '(空)'}")
    print(f"  待機: {', '.join(board.staging_box_ids) or '(なし)'}")
    if board.violations:
        print(f"  違反: {[f'{v.tower}:{v.type}' for v in board.violations]}")


def run(mock: MockCv, lines: list[str] | None = None, *, frames: bool = False) -> None:
    """CLIループ。lines を渡すと非対話実行(テスト用)。"""
    source = iter(lines) if lines is not None else None
    while True:
        if source is not None:
            line = next(source, None)
            if line is None:
                return
        else:
            try:
                line = input("mock> ")
            except EOFError:
                return
        cmd, _, arg = line.strip().partition(" ")
        arg = arg.strip()
        try:
            match cmd:
                case "":
                    continue
                case "quit" | "q" | "exit":
                    return
                case "help" | "?":
                    print(HELP)
                case "show":
                    show_state(mock)
                case "grab":
                    mock.grab(resolve_box_id(arg))
                    print_messages(mock.poll(), frames=frames)
                case "place":
                    mock.place(arg.upper())
                    print_messages(mock.poll(), frames=frames)
                case "board":
                    mock.set_board(arg)
                    print_messages(mock.poll(), frames=frames)
                case _:
                    print(f"不明なコマンド: {cmd!r}(help で一覧)")
        except ValueError as e:
            print(f"エラー: {e}")


def main() -> None:
    frames = "--frames" in sys.argv  # CvFrame(30fps相当のストリーム)も表示する
    print("モックCV(cv-interface.md 準拠)。help でコマンド一覧。")
    run(MockCv(), frames=frames)


if __name__ == "__main__":
    main()
