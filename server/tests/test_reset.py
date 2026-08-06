"""プレイデータリセットのテスト(app/cloud/reset.py)。

DoD: SQLite と Firestore を必ずセットで消すこと(片側だけの削除にならないこと)。
- Firestore 未構成 → 何も消さずにエラー終了
- ローカル削除に失敗 → Firestore に手を付けない(削除順 SQLite → Firestore)
- Firestore 削除に失敗 → 非0終了し、再実行で完了する
"""

from __future__ import annotations

from pathlib import Path

import pytest
from app.cloud.reset import (
    CloudPlays,
    delete_local,
    local_play_count,
    reset_plays,
    run_cli,
)
from app.state.sqlite_store import SqliteStore

from tests.test_sqlite_store import make_play


class FakeCloud:
    """Firestore plays の代役。fail_delete で削除途中の失敗を再現する。"""

    def __init__(self, docs: int = 0, *, fail_delete: bool = False) -> None:
        self.docs = docs
        self.fail_delete = fail_delete

    def count(self) -> int:
        return self.docs

    def delete_all(self) -> int:
        if self.fail_delete:
            # 1件も消せずに失敗するケース(オフライン等)
            raise ConnectionError("offline")
        deleted = self.docs
        self.docs = 0
        return deleted


def make_db(tmp_path: Path, plays: int = 2) -> Path:
    """WAL副ファイル込みの実DBファイルを作る。"""
    db_path = tmp_path / "plays.sqlite3"
    store = SqliteStore(db_path)
    for i in range(plays):
        store.save_play(make_play(f"play-{i}"))
    # close() で WAL がチェックポイントされるため、副ファイル削除の検証用に close 前に確認
    assert db_path.with_name("plays.sqlite3-wal").exists()
    store.close()
    return db_path


def test_local_play_count(tmp_path: Path) -> None:
    assert local_play_count(tmp_path / "missing.sqlite3") == 0
    empty = tmp_path / "empty.sqlite3"
    empty.write_bytes(b"")  # スキーマ未作成の空ファイル
    assert local_play_count(empty) == 0
    assert local_play_count(make_db(tmp_path, plays=3)) == 3


def test_reset_deletes_both_stores(tmp_path: Path) -> None:
    db_path = make_db(tmp_path, plays=2)
    # 副ファイルが残っているケースも消えることを確認するため作っておく
    db_path.with_name("plays.sqlite3-wal").write_bytes(b"")
    db_path.with_name("plays.sqlite3-shm").write_bytes(b"")
    cloud = FakeCloud(docs=2)
    result = reset_plays(db_path, cloud)
    assert (result.local_deleted, result.cloud_deleted) == (2, 2)
    assert not db_path.exists()
    assert not db_path.with_name("plays.sqlite3-wal").exists()
    assert not db_path.with_name("plays.sqlite3-shm").exists()
    assert cloud.count() == 0


def test_local_failure_leaves_cloud_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 削除順は SQLite → Firestore。ローカルで失敗したら Firestore は無傷のまま
    db_path = make_db(tmp_path)

    def boom(self: Path, missing_ok: bool = False) -> None:
        raise OSError("busy")

    monkeypatch.setattr(Path, "unlink", boom)
    cloud = FakeCloud(docs=2)
    with pytest.raises(OSError):
        reset_plays(db_path, cloud)
    assert cloud.count() == 2  # 片側(クラウドのみ)削除になっていない


def test_cloud_failure_then_rerun_completes(tmp_path: Path) -> None:
    # Firestore 側の失敗は「SQLiteだけ消えた」状態で止まり、再実行で完了する
    db_path = make_db(tmp_path)
    cloud = FakeCloud(docs=2, fail_delete=True)
    with pytest.raises(ConnectionError):
        reset_plays(db_path, cloud)
    assert not db_path.exists()
    assert cloud.count() == 2
    cloud.fail_delete = False
    result = reset_plays(db_path, cloud)  # 再実行(SQLiteは既に無い)
    assert (result.local_deleted, result.cloud_deleted) == (0, 2)
    assert cloud.count() == 0


def test_delete_local_is_idempotent(tmp_path: Path) -> None:
    delete_local(tmp_path / "missing.sqlite3")  # 例外にならない


def test_cli_refuses_without_cloud_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Firestore 未構成なら SQLite にも手を付けない(セット削除の担保)
    for var in (
        "HANOI_FIREBASE_CREDENTIALS",
        "GOOGLE_APPLICATION_CREDENTIALS",
        "FIRESTORE_EMULATOR_HOST",
        "HANOI_FIREBASE_PROJECT",
    ):
        monkeypatch.delenv(var, raising=False)
    db_path = make_db(tmp_path)
    code = run_cli(["--db", str(db_path)])
    assert code == 2
    assert db_path.exists()
    assert local_play_count(db_path) == 2


def cli_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
    monkeypatch.setenv("HANOI_FIREBASE_PROJECT", "demo-hanoi")


def test_cli_aborts_unless_yes_typed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cli_env(monkeypatch)
    db_path = make_db(tmp_path)
    cloud = FakeCloud(docs=1)
    lines: list[str] = []
    code = run_cli(
        ["--db", str(db_path)],
        cloud_factory=lambda: cloud,
        input_fn=lambda _prompt: "no",
        print_fn=lines.append,
    )
    assert code == 1
    assert db_path.exists()
    assert cloud.count() == 1
    assert any("中止" in line for line in lines)


def test_cli_shows_counts_and_deletes_on_yes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli_env(monkeypatch)
    db_path = make_db(tmp_path, plays=3)
    cloud = FakeCloud(docs=2)
    lines: list[str] = []
    code = run_cli(
        ["--db", str(db_path)],
        cloud_factory=lambda: cloud,
        input_fn=lambda _prompt: "yes",
        print_fn=lines.append,
    )
    assert code == 0
    assert not db_path.exists()
    assert cloud.count() == 0
    joined = "\n".join(lines)
    assert "3 プレイ" in joined  # 削除対象件数の表示(SQLite)
    assert "2 ドキュメント" in joined  # 削除対象件数の表示(Firestore)
    assert "エミュレータ" in joined  # 削除先の明示


def test_cli_cloud_failure_reports_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cli_env(monkeypatch)
    db_path = make_db(tmp_path)
    cloud = FakeCloud(docs=2, fail_delete=True)
    lines: list[str] = []
    code = run_cli(
        ["--db", str(db_path)],
        cloud_factory=lambda: cloud,
        input_fn=lambda _prompt: "yes",
        print_fn=lines.append,
    )
    assert code == 3
    assert any("再実行" in line for line in lines)


def test_cli_aborts_before_prompt_when_db_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # 破損ファイル(=ロック等の異常の代表)は 0 件と誤表示せず、何も消さずに中止する
    cli_env(monkeypatch)
    db_path = tmp_path / "plays.sqlite3"
    db_path.write_bytes(b"this is not a sqlite database file......")
    cloud = FakeCloud(docs=2)
    lines: list[str] = []
    code = run_cli(
        ["--db", str(db_path)],
        cloud_factory=lambda: cloud,
        input_fn=lambda _prompt: "yes",
        print_fn=lines.append,
    )
    assert code == 2
    assert db_path.exists()
    assert cloud.count() == 2
    assert any("何も削除していません" in line for line in lines)


def _protocol_check(cloud: CloudPlays) -> CloudPlays:
    return cloud


def test_fake_satisfies_protocol() -> None:
    _protocol_check(FakeCloud())
