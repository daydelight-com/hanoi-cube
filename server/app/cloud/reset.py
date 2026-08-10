"""本番開始前のプレイデータ一括リセット(scripts/reset_plays.py の本体)。

開発・検証も本番と同じ SQLite ファイル・同じ Firestore `plays` コレクションに
書く運用のため、本番開始直前に一度だけ両ストアをセットで初期化する。
片側だけの削除は禁止: SQLite だけ残ると開発プレイがランキングに出続け、
その QR は永遠に「準備中」になる(docs/operations.md)。

削除順は SQLite → Firestore。途中失敗で残るのは「SQLite だけ消えた」状態で、
ローカルランキングには影響しない(逆順だと Firestore 側の失敗でこの悪い状態に
陥る)。どちらで失敗しても再実行すれば完了する。

実行はサーバー停止中に行うこと。起動中の DB ファイルを消しても、開いている
プロセスは古いデータを持ち続ける。スキーマは次回起動時に自動作成される。
アップロードキューも SQLite 内にあるため、ファイル削除で一緒に消える
(開発プレイが後から本番 Firestore へ送られる事故は起きない)。
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.cloud.uploader import make_firestore_client, resolve_credentials_path


class CloudPlays(Protocol):
    """Firestore `plays` コレクションへの管理操作。失敗は例外で伝える。"""

    def count(self) -> int: ...

    def delete_all(self) -> int: ...


class FirestorePlays:
    """Admin SDK 経由の実装(接続構成はアップローダと同じ環境変数)。

    クライアントからの削除はルールで禁止されているため(firestore.md §3)、
    削除はこの Admin SDK 経路でのみ可能。
    """

    def __init__(self) -> None:
        self._db = make_firestore_client()

    def count(self) -> int:
        return sum(1 for _ in self._db.collection("plays").list_documents())

    def delete_all(self) -> int:
        deleted = 0
        for doc in self._db.collection("plays").list_documents():
            doc.delete()
            deleted += 1
        return deleted


def cloud_target_description() -> str | None:
    """削除先の説明(誤対象への実行防止のため確認表示に使う)。未構成なら None。"""
    project = os.environ.get("HANOI_FIREBASE_PROJECT")
    if emulator := os.environ.get("FIRESTORE_EMULATOR_HOST"):
        return f"Firestoreエミュレータ {emulator} (project={project or '未指定'})"
    if cred := resolve_credentials_path():
        return f"Firestore本番 (credentials={cred})"
    return None


def local_play_count(db_path: Path) -> int:
    """SQLite の plays 件数。ファイルやテーブルが無ければ 0。

    「テーブルなし」以外の失敗(ロック=サーバー起動中の疑い、破損)は例外のまま
    伝える。0 件と誤表示したまま削除に進まないため。
    """
    if not db_path.exists():
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("SELECT COUNT(*) FROM plays").fetchone()
        return int(row[0])
    except sqlite3.OperationalError as exc:
        if "no such table" in str(exc):  # スキーマ未作成の空ファイル
            return 0
        raise
    finally:
        conn.close()


def delete_local(db_path: Path) -> None:
    """DBファイルを WAL/SHM の副ファイルごと削除する(無ければ何もしない)。"""
    for path in (
        db_path,
        db_path.with_name(db_path.name + "-wal"),
        db_path.with_name(db_path.name + "-shm"),
    ):
        path.unlink(missing_ok=True)


@dataclass
class ResetResult:
    local_deleted: int
    cloud_deleted: int


def reset_plays(db_path: Path, cloud: CloudPlays) -> ResetResult:
    """SQLite と Firestore のプレイデータをセットで消す(順序はモジュール docstring)。"""
    local = local_play_count(db_path)
    delete_local(db_path)
    cloud_deleted = cloud.delete_all()
    return ResetResult(local_deleted=local, cloud_deleted=cloud_deleted)


def default_db_path() -> Path:
    """既定のDBパス。HANOI_DB_PATH があれば尊重(サーバーと同じ cwd で実行すること)。"""
    if env := os.environ.get("HANOI_DB_PATH"):
        return Path(env)
    # リポジトリ内の server/output/plays.sqlite3(このファイルは server/app/cloud/ 配下)
    return Path(__file__).resolve().parents[2] / "output" / "plays.sqlite3"


def run_cli(
    argv: list[str] | None = None,
    *,
    cloud_factory: Callable[[], CloudPlays] = FirestorePlays,
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
) -> int:
    """確認プロンプト付き CLI(scripts/reset_plays.py から呼ばれる)。返り値は終了コード。"""
    parser = argparse.ArgumentParser(
        prog="reset_plays",
        description="プレイデータの初期化(ローカルSQLite削除+Firestore plays 全削除)",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=default_db_path(),
        help="SQLite DBのパス(既定: HANOI_DB_PATH または server/output/plays.sqlite3)",
    )
    args = parser.parse_args(argv)
    db_path: Path = args.db

    target = cloud_target_description()
    if target is None:
        print_fn(
            "エラー: Firestore の接続設定がありません。片側(SQLiteのみ)の削除は行いません。\n"
            "  本番:       リポジトリ直下に service-account.json を置く"
            "(または HANOI_FIREBASE_CREDENTIALS=<鍵のパス>)\n"
            "  エミュレータ: FIRESTORE_EMULATOR_HOST=127.0.0.1:8080"
            " HANOI_FIREBASE_PROJECT=demo-hanoi"
        )
        return 2

    try:
        cloud = cloud_factory()
        local = local_play_count(db_path)
        remote = cloud.count()
    except Exception as exc:
        print_fn(
            f"エラー: 削除対象の確認に失敗しました: {exc}\n"
            "  何も削除していません。Firestore の接続設定と、サーバーが停止していること\n"
            "  (DBロックの原因)を確認して再実行してください。"
        )
        return 2
    print_fn("削除対象:")
    print_fn(f"  ローカルSQLite: {db_path} — {local} プレイ(ファイルごと削除)")
    print_fn(f"  {target} — plays {remote} ドキュメント")
    # 確認プロンプトは省略不可(自動実行は `printf 'yes\n' |` で標準入力から渡す)
    answer = input_fn('本当に削除しますか? 削除するには "yes" と入力: ')
    if answer.strip() != "yes":
        print_fn("中止しました(何も削除していません)")
        return 1

    try:
        result = reset_plays(db_path, cloud)
    except Exception as exc:
        print_fn(
            f"エラー: 削除が途中で失敗しました: {exc}\n"
            "  SQLite は削除済みの可能性があります(ローカルランキングへの実害はありません)。\n"
            "  原因を解消して再実行すれば残りの Firestore ドキュメントが削除されます。"
        )
        return 3
    print_fn(
        f"完了: SQLite {result.local_deleted} プレイ / "
        f"Firestore {result.cloud_deleted} ドキュメントを削除しました"
    )
    print_fn("サーバーを起動してください(スキーマは起動時に自動作成されます)")
    return 0
