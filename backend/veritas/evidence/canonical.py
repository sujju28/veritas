"""RFC 8785 canonical JSON, with NFC applied to every string first.

Object key order does not affect the bytes. Non-finite numbers are rejected.
"""

from __future__ import annotations

import unicodedata
from typing import Any

import rfc8785
from rfc8785 import CanonicalizationError, FloatDomainError, IntegerDomainError


class CanonicalError(ValueError):
    """The value cannot be serialized as canonical JSON."""


def canonical_bytes(value: Any) -> bytes:
    try:
        return rfc8785.dumps(_normalize(value))
    except (CanonicalizationError, FloatDomainError, IntegerDomainError) as exc:
        raise CanonicalError(str(exc)) from exc


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, dict):
        return {_normalize(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value
