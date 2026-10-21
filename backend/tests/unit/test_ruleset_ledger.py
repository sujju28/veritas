"""Unit tests for RulesetRegistry ledger client, calldata encoding, and build pin."""

from __future__ import annotations

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from veritas.ledger.client import (
    ChainConfigError,
    ChainIdentityError,
    ChainResetError,
    LedgerConfig,
)
from veritas.ledger.ruleset import (
    DEPRECATE_SELECTOR,
    PINNED_RULESET_REGISTRY_RUNTIME_SHA256,
    REGISTER_SELECTOR,
    RulesetClient,
    deprecate_calldata,
    register_calldata,
    ruleset_key,
)

_CODE = bytes.fromhex("60806040")
_CODE_HASH = hashlib.sha256(_CODE).hexdigest()
_KEY = bytes.fromhex("11" * 32)
_MANIFEST_HASH = bytes.fromhex("22" * 32)


class _RulesetRpc(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        method = body["method"]
        if method == "eth_chainId":
            result = hex(self.server.chain_id)
        elif method == "eth_getCode":
            result = "0x" if self.server.empty_code else "0x" + _CODE.hex()
        elif method == "eth_call":
            # 6 words: exists (1), manifest_sha256, deprecated (0),
            # sender, blockNumber (12), timestamp (123456)
            manifest_word = _MANIFEST_HASH.rjust(32, b"\x00")
            sender = bytes.fromhex("f39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
            blob = b"".join(
                (
                    (1).to_bytes(32, "big"),
                    manifest_word,
                    (0).to_bytes(32, "big"),
                    sender.rjust(32, b"\x00"),
                    (12).to_bytes(32, "big"),
                    (123456).to_bytes(32, "big"),
                )
            )
            result = "0x" + blob.hex()
        elif method == "eth_sendTransaction":
            result = "0x" + "aa" * 32
        else:
            result = None
        payload = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def _server(*, chain_id: int = 31337, empty_code: bool = False) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RulesetRpc)
    server.chain_id = chain_id
    server.empty_code = empty_code
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    return server, f"http://127.0.0.1:{port}"


def _config(url: str, **overrides: object) -> LedgerConfig:
    raw = {
        "rpc_url": url,
        "chain_id": 31337,
        "contract_address": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
        "runtime_code_sha256": _CODE_HASH,
    }
    raw.update(overrides)
    return LedgerConfig(**raw)


def test_ruleset_build_fixture_pinned() -> None:
    fixture_path = (
        Path(__file__).resolve().parents[3]
        / "contracts"
        / "fixtures"
        / "RulesetRegistry.build.json"
    )
    assert fixture_path.exists(), f"Fixture missing at {fixture_path}"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    assert fixture["runtime_sha256"] == PINNED_RULESET_REGISTRY_RUNTIME_SHA256


def test_ruleset_key_derivation() -> None:
    expected = hashlib.sha256(b"VERITAS:RULESET:rules-v1").digest()
    assert ruleset_key("rules-v1") == expected
    assert len(ruleset_key("rules-v1")) == 32


def test_calldata_encoding() -> None:
    calldata = register_calldata(_KEY, _MANIFEST_HASH)
    assert calldata.startswith(REGISTER_SELECTOR)
    assert calldata == REGISTER_SELECTOR + _KEY.hex() + _MANIFEST_HASH.hex()

    dep_data = deprecate_calldata(_KEY)
    assert dep_data.startswith(DEPRECATE_SELECTOR)
    assert dep_data == DEPRECATE_SELECTOR + _KEY.hex()


def test_calldata_validation() -> None:
    with pytest.raises(ChainIdentityError):
        register_calldata(b"short", _MANIFEST_HASH)
    with pytest.raises(ChainIdentityError):
        register_calldata(bytes(32), _MANIFEST_HASH)
    with pytest.raises(ChainIdentityError):
        deprecate_calldata(bytes(32))


def test_ruleset_client_validate_and_get() -> None:
    server, url = _server()
    try:
        client = RulesetClient(_config(url))
        client.validate()
        entry = client.get_ruleset(_KEY)
        assert entry.exists is True
        assert entry.manifest_sha256 == _MANIFEST_HASH
        assert entry.deprecated is False
        assert entry.sender == "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
        assert entry.block_number == 12
        assert entry.timestamp == 123456
    finally:
        server.shutdown()


def test_ruleset_client_rejects_wrong_chain_or_empty_code() -> None:
    wrong_server, wrong_url = _server(chain_id=1)
    empty_server, empty_url = _server(empty_code=True)
    try:
        with pytest.raises(ChainConfigError):
            RulesetClient(_config(wrong_url)).validate()
        with pytest.raises(ChainResetError):
            RulesetClient(_config(empty_url)).validate()
    finally:
        wrong_server.shutdown()
        empty_server.shutdown()
