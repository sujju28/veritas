"""Named dataset sizes. Counts above the benchmark cap are rejected."""

from __future__ import annotations

SCALES: dict[str, tuple[int, int]] = {
    "tiny": (100, 500),
    "default": (300, 2_000),
    "benchmark": (1_000, 10_000),
}

MAX_ACCOUNTS = 1_000
MAX_TRANSACTIONS = 10_000


class ScaleError(ValueError):
    pass


class BenchmarkConfirmationRequired(ScaleError):
    pass


def resolve_scale(scale: str, *, confirm_benchmark: bool) -> tuple[int, int]:
    if scale not in SCALES:
        raise ScaleError("scale must be tiny, default, or benchmark")
    accounts, transactions = SCALES[scale]
    if accounts > MAX_ACCOUNTS or transactions > MAX_TRANSACTIONS:
        raise ScaleError("scale exceeds the local cap")
    if scale == "benchmark" and not confirm_benchmark:
        raise BenchmarkConfirmationRequired("benchmark generation requires confirmation")
    return accounts, transactions
