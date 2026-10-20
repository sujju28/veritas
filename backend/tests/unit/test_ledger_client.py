"""Local chain identity checks. A mismatch is not an on-chain verification."""

import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from veritas.ledger.client import (
    ChainIdentityError,
    LedgerClient,
    LedgerConfig,
    anchor_calldata,
)

_CODE = bytes.fromhex("60806040")
_CODE_HASH = hashlib.sha256(_CODE).hexdigest()
_KEY = bytes.fromhex("11" * 32)
_DIGEST = bytes.fromhex("22" * 32)


class _Rpc(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        method = body["method"]
        if method == "eth_chainId":
            result = hex(self.server.chain_id)
        elif method == "eth_getCode":
            result = "0x" if self.server.empty_code else "0x" + _CODE.hex()
        else:
            word = _DIGEST.rjust(32, b"\x00")
            sender = bytes.fromhex("f39Fd6e51aad88F6F4ce6aB8827279cffFb92266")
            blob = b"".join(
                (
                    (1).to_bytes(32, "big"),
                    word,
                    sender.rjust(32, b"\x00"),
                    (7).to_bytes(32, "big"),
                    (9).to_bytes(32, "big"),
                )
            )
            result = "0x" + blob.hex()
        payload = json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": result}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt: str, *args: object) -> None:
        return


def _server(*, chain_id: int = 31337, empty_code: bool = False) -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Rpc)
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


def test_rpc_must_stay_on_loopback() -> None:
    try:
        LedgerClient(_config("http://example.com:8545"))
    except ChainIdentityError:
        return
    raise AssertionError("remote RPC was accepted")


def test_chain_id_and_bytecode_must_match() -> None:
    wrong, wrong_url = _server(chain_id=1)
    empty, empty_url = _server(empty_code=True)
    try:
        try:
            LedgerClient(_config(wrong_url)).validate()
        except ChainIdentityError as exc:
            assert "chain id" in str(exc)
        else:
            raise AssertionError("wrong chain id was accepted")
        try:
            LedgerClient(_config(empty_url)).validate()
        except ChainIdentityError as exc:
            assert "no code" in str(exc)
        else:
            raise AssertionError("empty code was accepted")
    finally:
        wrong.shutdown()
        empty.shutdown()


def test_get_decision_reads_the_commitment() -> None:
    server, url = _server()
    try:
        record = LedgerClient(_config(url)).get_decision(_KEY)
    finally:
        server.shutdown()
    assert record.exists is True
    assert record.evidence_digest == _DIGEST
    assert record.sender == "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266"
    assert record.block_number == 7
    assert record.timestamp == 9


def test_anchor_calldata_rejects_zero_values() -> None:
    encoded = anchor_calldata(_KEY, _DIGEST)
    assert encoded.startswith("0xc7e056bf")
    try:
        anchor_calldata(bytes(32), _DIGEST)
    except ChainIdentityError:
        return
    raise AssertionError("zero key was accepted")
