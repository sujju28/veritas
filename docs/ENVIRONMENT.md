# VERITAS environment preflight (Phase 00)

**Date:** 2026-10-19  
**Scope:** host inspection plus the approved native toolchain install. No application code, Podman machine, or service process was started.

## Host

| Item | Observed |
|---|---|
| Architecture | `arm64` (`uname -m`), `hw.optional.arm64=1` |
| CPU | Apple M1, 8 physical cores |
| Kernel | Darwin 25.6.0, `RELEASE_ARM64_T8103` |
| macOS | 26.6.2 (build 25G83) |
| Physical RAM | `8589934592` bytes = **8.00 GiB** |
| Shell | `/bin/zsh`, zsh 5.9 (`arm64-apple-darwin25.0`) |
| Rosetta 2 | false |
| Data volume free | **58 GiB** available of 228 GiB after installs (`/dev/disk3s5`) |
| Command Line Tools | `/Library/Developer/CommandLineTools`, package `26.5.0.0.1777544298` |
| Clang | Apple clang 21.0.0, target `arm64-apple-darwin25.6.0` |
| Xcode reported by Homebrew | 27.0 |

ENV-01 matches the planned machine: Apple Silicon and 8 GiB unified memory.

## Memory

Before installs, `vm.swapusage` was **15358.94 MiB used of 16384.00 MiB**, with about 84 MiB physical memory unused and a 28% system-wide free percentage. After the installs, swap used was **15733.25 MiB of 16384.00 MiB** and the free percentage was 36%. Ports 8000, 5173, and 8545 stayed free. Podman is still absent and was not started.

Keep later work to one native process at a time. Close other heavy apps before the API, Vite, and Anvil run together.

## Confirmed toolchain

Login shells source `~/.zprofile`, which now prepends `$HOME/.foundry/bin`. A login `zsh` resolves `anvil`, `forge`, `node`, and `npm` as below.

| Tool | Confirmed | Native? |
|---|---|---|
| Git on PATH | `/opt/homebrew/bin/git` **2.45.2**, Mach-O arm64 | yes |
| Python project venv | `<repo>/.venv` from Homebrew CPython **3.14.2**, Mach-O arm64, SQLite 3.51.2 | yes |
| Node.js | `/opt/homebrew/bin/node` **v24.22.0**, Mach-O arm64 (`node@24` keg) | yes |
| npm | **11.19.1** | yes, script on the same keg |
| Foundry | `~/.foundry/bin/{anvil,forge,cast}` **1.8.5**, commit `51a52c59cffd940f76eddd0b4bb1791aa4b5ac7f`, Mach-O arm64 | yes |
| Homebrew | **7.0.10** at `/opt/homebrew` (was 5.1.15 at inspection; auto-updated during the Node upgrade) | yes |
| Podman / Docker | absent | not started |

python.org 3.10.4 and Command Line Tools Python 3.9.6 remain installed and are not the project interpreter. `python@3.12` and `python@3.13` were not installed.

PyPI, checked before the venv was created, publishes arm64 macOS wheels usable with CPython 3.14 for NumPy 2.5.4, scikit-learn 1.9.1, and cryptography 50.0.2. Those packages are not installed yet. Exact pins belong in the Phase 01 lockfile.

This directory is still not a Git repository. No commit was created.

## Install record

Approved on 2026-10-19 and executed in this order.

### Foundry v1.8.5 darwin_arm64

Downloaded the official release archive and its `.sha256`. `shasum -a 256 -c` reported **OK**.

```text
56049728e25e44a61c7f2e49438023b0890cb45850ffcb7c882f90cd998baf83  foundry_v1.8.5_darwin_arm64.tar.gz
```

The archive contains `forge`, `cast`, `anvil`, `chisel`, and `solar`. They were extracted to `~/.foundry/bin`. The vendor `curl | bash` installer was not used. Anvil was not left running; `anvil --help` exits successfully.

`~/.zprofile` gained:

```bash
export PATH="$HOME/.foundry/bin:$PATH"
```

### Python virtualenv

```bash
/opt/homebrew/bin/python3.14 -m venv .venv
```

`.venv/bin/python` prints `3.14.2 arm64`.

### Node.js 24.22.0

`brew install node@24` with auto-update disabled poured bottle **24.16.0** from the local formula snapshot. `brew info` then showed stable **24.22.0**, the Active LTS patch approved for this machine. `brew upgrade node@24` poured the `arm64_tahoe` bottle and left `v24.22.0` / npm `11.19.1`. Homebrew linked `node` and `npm` into `/opt/homebrew/bin`.

That upgrade also auto-updated Homebrew from 5.1.15 to 7.0.10 and upgraded Node's bottled dependencies (`c-ares`, `hdrhistogram_c`, `libnghttp2`, `libnghttp3`, `libngtcp2`, `libuv`, `simdjson`, `readline`, `sqlite`, `xz`, `ca-certificates`, and a new `openssl@4` 4.0.3). The first install's automatic `brew cleanup` removed outdated kegs that had not been cleaned in 30 days, including the previous `icu4c@78` 78.2, `sqlite` 3.51.2, `xz` 5.6.4/5.8.2, and `zstd` 1.5.7.

## Residual risk

Installing `openssl@4` unlinked the generic Homebrew `openssl` name from OpenSSL 3. `/opt/homebrew/bin/openssl` is now **OpenSSL 4.0.3**. `openssl@3` **3.6.2** is still installed at `/opt/homebrew/opt/openssl@3`. Homebrew Python 3.14 still reports `OpenSSL 3.6.2` through `ssl.OPENSSL_VERSION`, and Git 2.45.2 still runs.

Swap remains nearly full. The dev stack should stay native and serial.

## Gate

Required runtimes are confirmed usable: Python 3.14.2 arm64 venv, Node.js v24.22.0 arm64, npm 11.19.1, and Foundry 1.8.5 arm64 `anvil`/`forge`/`cast`. No container VM is running. Phase 00 is **ACCEPTED**. Application tests remain **NOT TESTED** until later phases.
