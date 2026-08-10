"""クラウドアップロードのリトライキュー(仕様§3.2-1・§8.2、契約: firestore.md §1)。

プレイ結果はまず SQLite に保存され(uploaded=0)、本モジュールが非同期に
Firestore へ `set()` する(冪等。リトライで重複しない)。アップロードの失敗は
ゲーム進行に一切影響させない: 失敗したら間隔を伸ばして再試行を続けるだけで、
キューは SQLite 上にあるためプロセス再起動でも失われない。
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Protocol

from app.state.sqlite_store import SqliteStore
from app.state.store import PlayRecord

logger = logging.getLogger(__name__)

UPLOAD_INTERVAL_S = 3.0  # 通常時のキュー確認間隔
UPLOAD_MAX_BACKOFF_S = 60.0  # オフライン時の再試行間隔の上限


def play_document(record: PlayRecord) -> dict[str, Any]:
    """plays/{play_id} ドキュメントの形(firestore.md §1)。"""
    return {
        "player_name": record.name,
        "score": record.score,
        "fail_count": record.fail_count,
        "played_at": record.played_at,
        "judgements": [
            {
                "seq": j.seq,
                "board": j.board,
                "elapsed_ms": j.elapsed_ms,
                "result": j.result,
                "points": j.points,
                "min_moves": j.min_moves,
                "dup_of_seq": j.dup_of_seq,
                # Firestore は配列の直接入れ子を保存できないため a/b/c のマップにする
                # (firestore.md §1)
                "tower_box_ids": {
                    "a": list(j.tower_box_ids[0]),
                    "b": list(j.tower_box_ids[1]),
                    "c": list(j.tower_box_ids[2]),
                },
            }
            for j in record.judgements
        ],
    }


class UploadSink(Protocol):
    """1プレイ分のアップロード先。失敗は例外で伝える(呼び出し側が再試行)。"""

    def upload(self, record: PlayRecord) -> None: ...


def default_credentials_path() -> Path:
    """リポジトリ直下の service-account.json(既定の配置。ブースMacもこの形で運用)。"""
    # このファイルは server/app/cloud/ 配下 → parents[3] がリポジトリルート
    return Path(__file__).resolve().parents[3] / "service-account.json"


def resolve_credentials_path() -> str | None:
    """アップロード先の認証ファイルを決める。明示指定 > リポジトリ既定配置 > なし。

    汎用ADC(GOOGLE_APPLICATION_CREDENTIALS)は意図的に見ない: 開発者のシェルに
    他案件の認証が残っていると、無関係なプロジェクトの Firestore へプレイ記録を
    書き込む事故になるため(実際に発生。handoff S17)。
    """
    if explicit := os.environ.get("HANOI_FIREBASE_CREDENTIALS"):
        return explicit
    default = default_credentials_path()
    if default.exists():
        return str(default)
    return None


def make_firestore_client() -> Any:
    """環境変数から Firestore クライアントを構成する(アップローダとリセットで共用)。

    認証はサービスアカウント(resolve_credentials_path のJSONパス)。
    FIRESTORE_EMULATOR_HOST 設定時は Admin SDK がエミュレータへ接続する
    (この場合は認証不要。HANOI_FIREBASE_PROJECT でプロジェクトIDを指定)。
    """
    import firebase_admin
    from firebase_admin import credentials, firestore

    cred_path = resolve_credentials_path()
    cred = credentials.Certificate(cred_path) if cred_path else None
    options: dict[str, Any] = {}
    if project := os.environ.get("HANOI_FIREBASE_PROJECT"):
        options["projectId"] = project
    app = firebase_admin.initialize_app(cred, options or None)
    return firestore.client(app)


class FirestoreSink:
    """Firebase Admin SDK による plays/{play_id} への set()(仕様§8.2)。"""

    def __init__(self) -> None:
        self._db = make_firestore_client()

    def upload(self, record: PlayRecord) -> None:
        self._db.collection("plays").document(record.play_id).set(play_document(record))


def make_sink() -> UploadSink | None:
    """環境変数からアップロード先を構成する。未設定・構成失敗ならクラウド連携なし(None)。

    クラウド側の問題でゲームを止めない(仕様§3.2-1)ため、認証ファイル破損等で
    構成に失敗してもローカルのみで起動を続ける(キューはSQLiteに残る)。
    """
    configured = resolve_credentials_path() or os.environ.get("FIRESTORE_EMULATOR_HOST")
    if not configured:
        logger.info(
            "クラウドアップロード無効(リポジトリ直下に service-account.json が無く、"
            "HANOI_FIREBASE_CREDENTIALS も未設定)"
        )
        return None
    try:
        return FirestoreSink()
    except Exception:
        logger.exception("Firestore初期化に失敗。アップロード無効のまま起動を続けます")
        return None


class Uploader:
    """SQLite の未アップロード分を順に送る常駐タスク。"""

    def __init__(
        self,
        store: SqliteStore,
        sink: UploadSink,
        *,
        interval_s: float = UPLOAD_INTERVAL_S,
        max_backoff_s: float = UPLOAD_MAX_BACKOFF_S,
    ) -> None:
        self._store = store
        self._sink = sink
        self._interval_s = interval_s
        self._max_backoff_s = max_backoff_s

    def process_once(self) -> tuple[int, int]:
        """キューを1周分処理する。返り値は (アップロード成功数, 残件数)。

        失敗したらその周は打ち切る(古い順を保ったまま次周期に再試行)。
        """
        pending = self._store.pending_uploads()
        uploaded = 0
        for record in pending:
            try:
                self._sink.upload(record)
            except Exception as exc:  # 失敗理由によらずゲームは止めない(仕様§3.2-1)
                logger.warning("アップロード失敗(再試行します) play_id=%s: %s", record.play_id, exc)
                break
            self._store.mark_uploaded(record.play_id)
            logger.info("アップロード完了 play_id=%s", record.play_id)
            uploaded += 1
        return uploaded, len(pending) - uploaded

    async def run(self) -> None:
        """常駐ループ。失敗が続く間は間隔を指数的に伸ばす(上限あり)。"""
        delay = self._interval_s
        while True:
            _, remaining = await asyncio.to_thread(self.process_once)
            delay = min(delay * 2, self._max_backoff_s) if remaining else self._interval_s
            await asyncio.sleep(delay)
