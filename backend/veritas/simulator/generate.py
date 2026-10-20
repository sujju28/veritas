"""Deterministic synthetic banks, accounts, and transfers for seed 42."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from veritas.simulator.scales import resolve_scale
from veritas.simulator.validate import (
    validate_account_id,
    validate_amount_minor,
    validate_event_time,
)

_BASE = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
_BANKS = (
    ("BANK_A", "Logical Bank A"),
    ("BANK_B", "Logical Bank B"),
    ("BANK_C", "Logical Bank C"),
)
_PATTERN_ACCOUNTS = 14
_FAN_TRANSACTIONS = 8
_PASS_TRANSACTIONS = 4
_PATTERN_TRANSACTIONS = _FAN_TRANSACTIONS + _PASS_TRANSACTIONS


@dataclass(frozen=True)
class Dataset:
    seed: int
    scale: str
    banks: tuple[dict[str, str], ...]
    accounts: tuple[dict[str, str], ...]
    transactions: tuple[dict[str, Any], ...]
    ground_truth: tuple[dict[str, str | None], ...]

    def normalized(self) -> dict[str, Any]:
        return canonical_document(
            {
                "accounts": list(self.accounts),
                "banks": list(self.banks),
                "ground_truth": list(self.ground_truth),
                "transactions": list(self.transactions),
            }
        )

    def content_sha256(self) -> str:
        return document_sha256(self.normalized())


def build_dataset(seed: int, scale: str, *, confirm_benchmark: bool = False) -> Dataset:
    account_count, transaction_count = resolve_scale(scale, confirm_benchmark=confirm_benchmark)
    if account_count <= _PATTERN_ACCOUNTS:
        raise ValueError("scale does not leave room for planted patterns and legitimate transfers")
    if transaction_count <= _PATTERN_TRANSACTIONS:
        raise ValueError("scale does not leave room for legitimate transfers")

    banks = tuple({"bank_id": bank_id, "display_name": name} for bank_id, name in _BANKS)
    accounts = _accounts(account_count)
    transactions, ground_truth = _transfers(seed, account_count, transaction_count, accounts)
    for account in accounts:
        validate_account_id(account["account_id"])
        validate_event_time(account["opened_at"])
    for transaction in transactions:
        validate_account_id(transaction["from_account_id"])
        validate_account_id(transaction["to_account_id"])
        validate_amount_minor(transaction["amount_minor"])
        validate_event_time(transaction["event_time"])
    return Dataset(
        seed=seed,
        scale=scale,
        banks=banks,
        accounts=accounts,
        transactions=transactions,
        ground_truth=ground_truth,
    )


def _accounts(account_count: int) -> tuple[dict[str, str], ...]:
    special_banks = (
        ["BANK_B"]
        + ["BANK_A"] * 4
        + ["BANK_C"] * 4
        + ["BANK_A", "BANK_B", "BANK_C", "BANK_A", "BANK_B"]
    )
    rows: list[dict[str, str]] = []
    for index in range(account_count):
        if index < _PATTERN_ACCOUNTS:
            bank_id = special_banks[index]
        else:
            bank_id = _BANKS[index % 3][0]
        opened_at = _BASE - timedelta(days=30) + timedelta(minutes=index)
        rows.append(
            {
                "account_id": f"acct-{index:04d}",
                "bank_id": bank_id,
                "opened_at": _format(opened_at),
            }
        )
    return tuple(rows)


def _transfers(
    seed: int,
    account_count: int,
    transaction_count: int,
    accounts: tuple[dict[str, str], ...],
) -> tuple[tuple[dict[str, Any], ...], tuple[dict[str, str | None], ...]]:
    del account_count
    transactions: list[dict[str, Any]] = []
    truth: list[dict[str, str | None]] = []
    _add_fan_ring(accounts, transactions, truth)
    _add_pass_through(accounts, transactions, truth)
    _add_legitimate(seed, transaction_count, accounts, transactions)
    return tuple(transactions), tuple(truth)


def _add_fan_ring(
    accounts: tuple[dict[str, str], ...],
    transactions: list[dict[str, Any]],
    truth: list[dict[str, str | None]],
) -> None:
    mule = accounts[0]["account_id"]
    sources = [accounts[index]["account_id"] for index in range(1, 5)]
    destinations = [accounts[index]["account_id"] for index in range(5, 9)]
    _truth_account(truth, "mule-ring-fan", mule, "MULE_ACCOUNT")
    for offset, source in enumerate(sources):
        _truth_account(truth, "mule-ring-fan", source, "FAN_IN_SOURCE")
        _append_transfer(
            transactions,
            truth,
            scenario_id="mule-ring-fan",
            label="FAN_IN_TRANSFER",
            from_account_id=source,
            to_account_id=mule,
            amount_minor=150_000,
            event_time=_format(_BASE + timedelta(minutes=offset)),
        )
    for offset, destination in enumerate(destinations):
        _truth_account(truth, "mule-ring-fan", destination, "FAN_OUT_DESTINATION")
        _append_transfer(
            transactions,
            truth,
            scenario_id="mule-ring-fan",
            label="FAN_OUT_TRANSFER",
            from_account_id=mule,
            to_account_id=destination,
            amount_minor=120_000,
            event_time=_format(_BASE + timedelta(minutes=10 + offset)),
        )


def _add_pass_through(
    accounts: tuple[dict[str, str], ...],
    transactions: list[dict[str, Any]],
    truth: list[dict[str, str | None]],
) -> None:
    hops = [accounts[index]["account_id"] for index in range(9, 14)]
    for account_id in hops:
        _truth_account(truth, "pass-through-hops", account_id, "PASS_THROUGH_ACCOUNT")
    for offset in range(4):
        _append_transfer(
            transactions,
            truth,
            scenario_id="pass-through-hops",
            label="PASS_THROUGH_TRANSFER",
            from_account_id=hops[offset],
            to_account_id=hops[offset + 1],
            amount_minor=200_000,
            event_time=_format(_BASE + timedelta(minutes=30 + (offset * 2))),
        )


def _add_legitimate(
    seed: int,
    transaction_count: int,
    accounts: tuple[dict[str, str], ...],
    transactions: list[dict[str, Any]],
) -> None:
    pool = [account["account_id"] for account in accounts[_PATTERN_ACCOUNTS:]]
    rng = random.Random(seed)
    start = _BASE + timedelta(hours=6)
    for offset in range(transaction_count - _PATTERN_TRANSACTIONS):
        source = rng.choice(pool)
        destination = rng.choice(pool)
        while destination == source:
            destination = rng.choice(pool)
        transactions.append(
            {
                "transaction_id": f"txn-{len(transactions):06d}",
                "from_account_id": source,
                "to_account_id": destination,
                "amount_minor": rng.randrange(1_000, 80_000),
                "event_time": _format(start + timedelta(seconds=offset)),
                "currency": "USD",
                "scenario_id": None,
            }
        )


def _append_transfer(
    transactions: list[dict[str, Any]],
    truth: list[dict[str, str | None]],
    *,
    scenario_id: str,
    label: str,
    from_account_id: str,
    to_account_id: str,
    amount_minor: int,
    event_time: str,
) -> None:
    transaction_id = f"txn-{len(transactions):06d}"
    transactions.append(
        {
            "transaction_id": transaction_id,
            "from_account_id": from_account_id,
            "to_account_id": to_account_id,
            "amount_minor": amount_minor,
            "event_time": event_time,
            "currency": "USD",
            "scenario_id": scenario_id,
        }
    )
    truth.append(
        {
            "ground_truth_id": f"gt-{scenario_id}-txn-{transaction_id}",
            "scenario_id": scenario_id,
            "transaction_id": transaction_id,
            "account_id": None,
            "label": label,
        }
    )


def _truth_account(
    truth: list[dict[str, str | None]],
    scenario_id: str,
    account_id: str,
    label: str,
) -> None:
    truth.append(
        {
            "ground_truth_id": f"gt-{scenario_id}-acct-{account_id}-{label}",
            "scenario_id": scenario_id,
            "transaction_id": None,
            "account_id": account_id,
            "label": label,
        }
    )


def canonical_document(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "accounts": sorted(document["accounts"], key=lambda row: row["account_id"]),
        "banks": sorted(document["banks"], key=lambda row: row["bank_id"]),
        "ground_truth": sorted(
            document["ground_truth"],
            key=lambda row: (row["scenario_id"], row["label"], row["ground_truth_id"]),
        ),
        "transactions": sorted(document["transactions"], key=lambda row: row["transaction_id"]),
    }


def document_sha256(document: dict[str, Any]) -> str:
    payload = json.dumps(
        canonical_document(document),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _format(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
