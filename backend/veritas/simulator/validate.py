"""Validate synthetic transfer fields before they are written."""

from __future__ import annotations

import re
from datetime import datetime

_ACCOUNT_ID = re.compile(r"^acct-[0-9]{4}$")
_EVENT_TIME = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$")


class PayloadError(ValueError):
    pass


def validate_account_id(value: object) -> str:
    if not isinstance(value, str) or _ACCOUNT_ID.fullmatch(value) is None:
        raise PayloadError("account_id must be an opaque synthetic id")
    return value


def validate_amount_minor(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PayloadError("amount_minor must be a positive integer")
    if value <= 0:
        raise PayloadError("amount_minor must be a positive integer")
    return value


def validate_event_time(value: object) -> str:
    if not isinstance(value, str) or _EVENT_TIME.fullmatch(value) is None:
        raise PayloadError("event_time must be a UTC timestamp ending in Z")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise PayloadError("event_time must be a UTC timestamp ending in Z") from exc
    return value
