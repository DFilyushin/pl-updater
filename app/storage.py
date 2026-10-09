"""SQLite-хранилище: список запросов и найденные темы со статусом «прочитано»."""
import re
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .config import base_dir

SCHEMA = """
CREATE TABLE IF NOT EXISTS queries (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT NOT NULL UNIQUE,
    enabled    INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS topics (
    topic_id      INTEGER PRIMARY KEY,
    query_id      INTEGER,
    title         TEXT,
    forum         TEXT,
    size          TEXT,
    seeders       INTEGER,
    added_at      TEXT,
    added_ts      INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT,
    read          INTEGER NOT NULL DEFAULT 0
);
"""


class Storage:
    """Обёртка над sqlite3. Соединение общее для GUI и фоновых потоков,
    поэтому каждое обращение идёт под self._lock."""

    def __init__(self, path: Path | None = None):
        self.path = path or (base_dir() / "data.sqlite3")
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()
            self._migrate()

    def _migrate(self) -> None:
        """Добавляет added_ts в старые базы и чинит записи, испорченные
        скрытыми <u>-тегами раннего парсера (unix-время в added_at,
        задвоенные сиды вида «3636»)."""
        cols = [r[1] for r in self._conn.execute("PRAGMA table_info(topics)").fetchall()]
        if "added_ts" in cols:
            return
        self._conn.execute(
            "ALTER TABLE topics ADD COLUMN added_ts INTEGER NOT NULL DEFAULT 0")
        for row in self._conn.execute(
                "SELECT topic_id, added_at, seeders FROM topics").fetchall():
            added_at = row["added_at"] or ""
            added_ts = 0
            m = re.match(r"(\d{9,10})\b", added_at)
            if m:
                added_ts = int(m.group(1))
                added_at = datetime.fromtimestamp(added_ts).strftime("%Y-%m-%d %H:%M")
            s = str(row["seeders"] or 0)
            seeders = row["seeders"]
            if len(s) >= 2 and len(s) % 2 == 0 and s[: len(s) // 2] == s[len(s) // 2:]:
                seeders = int(s[: len(s) // 2])
            self._conn.execute(
                "UPDATE topics SET added_ts = ?, added_at = ?, seeders = ?"
                " WHERE topic_id = ?",
                (added_ts, added_at, seeders, row["topic_id"]),
            )
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- запросы ---

    def add_query(self, text: str) -> int:
        """Добавляет запрос (дубликат не создаётся) и возвращает его id."""
        text = text.strip()
        if not text:
            raise ValueError("Пустой запрос")
        with self._lock:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO queries(text, enabled, created_at) VALUES (?, 1, ?)",
                (text, datetime.now().isoformat(timespec="seconds")),
            )
            self._conn.commit()
            if cur.lastrowid:
                return cur.lastrowid
            row = self._conn.execute(
                "SELECT id FROM queries WHERE text = ?", (text,)
            ).fetchone()
            return row["id"]

    def update_query(self, query_id: int, text: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE queries SET text = ? WHERE id = ?", (text.strip(), query_id)
            )
            self._conn.commit()

    def set_query_enabled(self, query_id: int, enabled: bool) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE queries SET enabled = ? WHERE id = ?",
                (1 if enabled else 0, query_id),
            )
            self._conn.commit()

    def delete_query(self, query_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM queries WHERE id = ?", (query_id,))
            self._conn.commit()

    def list_queries(self, enabled_only: bool = False) -> list[sqlite3.Row]:
        """Запросы в порядке добавления; enabled_only — только включённые."""
        sql = "SELECT * FROM queries"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY id"
        with self._lock:
            return self._conn.execute(sql).fetchall()

    # --- темы ---

    def add_topics(self, query_id: int, topics: list[dict]) -> int:
        """Сохраняет темы; уже виденные topic_id игнорируются. Возвращает число новых."""
        new_count = 0
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            for t in topics:
                cur = self._conn.execute(
                    "INSERT OR IGNORE INTO topics"
                    "(topic_id, query_id, title, forum, size, seeders,"
                    " added_at, added_ts, first_seen_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        t["topic_id"], query_id, t.get("title", ""),
                        t.get("forum", ""), t.get("size", ""),
                        t.get("seeders", 0), t.get("added_at", ""),
                        t.get("added_ts", 0), now,
                    ),
                )
                new_count += cur.rowcount
            self._conn.commit()
        return new_count

    def unread_topics(self) -> list[sqlite3.Row]:
        """Непрочитанные темы для главной таблицы: по запросу, внутри — новые сверху."""
        with self._lock:
            return self._conn.execute(
                "SELECT t.*, q.text AS query_text FROM topics t"
                " LEFT JOIN queries q ON q.id = t.query_id"
                " WHERE t.read = 0"
                " ORDER BY t.query_id, t.added_ts DESC, t.topic_id DESC"
            ).fetchall()

    def mark_read(self, topic_ids: list[int]) -> None:
        """Отмечает темы прочитанными: они навсегда пропадают из списка."""
        if not topic_ids:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE topics SET read = 1 WHERE topic_id = ?",
                [(tid,) for tid in topic_ids],
            )
            self._conn.commit()
