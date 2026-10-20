"""Independent verifier CLI. It does not call the scoring API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from veritas.ledger.commitment import PINNED_RUNTIME_SHA256
from veritas.verifier.check import verify_on_chain


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m veritas.verifier")
    parser.add_argument("command", choices=["verify"])
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--trusted-keys", type=Path, required=True)
    parser.add_argument("--rpc-url", default="http://127.0.0.1:8545")
    parser.add_argument("--chain-id", type=int, required=True)
    parser.add_argument("--contract-address", required=True)
    parser.add_argument("--code-sha256", default=PINNED_RUNTIME_SHA256)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    registry = json.loads(args.trusted_keys.read_text(encoding="utf-8"))
    result = verify_on_chain(
        receipt,
        registry,
        rpc_url=args.rpc_url,
        chain_id=args.chain_id,
        contract_address=args.contract_address,
        runtime_code_sha256=args.code_sha256,
    )
    if args.json:
        json.dump(result, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(result["status"])
    return 0 if result["status"] == "VERIFIED_ONCHAIN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
