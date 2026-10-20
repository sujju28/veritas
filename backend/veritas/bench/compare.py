"""Compare a signed local audit log with a local Anvil commitment."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def write_comparison(output_dir: Path, document: dict[str, Any]) -> None:
    score = _cell(document, "default", "graph_score")
    sign = _cell(document, "default", "sign")
    verify = _cell(document, "default", "offline_verify")
    try:
        anchor = _cell(document, "chain", "anchor_confirm")
    except KeyError:
        anchor = None
    chain = document.get("chain", {})
    if anchor is None:
        anchor_text = f"not measured ({chain.get('reason', 'no chain sample')})"
    else:
        anchor_text = f"{anchor['p50_ms']:.3f} ms (n={anchor['n']})"
    lines = [
        "# Signed audit log and local Anvil commitment",
        "",
        f"Generated {document['generated_at']}. Seed {document['seed']}.",
        f"Git revision `{document['git_revision']}`.",
        (
            f"Host `{document['os']}` `{document['machine']}`, "
            f"physical RAM {document['ram_bytes']} bytes, Python {document['python']}."
        ),
        "Latency unit is milliseconds. RSS unit is bytes.",
        (
            f"Percentiles use nearest-rank after {document['warmup']} discarded warm-up calls. "
            f"Scoring mode is `{document['scoring_mode']}`."
        ),
        "These figures are one local run, not a bank production result.",
        "With 15 samples, nearest-rank p95 and p99 can select the same observation.",
        "Graph scoring reads the capped lookback window, so a 10k dataset",
        "costs more to generate while one score stays near the default-window cost.",
        "",
        "## What both approaches detect",
        "",
        "A signed audit log stores the RFC 8785 payload, its SHA-256 digest,",
        "and an Ed25519 signature under a pinned issuer key.",
        "An on-chain commitment stores only the opaque decision-key digest",
        "and that same evidence digest.",
        "Changing a signed field changes the digest, so both the offline check",
        "and a later chain comparison reject it.",
        "Neither check detects a change that is re-signed by the issuer key holder.",
        "",
        "## Trust and operations",
        "",
        "| | Signed local audit log | Local Anvil commitment |",
        "|---|---|---|",
        "| Modification check | Canonical digest and Ed25519 | Same digest plus the chain digest |",
        "| Trust | Issuer key and SQLite write access | Issuer key, bytecode, writer, operator |",
        "| Processes | API process | API, Anvil, deploy, and worker |",
        "| Failure | Decision stays anchor status PENDING | RPC loss queues a bounded retry |",
        (
            "| Measured default p50 | "
            f"sign {sign['p50_ms']:.3f} ms, verify {verify['p50_ms']:.3f} ms, "
            f"score {score['p50_ms']:.3f} ms | anchor {anchor_text} |"
        ),
        "",
        "## What this local chain does not show",
        "",
        "Anvil here is one resettable development chain on 127.0.0.1.",
        "One operator can stop it, replace its state file, or redeploy the contract.",
        "That is not a permissioned QBFT ledger.",
        "It does not show a cross-bank governance advantage.",
        "The extra cost is a second process, a writer role,",
        "confirmation latency, and an outage path.",
        "A commitment on this chain does not outrank the issuer key",
        "when the same person controls both.",
        "",
    ]
    (output_dir / "COMPARISON.md").write_text("\n".join(lines), encoding="utf-8")


def _cell(document: dict[str, Any], scale: str, operation: str) -> dict[str, Any]:
    for row in document["rows"]:
        if row["scale"] == scale and row["operation"] == operation:
            return row
    raise KeyError(f"missing {scale} {operation}")
