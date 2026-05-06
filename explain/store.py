"""SQLite-backed per-card chat history."""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Turn:
    role: str
    content: str
    created_at: int


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


class Store:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.con = _connect(self.db_path)
        _migrate(self.con)

    def history(self, card_id: int) -> list[Turn]:
        cur = self.con.execute(
            "SELECT role, content, created_at FROM chats "
            "WHERE card_id = ? ORDER BY turn_idx ASC",
            (card_id,),
        )
        return [Turn(role=r, content=c, created_at=ts) for r, c, ts in cur.fetchall()]

    def append(self, card_id: int, role: str, content: str) -> int:
        now = int(time.time())
        cur = self.con.execute(
            "SELECT COALESCE(MAX(turn_idx), -1) + 1 FROM chats WHERE card_id = ?",
            (card_id,),
        )
        next_idx = cur.fetchone()[0]
        self.con.execute(
            "INSERT INTO chats (card_id, turn_idx, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (card_id, next_idx, role, content, now),
        )
        self.con.commit()
        return next_idx

    def append_many(self, card_id: int, turns: Iterable[tuple[str, str]]) -> None:
        now = int(time.time())
        cur = self.con.execute(
            "SELECT COALESCE(MAX(turn_idx), -1) + 1 FROM chats WHERE card_id = ?",
            (card_id,),
        )
        next_idx = cur.fetchone()[0]
        rows = [
            (card_id, next_idx + i, role, content, now)
            for i, (role, content) in enumerate(turns)
        ]
        self.con.executemany(
            "INSERT INTO chats (card_id, turn_idx, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self.con.commit()

    def clear(self, card_id: int) -> None:
        self.con.execute("DELETE FROM chats WHERE card_id = ?", (card_id,))
        self.con.commit()

    def close(self) -> None:
        self.con.close()
