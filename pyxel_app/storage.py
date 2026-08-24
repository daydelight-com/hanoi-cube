"""自己ベストの永続化(仕様書 §3.5、要判断 #6)。Pyxel に依存しない。

ブラウザ(Pyodide)では `js` モジュール経由で `window.localStorage` に保存し、リロード後も残る。
ネイティブ実行ではホームディレクトリの JSON ファイルに保存する(開発時の確認用)。
どちらも使えない・壊れている場合は黙って揮発(ゲームは止めない)。
"""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any, Protocol

BEST_KEY = "hanoi_cube.best"
NATIVE_SAVE_PATH = Path.home() / ".hanoi_cube_pyxel.json"


class KeyValueStore(Protocol):
    """localStorage 相当の最小インターフェース。"""

    def get(self, key: str) -> str | None: ...

    def set(self, key: str, value: str) -> None: ...


class MemoryStore:
    """テスト・フォールバック用(揮発)。"""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value


class FileStore:
    """JSON ファイル 1 つに全キーを持つ(ネイティブ実行用)。I/O 失敗は握りつぶす。"""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _load(self) -> dict[str, str]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if isinstance(k, str) and isinstance(v, str)}

    def get(self, key: str) -> str | None:
        return self._load().get(key)

    def set(self, key: str, value: str) -> None:
        data = self._load()
        data[key] = value
        with contextlib.suppress(OSError):
            self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


class SafeStore:
    """例外を握りつぶす KeyValueStore ラッパー。

    ブラウザの localStorage はプライベートモード等で `getItem` / `setItem` が例外を投げうる
    (Pyodide では JsException)。自己ベストが読めない・書けないだけでゲームは止めない。
    """

    def __init__(self, inner: KeyValueStore) -> None:
        self._inner = inner

    def get(self, key: str) -> str | None:
        try:
            return self._inner.get(key)
        except Exception:  # JsException を含む何が来ても揮発に倒す
            return None

    def set(self, key: str, value: str) -> None:
        with contextlib.suppress(Exception):
            self._inner.set(key, value)


def _browser_store() -> KeyValueStore | None:
    """Pyodide 上なら window.localStorage を包んで返す(getItem は無ければ None を返す)。"""
    try:
        from js import window  # type: ignore[import-not-found]  # Pyodide のみ存在

        local_storage = getattr(window, "localStorage", None)
    except Exception:  # ImportError のほか、localStorage 無効時のアクセス例外も含む
        return None
    if local_storage is None:
        return None
    ls: Any = local_storage  # クロージャ越しに None 除去の絞り込みが効かないため付け直す

    class _LocalStorage:
        def get(self, key: str) -> str | None:
            value = ls.getItem(key)
            return str(value) if value is not None else None

        def set(self, key: str, value: str) -> None:
            ls.setItem(key, value)

    return SafeStore(_LocalStorage())


class BestStore:
    """自己ベスト(最高スコア)の読み書き。値が壊れていたら 0 扱い。"""

    def __init__(self, store: KeyValueStore) -> None:
        self._store = store
        self.best = self._read()

    def _read(self) -> int:
        raw = self._store.get(BEST_KEY)
        if raw is None:
            return 0
        try:
            value = int(raw)
        except ValueError:
            return 0
        return max(0, value)

    def update(self, score: int) -> bool:
        """スコアを反映し、自己ベストを更新したら True(同点は更新しない)。"""
        if score <= self.best:
            return False
        self.best = score
        self._store.set(BEST_KEY, str(score))
        return True


_default: BestStore | None = None


def best_store() -> BestStore:
    """アプリ共有のシングルトン(ブラウザ: localStorage / ネイティブ: ホームの JSON)。"""
    global _default
    if _default is None:
        _default = BestStore(_browser_store() or FileStore(NATIVE_SAVE_PATH))
    return _default
