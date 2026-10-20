"""Load a seeded synthetic dataset into the local SQLite file."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from veritas.simulator.scales import BenchmarkConfirmationRequired, ScaleError
from veritas.simulator.store import DemoDataRetained, ReseedRequired, seed_database


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the VERITAS synthetic dataset")
    parser.add_argument("--scale", default="default", choices=["tiny", "default", "benchmark"])
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--replace", default="0")
    parser.add_argument("--confirm-benchmark", default="0")
    parser.add_argument(
        "--db",
        default=os.environ.get("VERITAS_DB_PATH", "data/veritas.db"),
    )
    args = parser.parse_args(argv)
    replace = _flag(args.replace)
    confirm = _flag(args.confirm_benchmark)
    if args.seed < 0:
        print("seed must be a non-negative integer", file=sys.stderr)
        return 2
    try:
        result = seed_database(
            Path(args.db),
            seed=args.seed,
            scale=args.scale,
            replace=replace,
            confirm_benchmark=confirm,
        )
    except BenchmarkConfirmationRequired as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ScaleError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except ReseedRequired as exc:
        print(str(exc), file=sys.stderr)
        return 3
    except DemoDataRetained as exc:
        print(str(exc), file=sys.stderr)
        return 3
    public = {
        "seed": result["seed"],
        "scale": result["scale"],
        "accounts": result["accounts"],
        "transactions": result["transactions"],
        "scenarios": result["scenarios"],
        "replaced": result["replaced"],
        "content_sha256": result["content_sha256"],
    }
    print(json.dumps(public, sort_keys=True))
    return 0


def _flag(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes"}


if __name__ == "__main__":
    raise SystemExit(main())
