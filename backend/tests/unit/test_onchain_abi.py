"""Unit tests for hand-written EVM ABI encoding/decoding and topic hashes."""

import pytest
from veritas.onchain.abi import (
    ACCOUNT_REGISTERED_TOPIC,
    RECORD_TRANSFERS_SELECTOR,
    REGISTER_ACCOUNTS_SELECTOR,
    TRANSFER_RECORDED_TOPIC,
    decode_account_registered_log,
    decode_transfer_recorded_log,
    encode_record_transfers,
    encode_register_accounts,
    from_bytes32,
    from_uint256,
    iso_to_unix,
    to_bytes32,
    to_uint256,
    unix_to_iso,
)


def test_bytes32_roundtrip() -> None:
    text = "acct-0001"
    raw = to_bytes32(text)
    assert len(raw) == 32
    assert raw.startswith(b"acct-0001\x00")
    assert from_bytes32(raw) == text


def test_bytes32_length_check() -> None:
    with pytest.raises(ValueError, match="exceeds 32 ascii bytes"):
        to_bytes32("a" * 33)


def test_uint256_roundtrip() -> None:
    val = 123456789
    raw = to_uint256(val)
    assert len(raw) == 32
    assert from_uint256(raw) == val


def test_timestamp_conversions() -> None:
    iso = "2026-01-15T09:00:00Z"
    ts = iso_to_unix(iso)
    assert ts > 0
    assert unix_to_iso(ts) == iso


def test_encode_register_accounts() -> None:
    accs = ["acct-0001", "acct-0002"]
    banks = ["BANK_A", "BANK_B"]
    opened = [1768467600, 1768467660]

    calldata = encode_register_accounts(accs, banks, opened)
    raw_hex = calldata.removeprefix("0x").removeprefix(
        REGISTER_ACCOUNTS_SELECTOR.removeprefix("0x")
    )
    raw = bytes.fromhex(raw_hex)
    head_size = 3 * 32
    array_size = 32 + 2 * 32
    assert len(raw) == head_size + 3 * array_size

    off0 = from_uint256(raw[0:32])
    off1 = from_uint256(raw[32:64])
    off2 = from_uint256(raw[64:96])
    assert off0 == head_size
    assert off1 == head_size + array_size
    assert off2 == head_size + 2 * array_size


def test_encode_record_transfers() -> None:
    tx_ids = ["txn-000001"]
    froms = ["acct-0001"]
    tos = ["acct-0002"]
    amounts = [50000]
    times = [1768467700]

    calldata = encode_record_transfers(tx_ids, froms, tos, amounts, times)
    assert calldata.startswith(RECORD_TRANSFERS_SELECTOR)


def test_decode_account_registered_log() -> None:
    acc = "acct-0001"
    bank = "BANK_A"
    opened = 1768467600
    sender = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"

    log = {
        "topics": [
            ACCOUNT_REGISTERED_TOPIC,
            "0x" + to_bytes32(acc).hex(),
            "0x" + bytes.fromhex(sender[2:]).rjust(32, b"\x00").hex(),
        ],
        "data": "0x" + to_bytes32(bank).hex() + to_uint256(opened).hex() + to_uint256(42).hex(),
        "blockNumber": "0x2a",
        "transactionHash": "0xabc",
        "logIndex": "0x1",
        "blockHash": "0xdef",
    }

    decoded = decode_account_registered_log(log)
    assert decoded["account_id"] == acc
    assert decoded["bank_id"] == bank
    assert decoded["opened_at"] == opened
    assert decoded["sender"].lower() == sender.lower()
    assert decoded["block_number"] == 42
    assert decoded["log_index"] == 1


def test_decode_transfer_recorded_log() -> None:
    tx_id = "txn-000001"
    from_acct = "acct-0001"
    to_acct = "acct-0002"
    amount = 50000
    event_time = 1768467700
    sender = "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"

    log = {
        "topics": [
            TRANSFER_RECORDED_TOPIC,
            "0x" + to_bytes32(tx_id).hex(),
            "0x" + to_bytes32(from_acct).hex(),
            "0x" + to_bytes32(to_acct).hex(),
        ],
        "data": (
            "0x"
            + to_uint256(amount).hex()
            + to_uint256(event_time).hex()
            + bytes.fromhex(sender[2:]).rjust(32, b"\x00").hex()
            + to_uint256(42).hex()
        ),
        "blockNumber": "0x2a",
        "transactionHash": "0xabc123",
        "logIndex": "0x2",
        "blockHash": "0xdef456",
    }

    decoded = decode_transfer_recorded_log(log)
    assert decoded["transaction_id"] == tx_id
    assert decoded["from_account_id"] == from_acct
    assert decoded["to_account_id"] == to_acct
    assert decoded["amount_minor"] == amount
    assert decoded["event_time"] == event_time
    assert decoded["sender"].lower() == sender.lower()
    assert decoded["block_number"] == 42
    assert decoded["log_index"] == 2
