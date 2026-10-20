# Third-party licenses

The project license is the MIT license in `LICENSE`. This file is the notice for the pinned dependencies. Direct-dependency licenses were read from installed metadata on 2026-10-20. The transitive audit below was run the same day against the installed Python environment and `frontend/package-lock.json`.

## Direct dependencies

| Package | Version | License |
|---|---|---|
| fastapi | 0.148.0 | MIT |
| pydantic | 2.14.1 | MIT |
| uvicorn | 0.54.0 | BSD-3-Clause |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| rfc8785 | 0.1.4 | Apache-2.0 |
| networkx | 3.7 | BSD-3-Clause |
| scikit-learn | 1.9.1 | BSD-3-Clause |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| react / react-dom | 19.3.1 | MIT |
| vite | 8.3.4 | MIT |
| cytoscape | 3.34.4 | MIT |
| vitest | 5.0.5 | MIT |
| forge-std | v1.9.6 | MIT OR Apache-2.0 |

## Transitive audit

- **Python (installed environment):** MIT, BSD-2/3-Clause, Apache-2.0, MIT-0, PSF-2.0, and dual licenses of those. No GPL, LGPL, or AGPL license metadata was found. The only entries without metadata are this project itself.
- **npm (`package-lock.json`, 89 packages):** MIT 52, Apache-2.0 23, MPL-2.0 12, ISC 1, BSD-3-Clause 1, plus the root package.
- **MPL-2.0 entries:** all 12 are `lightningcss` and its per-platform native binaries, pulled in by Vite as a **build-time** tool. MPL-2.0 is file-level copyleft. This repository does not copy, modify, or redistribute that code, and `node_modules/` and `dist/` are gitignored, so the published source contains none of it. If you ever publish a container image or `node_modules`, include the MPL-2.0 text and source pointer for it.

MIT can be distributed together with these BSD, Apache-2.0, and ISC dependencies when their notices are retained. `forge-std` is installed into `contracts/lib/` and that directory is gitignored. Foundry itself is a development tool installed outside the repository. Anvil's published development accounts are documented in `SECURITY.md`.

This is an engineering check, not legal advice. Have the maintainer confirm the license choice before publishing, particularly if any code was written under an employment agreement.
