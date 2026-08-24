"""storage(自己ベストの永続化)のテスト。Pyxel 非依存。"""

from __future__ import annotations

from pathlib import Path

from storage import BEST_KEY, BestStore, FileStore, MemoryStore, SafeStore

# ---- KeyValueStore 実装 ----


def test_memory_store_roundtrip() -> None:
    store = MemoryStore()
    assert store.get("k") is None
    store.set("k", "v")
    assert store.get("k") == "v"


def test_file_store_roundtrip_and_persistence(tmp_path: Path) -> None:
    path = tmp_path / "save.json"
    store = FileStore(path)
    assert store.get(BEST_KEY) is None  # ファイル未作成
    store.set(BEST_KEY, "42")
    store.set("other", "x")
    reopened = FileStore(path)  # 別インスタンス = プロセス再起動相当
    assert reopened.get(BEST_KEY) == "42"
    assert reopened.get("other") == "x"


def test_file_store_survives_corrupted_file(tmp_path: Path) -> None:
    path = tmp_path / "save.json"
    path.write_text("{broken json", encoding="utf-8")
    store = FileStore(path)
    assert store.get(BEST_KEY) is None
    store.set(BEST_KEY, "10")  # 壊れたファイルは作り直す
    assert FileStore(path).get(BEST_KEY) == "10"


def test_file_store_ignores_non_dict_json(tmp_path: Path) -> None:
    path = tmp_path / "save.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert FileStore(path).get(BEST_KEY) is None


class _RaisingStore:
    """localStorage がプライベートモード等で例外を投げる状況の代役。"""

    def get(self, key: str) -> str | None:
        raise RuntimeError("storage disabled")

    def set(self, key: str, value: str) -> None:
        raise RuntimeError("storage disabled")


def test_safe_store_swallows_backend_exceptions() -> None:
    store = SafeStore(_RaisingStore())
    assert store.get(BEST_KEY) is None
    store.set(BEST_KEY, "10")  # 例外にならない
    # BestStore に包んでもゲームを止めない(揮発するだけ)
    best = BestStore(store)
    assert best.best == 0
    assert best.update(10) is True
    assert best.best == 10


def test_safe_store_passes_through_when_backend_works() -> None:
    backend = MemoryStore()
    store = SafeStore(backend)
    store.set(BEST_KEY, "7")
    assert store.get(BEST_KEY) == "7"
    assert backend.get(BEST_KEY) == "7"


# ---- BestStore ----


def test_best_defaults_to_zero() -> None:
    assert BestStore(MemoryStore()).best == 0


def test_update_keeps_maximum_and_reports_new_record() -> None:
    store = BestStore(MemoryStore())
    assert store.update(10) is True
    assert store.best == 10
    assert store.update(5) is False  # 下回っても残る
    assert store.best == 10
    assert store.update(10) is False  # 同点は更新しない
    assert store.update(11) is True
    assert store.best == 11


def test_update_zero_score_is_not_a_record() -> None:
    store = BestStore(MemoryStore())
    assert store.update(0) is False
    assert store.best == 0


def test_best_persists_across_instances() -> None:
    backend = MemoryStore()
    BestStore(backend).update(30)
    assert BestStore(backend).best == 30  # リロード相当


def test_corrupted_or_negative_value_reads_as_zero() -> None:
    backend = MemoryStore()
    backend.set(BEST_KEY, "not-a-number")
    assert BestStore(backend).best == 0
    backend.set(BEST_KEY, "-5")
    assert BestStore(backend).best == 0
