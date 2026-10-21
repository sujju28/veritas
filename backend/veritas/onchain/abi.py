"""Hand-written EVM ABI encoding and decoding for TransferLog.

Zero external dependencies. Supports fixed-width bytes32, uint128, uint64,
and dynamic arrays. Pinned event topic hashes match Foundry `cast sig-event`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

REGISTER_ACCOUNTS_SELECTOR = "0xb180b205"
RECORD_TRANSFERS_SELECTOR = "0xced560af"

ACCOUNT_REGISTERED_TOPIC = "0x9cf32dc9e1631362b242b6a77fcfad9a16ec1dee8febcda375b3a4494545e70f"
TRANSFER_RECORDED_TOPIC = "0x65b61e004a32233a80c77fb51fff9a4e03dfb3e21cdac8a6e290d01071d0f6e6"


def iso_to_unix(iso_str: str) -> int:
    return int(datetime.fromisoformat(iso_str.replace("Z", "+00:00")).timestamp())


def unix_to_iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_bytes32(text: str) -> bytes:
    encoded = text.encode("ascii")
    if len(encoded) > 32:
        raise ValueError(f"Identifier '{text}' exceeds 32 ascii bytes")
    return encoded.ljust(32, b"\x00")


def from_bytes32(raw: bytes) -> str:
    if len(raw) != 32:
        raise ValueError(f"Expected 32 bytes, got {len(raw)}")
    return raw.rstrip(b"\x00").decode("ascii")


def to_uint256(val: int) -> bytes:
    if val < 0:
        raise ValueError(f"Value {val} cannot be negative")
    return val.to_bytes(32, "big")


def from_uint256(raw: bytes) -> int:
    return int.from_bytes(raw, "big")


def encode_register_accounts(
    account_ids: list[str],
    bank_ids: list[str],
    opened_ats: list[int],
) -> str:
    n = len(account_ids)
    if not (n == len(bank_ids) == len(opened_ats)):
        raise ValueError("Array lengths must match")

    head_size = 3 * 32
    array_payload_size = 32 + (n * 32)

    offset0 = head_size
    offset1 = offset0 + array_payload_size
    offset2 = offset1 + array_payload_size

    head = b"".join((to_uint256(offset0), to_uint256(offset1), to_uint256(offset2)))

    data0 = b"".join([to_uint256(n)] + [to_bytes32(acc) for acc in account_ids])
    data1 = b"".join([to_uint256(n)] + [to_bytes32(bank) for bank in bank_ids])
    data2 = b"".join([to_uint256(n)] + [to_uint256(ts) for ts in opened_ats])

    payload = head + data0 + data1 + data2
    return REGISTER_ACCOUNTS_SELECTOR + payload.hex()


def encode_record_transfers(
    tx_ids: list[str],
    froms: list[str],
    tos: list[str],
    amounts_minor: list[int],
    event_times: list[int],
) -> str:
    n = len(tx_ids)
    if not (n == len(froms) == len(tos) == len(amounts_minor) == len(event_times)):
        raise ValueError("Array lengths must match")

    head_size = 5 * 32
    array_payload_size = 32 + (n * 32)

    offset0 = head_size
    offset1 = offset0 + array_payload_size
    offset2 = offset1 + array_payload_size
    offset3 = offset2 + array_payload_size
    offset4 = offset3 + array_payload_size

    head = b"".join(
        (
            to_uint256(offset0),
            to_uint256(offset1),
            to_uint256(offset2),
            to_uint256(offset3),
            to_uint256(offset4),
        )
    )

    data0 = b"".join([to_uint256(n)] + [to_bytes32(tx_id) for tx_id in tx_ids])
    data1 = b"".join([to_uint256(n)] + [to_bytes32(f) for f in froms])
    data2 = b"".join([to_uint256(n)] + [to_bytes32(t) for t in tos])
    data3 = b"".join([to_uint256(n)] + [to_uint256(a) for a in amounts_minor])
    data4 = b"".join([to_uint256(n)] + [to_uint256(t) for t in event_times])

    payload = head + data0 + data1 + data2 + data3 + data4
    return RECORD_TRANSFERS_SELECTOR + payload.hex()


def decode_account_registered_log(log: dict[str, Any]) -> dict[str, Any]:
    topics: list[str] = log.get("topics", [])
    if len(topics) < 3 or topics[0].lower() != ACCOUNT_REGISTERED_TOPIC.lower():
        raise ValueError("Not an AccountRegistered log")

    account = from_bytes32(bytes.fromhex(topics[1].removeprefix("0x")))
    sender = "0x" + topics[2].removeprefix("0x")[-40:]

    raw_data = bytes.fromhex(log.get("data", "").removeprefix("0x"))
    if len(raw_data) < 96:
        raise ValueError("AccountRegistered log data is short")

    bank = from_bytes32(raw_data[0:32])
    opened_at = from_uint256(raw_data[32:64])
    block_num_data = from_uint256(raw_data[64:96])

    log_block = (
        int(log["blockNumber"], 16)
        if isinstance(log.get("blockNumber"), str)
        else log.get("blockNumber", block_num_data)
    )
    tx_hash = log.get("transactionHash", "")
    log_index = (
        int(log["logIndex"], 16) if isinstance(log.get("logIndex"), str) else log.get("logIndex", 0)
    )
    block_hash = log.get("blockHash", "")

    return {
        "account_id": account,
        "bank_id": bank,
        "opened_at": opened_at,
        "sender": sender,
        "block_number": log_block,
        "tx_hash": tx_hash,
        "log_index": log_index,
        "block_hash": block_hash,
    }


def decode_transfer_recorded_log(log: dict[str, Any]) -> dict[str, Any]:
    topics: list[str] = log.get("topics", [])
    if len(topics) < 4 or topics[0].lower() != TRANSFER_RECORDED_TOPIC.lower():
        raise ValueError("Not a TransferRecorded log")

    tx_id = from_bytes32(bytes.fromhex(topics[1].removeprefix("0x")))
    from_acct = from_bytes32(bytes.fromhex(topics[2].removeprefix("0x")))
    to_acct = from_bytes32(bytes.fromhex(topics[3].removeprefix("0x")))

    raw_data = bytes.fromhex(log.get("data", "").removeprefix("0x"))
    if len(raw_data) < 128:
        raise ValueError("TransferRecorded log data is short")

    amount_minor = from_uint256(raw_data[0:32])
    event_time = from_uint256(raw_data[32:64])
    sender = "0x" + raw_data[64:96].hex()[-40:]
    block_num_data = from_uint256(raw_data[96:128])

    log_block = (
        int(log["blockNumber"], 16)
        if isinstance(log.get("blockNumber"), str)
        else log.get("blockNumber", block_num_data)
    )
    tx_hash = log.get("transactionHash", "")
    log_index = (
        int(log["logIndex"], 16) if isinstance(log.get("logIndex"), str) else log.get("logIndex", 0)
    )
    block_hash = log.get("blockHash", "")

    return {
        "transaction_id": tx_id,
        "from_account_id": from_acct,
        "to_account_id": to_acct,
        "amount_minor": amount_minor,
        "event_time": event_time,
        "sender": sender,
        "block_number": log_block,
        "tx_hash": tx_hash,
        "log_index": log_index,
        "block_hash": block_hash,
    }
