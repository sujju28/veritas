"""Write the publishable benchmark study. The 10k scale is this command's confirmation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from veritas.bench.chain import measure_chain
from veritas.bench.compare import write_comparison
from veritas.bench.study import run_study, write_study
from veritas.evidence.keys import registry_path_for


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure local VERITAS timings")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--samples", type=int, default=15)
    parser.add_argument("--skip-chain", action="store_true")
    args = parser.parse_args(argv)
    document = run_study(
        args.output,
        seed=args.seed,
        warmup=args.warmup,
        samples=args.samples,
    )
    if args.skip_chain:
        document["chain"] = {"measured": False, "reason": "chain section skipped"}
    else:
        document["chain"] = measure_chain(args.output, seed=args.seed, samples=args.samples)
        document["rows"].extend(document["chain"].get("rows", []))
    write_study(args.output, document)
    write_comparison(args.output, document)
    _remove_bench_secrets(args.output)
    summary = {"rows": len(document["rows"]), "chain_measured": document["chain"]["measured"]}
    print(json.dumps(summary))
    return 0


def _remove_bench_secrets(output_dir: Path) -> None:
    key_path = output_dir / ".bench-issuer.pem"
    registry_path_for(key_path).unlink(missing_ok=True)
    key_path.unlink(missing_ok=True)
    for path in output_dir.glob(".bench-*"):
        if path.is_file():
            path.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
