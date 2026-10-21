# VERITAS local targets. Tools come from the repository virtualenv, not the global PATH.
ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VENV := $(ROOT)/.venv
PY := $(VENV)/bin/python
PYTEST := $(VENV)/bin/pytest
RUFF := $(VENV)/bin/ruff
UVICORN := $(VENV)/bin/uvicorn
PYTHON ?= /opt/homebrew/bin/python3.14
FORGE ?= $(HOME)/.foundry/bin/forge
ANVIL ?= $(HOME)/.foundry/bin/anvil
CAST ?= $(HOME)/.foundry/bin/cast
CHAIN_ID ?= 31337
RPC_URL ?= http://127.0.0.1:8545

.DEFAULT_GOAL := help

SCALE ?= default
SEED ?= 42
REPLACE ?= 0
CONFIRM ?= 0

.PHONY: help setup backend seed test-unit lint format-check chain-start contract-test contract-deploy worker verify test-e2e frontend frontend-build frontend-test benchmark capture-tamper ruleset-manifest ruleset-register onchain-deploy onchain-replay onchain-ingest

NPM ?= npm

RECEIPT ?=
TRUSTED_KEYS ?=
CONTRACT_ADDRESS ?= $(shell awk -F= '/^VERITAS_CONTRACT_ADDRESS=/{print $$2}' "$(ROOT)/.env.local")
RULESET_REGISTRY_ADDRESS ?= $(shell awk -F= '/^VERITAS_RULESET_REGISTRY_ADDRESS=/{print $$2}' "$(ROOT)/.env.local")
TRANSFER_LOG_ADDRESS ?= $(shell awk -F= '/^VERITAS_TRANSFER_LOG_ADDRESS=/{print $$2}' "$(ROOT)/.env.local")

help: ## List the local targets
	@printf "Targets:\n"
	@printf "  setup          Create .venv with Python 3.14 and install locked backend dependencies\n"
	@printf "  backend        Run one Uvicorn worker on 127.0.0.1:8000 (stop with Ctrl-C)\n"
	@printf "  seed           Load seed $(SEED) at scale $(SCALE). REPLACE=1 reseeds demo rows only\n"
	@printf "  test-unit      Run backend unit tests with the virtualenv pytest\n"
	@printf "  lint           Run Ruff checks on the backend\n"
	@printf "  format-check   Check backend formatting with Ruff\n"
	@printf "  chain-start    Run native Anvil on 127.0.0.1:8545 (stop with Ctrl-C)\n"
	@printf "  contract-test  Run Foundry tests for DecisionRegistry, RulesetRegistry, TransferLog\n"
	@printf "  contract-deploy Deploy registries to the running local Anvil\n"
	@printf "  worker         Poll the outbox and anchor on local Anvil (stop with Ctrl-C)\n"
	@printf "  verify         Run the independent verifier. Set RECEIPT and TRUSTED_KEYS\n"
	@printf "  test-e2e       Anchor one fresh receipt on Anvil and verify it\n"
	@printf "  frontend       Run the Vite dashboard on 127.0.0.1:5173\n"
	@printf "  frontend-build Build the dashboard\n"
	@printf "  frontend-test  Run the dashboard unit tests\n"
	@printf "  benchmark      Time tiny, default, and 10k runs and write docs/benchmarks\n"
	@printf "  capture-tamper Run a temporary Anvil and write docs/publication/tamper-cli-live.txt\n"
	@printf "  ruleset-manifest Generate docs/rulesets/rules-v1.json from declared risk rules\n"
	@printf "  ruleset-register Register canonical ruleset manifest on local RulesetRegistry\n"
	@printf "  onchain-deploy Deploy contracts to local Anvil (alias for contract-deploy)\n"
	@printf "  onchain-replay Replay accounts and transactions from SQLite onto TransferLog\n"
	@printf "  onchain-ingest Ingest events from TransferLog into data/veritas-onchain.db\n"

setup: ## Create the virtualenv and install the locked Phase 01 dependencies
	@test -x "$(PY)" || "$(PYTHON)" -m venv "$(VENV)"
	"$(PY)" -m pip install --upgrade pip
	"$(PY)" -m pip install --require-virtualenv -e "$(ROOT)/backend[dev]"

backend: ## Start the API on the loopback interface with one worker
	cd "$(ROOT)/backend" && \
		VERITAS_HOST=127.0.0.1 \
		VERITAS_PORT=8000 \
		VERITAS_DB_PATH="$(ROOT)/data/veritas.db" \
		"$(UVICORN)" veritas.api.app:app --host 127.0.0.1 --port 8000 --workers 1

seed: ## Seed the synthetic dataset. Benchmark also needs CONFIRM=1
	cd "$(ROOT)/backend" && \
		"$(PY)" -m veritas.simulator.cli \
		--db "$(ROOT)/data/veritas.db" \
		--scale "$(SCALE)" \
		--seed "$(SEED)" \
		--replace "$(REPLACE)" \
		--confirm-benchmark "$(CONFIRM)"

test-unit: ## Run unit tests
	cd "$(ROOT)/backend" && "$(PYTEST)" tests/unit -q

lint: ## Lint the backend with Ruff
	"$(RUFF)" check "$(ROOT)/backend"

format-check: ## Fail if Ruff would reformat the backend
	"$(RUFF)" format --check "$(ROOT)/backend"

chain-start: ## Native Anvil on the loopback interface. Deleting .anvil/ wipes commitments.
	mkdir -p "$(ROOT)/.anvil"
	"$(ANVIL)" --host 127.0.0.1 --port 8545 --chain-id "$(CHAIN_ID)" \
		--state "$(ROOT)/.anvil/state.json" --state-interval 15

contract-test: ## Foundry unit tests. No chain process is started.
	@test -d "$(ROOT)/contracts/lib/forge-std" || \
		(cd "$(ROOT)/contracts" && "$(FORGE)" install --no-git foundry-rs/forge-std@v1.9.6)
	cd "$(ROOT)/contracts" && "$(FORGE)" test

contract-deploy: ## Deploy to the running loopback Anvil and write .env.local
	FORGE="$(FORGE)" CAST="$(CAST)" PY="$(PY)" RPC_URL="$(RPC_URL)" CHAIN_ID="$(CHAIN_ID)" \
		"$(ROOT)/contracts/script/deploy-local.sh"

worker: ## Poll one outbox job at a time against the local Anvil registry
	cd "$(ROOT)/backend" && "$(PY)" -m veritas.workers.anchor \
		--db "$(ROOT)/data/veritas.db" \
		--rpc-url "$(RPC_URL)" \
		--chain-id "$(CHAIN_ID)" \
		--contract-address "$(CONTRACT_ADDRESS)" \
		--poll-seconds 2

verify: ## Independent verifier. Does not call the scoring API
	cd "$(ROOT)/backend" && "$(PY)" -m veritas.verifier verify \
		--receipt "$(RECEIPT)" \
		--trusted-keys "$(TRUSTED_KEYS)" \
		--rpc-url "$(RPC_URL)" \
		--chain-id "$(CHAIN_ID)" \
		--contract-address "$(CONTRACT_ADDRESS)" \
		--json

test-e2e: ## Fresh receipt, anchor, independent verify, and an Anvil outage
	cd "$(ROOT)/backend" && "$(PYTEST)" tests/e2e -q

frontend: ## Vite dashboard on the loopback interface. Stop with Ctrl-C
	cd "$(ROOT)/frontend" && "$(NPM)" run dev

frontend-build: ## Typecheck and build the dashboard
	cd "$(ROOT)/frontend" && "$(NPM)" run build

frontend-test: ## Dashboard unit tests
	cd "$(ROOT)/frontend" && "$(NPM)" test

benchmark: ## Explicit 10k study plus a temporary Anvil sample. Stop other chain users first.
	cd "$(ROOT)/backend" && "$(PY)" -m veritas.bench \
		--output "$(ROOT)/docs/benchmarks" \
		--seed "$(SEED)" \
		--warmup 2 \
		--samples 15

capture-tamper: ## Temporary Anvil, one anchored receipt, then the verifier on original and tampered copies
	cd "$(ROOT)/backend" && "$(PY)" scripts/capture_tamper_evidence.py \
		--output "$(ROOT)/docs/publication/tamper-cli-live.txt"

ruleset-manifest: ## Generate docs/rulesets/rules-v1.json from declared risk rules and constants
	cd "$(ROOT)/backend" && "$(PY)" -m veritas.risk.manifest \
		--output "$(ROOT)/docs/rulesets/rules-v1.json"

ruleset-register: ## Register canonical ruleset manifest on local RulesetRegistry
	cd "$(ROOT)/backend" && "$(PY)" -m veritas.ledger.ruleset register \
		--manifest "$(ROOT)/docs/rulesets/rules-v1.json" \
		--rpc-url "$(RPC_URL)" \
		--chain-id "$(CHAIN_ID)" \
		--contract-address "$(RULESET_REGISTRY_ADDRESS)"

onchain-deploy: contract-deploy ## Deploy contracts to local Anvil

onchain-replay: ## Replay accounts and transactions from SQLite onto TransferLog
	cd "$(ROOT)/backend" && "$(PY)" -m veritas.onchain.replay \
		--source-db "$(ROOT)/data/veritas.db" \
		--rpc-url "$(RPC_URL)" \
		--chain-id "$(CHAIN_ID)" \
		--contract-address "$(TRANSFER_LOG_ADDRESS)"

onchain-ingest: ## Ingest events from TransferLog into data/veritas-onchain.db
	cd "$(ROOT)/backend" && "$(PY)" -m veritas.onchain.ingest \
		--db "$(ROOT)/data/veritas-onchain.db" \
		--rpc-url "$(RPC_URL)" \
		--chain-id "$(CHAIN_ID)" \
		--contract-address "$(TRANSFER_LOG_ADDRESS)"


