"""Main entry point for veritas.onchain CLI commands.

Usage:
    python -m veritas.onchain replay --source-db data/veritas.db ...
    python -m veritas.onchain ingest --db data/veritas-onchain.db ...
"""

from __future__ import annotations

import sys

from veritas.onchain.ingest import main as ingest_main
from veritas.onchain.replay import main as replay_main


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("Usage: python -m veritas.onchain {replay,ingest} [options]", file=sys.stderr)
        return 1

    command = args[0]
    rest = args[1:]
    if command == "replay":
        return replay_main(rest)
    elif command == "ingest":
        return ingest_main(rest)
    else:
        print(f"Unknown command: {command}. Choose 'replay' or 'ingest'.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
