"""SQLite-backed per-card chat history."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = 2


@dataclass(frozen=True)
class Turn:
    role: str
    content: str
    created_at: int


@dataclass(frozen=True)
class Session:
    session_id: int
    started_at: int
    first_user_preview: str


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _migrate(con: sqlite3.Connection) -> None:
    cur = con.execute("PRAGMA user_version")
    version = cur.fetchone()[0]
    if version < 1:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS chats (
              card_id      INTEGER NOT NULL,
              turn_idx     INTEGER NOT NULL,
              role         TEXT NOT NULL CHECK (role IN ('system','user','assistant','tool')),
              content      TEXT NOT NULL,
              created_at   INTEGER NOT NULL,
              PRIMARY KEY (card_id, turn_idx)
            );
            CREATE INDEX IF NOT EXISTS idx_chats_card ON chats(card_id);
            PRAGMA user_version = 1;
            """
        )
        con.commit()
    if version < 2:
        # Multi-session: rebuild chats with PK (card_id, session_id, turn_idx).
        cols = [r[1] for r in con.execute("PRAGMA table_info(chats)").fetchall()]
        has_session = "session_id" in cols
        con.executescript(
            """
            CREATE TABLE chats_new (
              card_id      INTEGER NOT NULL,
              session_id   INTEGER NOT NULL DEFAULT 1,
              turn_idx     INTEGER NOT NULL,
              role         TEXT NOT NULL CHECK (role IN ('system','user','assistant','tool')),
              content      TEXT NOT NULL,
              created_at   INTEGER NOT NULL,
              PRIMARY KEY (card_id, session_id, turn_idx)
            );
            """
        )
        if has_session:
            con.execute(
                "INSERT INTO chats_new (card_id, session_id, turn_idx, role, content, created_at) "
                "SELECT card_id, session_id, turn_idx, role, content, created_at FROM chats"
            )
        else:
            con.execute(
                "INSERT INTO chats_new (card_id, session_id, turn_idx, role, content, created_at) "
                "SELECT card_id, 1, turn_idx, role, content, created_at FROM chats"
            )
        con.executescript(
            """
            DROP TABLE chats;
            ALTER TABLE chats_new RENAME TO chats;
            CREATE INDEX IF NOT EXISTS idx_chats_card_session
              ON chats(card_id, session_id);
            PRAGMA user_version = 2;
            """
        )
        con.commit()


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.con = _connect(self.db_path)
        _migrate(self.con)

    def latest_session_id(self, card_id: int) -> int:
        cur = self.con.execute(
            "SELECT COALESCE(MAX(session_id), 1) FROM chats WHERE card_id = ?",
            (card_id,),
        )
        return int(cur.fetchone()[0])

    def new_session_id(self, card_id: int) -> int:
        cur = self.con.execute(
            "SELECT COALESCE(MAX(session_id), 0) + 1 FROM chats WHERE card_id = ?",
            (card_id,),
        )
        return int(cur.fetchone()[0])

    def list_sessions(self, card_id: int) -> list[Session]:
        cur = self.con.execute(
            """
            SELECT session_id, MIN(created_at) AS started_at,
                   COALESCE(
                     (SELECT content FROM chats c2
                      WHERE c2.card_id = c1.card_id AND c2.session_id = c1.session_id
                            AND c2.role = 'user'
                      ORDER BY turn_idx ASC LIMIT 1),
                     ''
                   ) AS first_user
            FROM chats c1
            WHERE card_id = ?
            GROUP BY session_id
            ORDER BY session_id DESC
            """,
            (card_id,),
        )
        out: list[Session] = []
        for sid, started, first in cur.fetchall():
            preview = (first or "").strip().replace("\n", " ")[:100]
            out.append(Session(int(sid), int(started), preview))
        return out

    def history(self, card_id: int, session_id: int | None = None) -> list[Turn]:
        if session_id is None:
            session_id = self.latest_session_id(card_id)
        cur = self.con.execute(
            "SELECT role, content, created_at FROM chats "
            "WHERE card_id = ? AND session_id = ? ORDER BY turn_idx ASC",
            (card_id, session_id),
        )
        return [Turn(role=r, content=c, created_at=ts) for r, c, ts in cur.fetchall()]

    def append(self, card_id: int, role: str, content: str,
               session_id: int | None = None) -> int:
        if session_id is None:
            session_id = self.latest_session_id(card_id)
        now = int(time.time())
        cur = self.con.execute(
            "SELECT COALESCE(MAX(turn_idx), -1) + 1 FROM chats "
            "WHERE card_id = ? AND session_id = ?",
            (card_id, session_id),
        )
        next_idx = cur.fetchone()[0]
        self.con.execute(
            "INSERT INTO chats (card_id, turn_idx, role, content, created_at, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (card_id, next_idx, role, content, now, session_id),
        )
        self.con.commit()
        return next_idx

    def append_many(self, card_id: int, turns: Iterable[tuple[str, str]],
                    session_id: int | None = None) -> None:
        if session_id is None:
            session_id = self.latest_session_id(card_id)
        now = int(time.time())
        cur = self.con.execute(
            "SELECT COALESCE(MAX(turn_idx), -1) + 1 FROM chats "
            "WHERE card_id = ? AND session_id = ?",
            (card_id, session_id),
        )
        next_idx = cur.fetchone()[0]
        rows = [
            (card_id, next_idx + i, role, content, now, session_id)
            for i, (role, content) in enumerate(turns)
        ]
        self.con.executemany(
            "INSERT INTO chats (card_id, turn_idx, role, content, created_at, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        self.con.commit()

    def clear_session(self, card_id: int, session_id: int) -> None:
        self.con.execute(
            "DELETE FROM chats WHERE card_id = ? AND session_id = ?",
            (card_id, session_id),
        )
        self.con.commit()

    def clear(self, card_id: int) -> None:
        """Delete ALL sessions for a card."""
        self.con.execute("DELETE FROM chats WHERE card_id = ?", (card_id,))
        self.con.commit()

    def close(self) -> None:
        self.con.close()
