from __future__ import annotations

import sqlite3
from pathlib import Path


class SuppressionStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS sms_suppression (
                    phone TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def add(self, phone: str, source: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sms_suppression(phone, source) VALUES (?, ?)
                ON CONFLICT(phone) DO UPDATE SET source = excluded.source,
                    recorded_at = CURRENT_TIMESTAMP
                """,
                (phone, source),
            )

    def contains(self, phone: str) -> bool:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM sms_suppression WHERE phone = ?", (phone,)
            ).fetchone()
        return row is not None
