"""Time-filtered transfer windows. Later events are excluded."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

MAX_WINDOW_EDGES = 2_000
_TIME = "%Y-%m-%dT%H:%M:%SZ"


@dataclass(frozen=True)
class Transfer:
    transaction_id: str
    from_account_id: str
    to_account_id: str
    amount_minor: int
    event_time: str


def parse_time(value: str) -> datetime:
    return datetime.strptime(value, _TIME).replace(tzinfo=None)


def format_time(value: datetime) -> str:
    return value.strftime(_TIME)


def shift_time(value: str, *, minutes: int) -> str:
    return format_time(parse_time(value) + timedelta(minutes=minutes))


def load_window(
    connection: sqlite3.Connection,
    *,
    as_of: str,
    lookback_minutes: int = 60,
    limit: int = MAX_WINDOW_EDGES,
) -> tuple[list[Transfer], bool]:
    """Return transfers in (as_of - lookback, as_of], newest-capped."""
    start = shift_time(as_of, minutes=-lookback_minutes)
    rows = connection.execute(
        """
        SELECT transaction_id, from_account_id, to_account_id, amount_minor, event_time
        FROM transactions
        WHERE event_time <= ? AND event_time > ?
        ORDER BY event_time DESC, transaction_id DESC
        LIMIT ?
        """,
        (as_of, start, limit + 1),
    ).fetchall()
    truncated = len(rows) > limit
    kept = list(reversed(rows[:limit]))
    transfers = [
        Transfer(
            transaction_id=row["transaction_id"],
            from_account_id=row["from_account_id"],
            to_account_id=row["to_account_id"],
            amount_minor=int(row["amount_minor"]),
            event_time=row["event_time"],
        )
        for row in kept
    ]
    return transfers, truncated


def slice_since(transfers: list[Transfer], as_of: str, *, minutes: int) -> list[Transfer]:
    start = shift_time(as_of, minutes=-minutes)
    return [item for item in transfers if start < item.event_time <= as_of]
