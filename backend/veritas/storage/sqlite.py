"""Local SQLite probe. The standard-library sqlite3 module is the storage driver."""

from __future__ import annotations

from pathlib import Path

from veritas.storage.db import connect


def check_sqlite(db_path: Path) -> None:
    """Open the database and confirm a trivial read.

    Raises OSError or sqlite3.Error when the file cannot be used. Callers
    must not surface the exception text, which can contain local paths.
    """
    with connect(db_path) as connection:
        connection.execute("SELECT 1")
