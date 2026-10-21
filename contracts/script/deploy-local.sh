#!/bin/sh
# Deploy DecisionRegistry to the local Anvil process. Refuses any non-loopback RPC.
# The keys below are Anvil's published sample keys, read from the public fixture.
set -eu

ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$ROOT"
export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
FORGE=${FORGE:-"$HOME/.foundry/bin/forge"}
CAST=${CAST:-"$HOME/.foundry/bin/cast"}
PY=${PY:-"$ROOT/.venv/bin/python"}
RPC=${RPC_URL:-http://127.0.0.1:8545}
CHAIN_ID=${CHAIN_ID:-31337}

case "$RPC" in
  http://127.0.0.1:*|http://localhost:*) ;;
  *)
    echo "Refusing RPC that is not loopback: $RPC" >&2
    exit 1
    ;;
esac

observed=$("$CAST" chain-id --rpc-url "$RPC")
if [ "$observed" != "$CHAIN_ID" ]; then
  echo "Anvil chain id $observed does not match $CHAIN_ID" >&2
  exit 1
fi

eval "$("$PY" - <<'PY'
import json
from pathlib import Path
fixture = json.loads(Path("contracts/fixtures/anvil-public-dev.json").read_text())
print(f"DEPLOYER={fixture['deployer_address']}")
print(f"DEPLOY_KEY={fixture['public_test_private_key']}")
print(f"OTHER_KEY={fixture['unauthorized_public_test_private_key']}")
PY
)"

cd "$ROOT/contracts"
receipt=$("$FORGE" create src/DecisionRegistry.sol:DecisionRegistry \
  --rpc-url "$RPC" \
  --private-key "$DEPLOY_KEY" \
  --broadcast \
  --constructor-args "$DEPLOYER")
cd "$ROOT"
printf '%s\n' "$receipt"

address=$(printf '%s\n' "$receipt" | awk '/Deployed to:/ {print $3}')
tx=$(printf '%s\n' "$receipt" | awk '/Transaction hash:/ {print $3}')
if [ -z "$address" ] || [ -z "$tx" ]; then
  echo "forge create did not report an address" >&2
  exit 1
fi

code_hash=$(
  "$CAST" code "$address" --rpc-url "$RPC" | "$PY" -c '
import hashlib, sys
text = sys.stdin.read().strip().removeprefix("0x")
print(hashlib.sha256(bytes.fromhex(text)).hexdigest())
'
)
pinned=$("$PY" -c 'import json; print(json.load(open("contracts/fixtures/DecisionRegistry.build.json"))["runtime_sha256"])')
if [ "$code_hash" != "$pinned" ]; then
  echo "runtime bytecode $code_hash does not match pinned $pinned" >&2
  exit 1
fi

key=0x1111111111111111111111111111111111111111111111111111111111111111
digest=0x2222222222222222222222222222222222222222222222222222222222222222
"$CAST" send "$address" "anchorDecision(bytes32,bytes32)" "$key" "$digest" \
  --rpc-url "$RPC" --private-key "$DEPLOY_KEY" >/dev/null
"$CAST" send "$address" "anchorDecision(bytes32,bytes32)" "$key" "$digest" \
  --rpc-url "$RPC" --private-key "$DEPLOY_KEY" >/dev/null
if "$CAST" send "$address" "anchorDecision(bytes32,bytes32)" "$key" \
  0x3333333333333333333333333333333333333333333333333333333333333333 \
  --rpc-url "$RPC" --private-key "$DEPLOY_KEY" >/dev/null 2>&1; then
  echo "different digest was accepted" >&2
  exit 1
fi
if "$CAST" send "$address" "anchorDecision(bytes32,bytes32)" "$key" "$digest" \
  --rpc-url "$RPC" --private-key "$OTHER_KEY" >/dev/null 2>&1; then
  echo "unauthorized writer was accepted" >&2
  exit 1
fi

stored=$("$CAST" call "$address" "getDecision(bytes32)(bool,bytes32,address,uint64,uint64)" \
  "$key" --rpc-url "$RPC")
printf '%s\n' "$stored" | head -n 1 | grep -q "true"

cd "$ROOT/contracts"
ruleset_receipt=$("$FORGE" create src/RulesetRegistry.sol:RulesetRegistry \
  --rpc-url "$RPC" \
  --private-key "$DEPLOY_KEY" \
  --broadcast)
cd "$ROOT"
printf '%s\n' "$ruleset_receipt"

ruleset_address=$(printf '%s\n' "$ruleset_receipt" | awk '/Deployed to:/ {print $3}')
ruleset_tx=$(printf '%s\n' "$ruleset_receipt" | awk '/Transaction hash:/ {print $3}')
if [ -z "$ruleset_address" ] || [ -z "$ruleset_tx" ]; then
  echo "forge create did not report a ruleset registry address" >&2
  exit 1
fi

ruleset_code_hash=$(
  "$CAST" code "$ruleset_address" --rpc-url "$RPC" | "$PY" -c '
import hashlib, sys
text = sys.stdin.read().strip().removeprefix("0x")
print(hashlib.sha256(bytes.fromhex(text)).hexdigest())
'
)
pinned_ruleset=$("$PY" -c 'import json; print(json.load(open("contracts/fixtures/RulesetRegistry.build.json"))["runtime_sha256"])')
if [ "$ruleset_code_hash" != "$pinned_ruleset" ]; then
  echo "ruleset runtime bytecode $ruleset_code_hash does not match pinned $pinned_ruleset" >&2
  exit 1
fi

cd "$ROOT/contracts"
transfer_receipt=$("$FORGE" create src/TransferLog.sol:TransferLog \
  --rpc-url "$RPC" \
  --private-key "$DEPLOY_KEY" \
  --broadcast \
  --constructor-args "$DEPLOYER")
cd "$ROOT"
printf '%s\n' "$transfer_receipt"

transfer_address=$(printf '%s\n' "$transfer_receipt" | awk '/Deployed to:/ {print $3}')
transfer_tx=$(printf '%s\n' "$transfer_receipt" | awk '/Transaction hash:/ {print $3}')
if [ -z "$transfer_address" ] || [ -z "$transfer_tx" ]; then
  echo "forge create did not report a transfer log address" >&2
  exit 1
fi

transfer_code_hash=$(
  "$CAST" code "$transfer_address" --rpc-url "$RPC" | "$PY" -c '
import hashlib, sys
text = sys.stdin.read().strip().removeprefix("0x")
print(hashlib.sha256(bytes.fromhex(text)).hexdigest())
'
)
pinned_transfer=$("$PY" -c 'import json; print(json.load(open("contracts/fixtures/TransferLog.build.json"))["runtime_sha256"])')
if [ "$transfer_code_hash" != "$pinned_transfer" ]; then
  echo "transfer log runtime bytecode $transfer_code_hash does not match pinned $pinned_transfer" >&2
  exit 1
fi

cat > "$ROOT/.env.local" <<EOF
# Generated by make contract-deploy. Local Anvil only. This file is gitignored.
# Anvil sample keys are public insecure credentials and are not stored here.
VERITAS_CHAIN_RPC_URL=$RPC
VERITAS_CHAIN_ID=$CHAIN_ID
VERITAS_CONTRACT_ADDRESS=$address
VERITAS_DEPLOY_TX=$tx
VERITAS_CONTRACT_CODE_SHA256=$code_hash
VERITAS_RULESET_REGISTRY_ADDRESS=$ruleset_address
VERITAS_RULESET_DEPLOY_TX=$ruleset_tx
VERITAS_RULESET_REGISTRY_CODE_SHA256=$ruleset_code_hash
VERITAS_TRANSFER_LOG_ADDRESS=$transfer_address
VERITAS_TRANSFER_LOG_DEPLOY_TX=$transfer_tx
VERITAS_TRANSFER_LOG_CODE_SHA256=$transfer_code_hash
EOF

"$PY" - <<PY
from veritas.ledger.client import LedgerClient, LedgerConfig
config = LedgerConfig(
    rpc_url="$RPC",
    chain_id=$CHAIN_ID,
    contract_address="$address",
    runtime_code_sha256="$code_hash",
)
client = LedgerClient(config)
client.validate()
record = client.get_decision(bytes.fromhex("$key"[2:]))
assert record.exists
assert record.evidence_digest == bytes.fromhex("$digest"[2:])
print("decision-registry-client", record.sender, record.block_number)

from veritas.ledger.ruleset import RulesetClient
ruleset_config = LedgerConfig(
    rpc_url="$RPC",
    chain_id=$CHAIN_ID,
    contract_address="$ruleset_address",
    runtime_code_sha256="$ruleset_code_hash",
)
ruleset_client = RulesetClient(ruleset_config)
ruleset_client.validate()
print("ruleset-registry-client verified")
PY

"$PY" -m veritas.ledger.ruleset register \
  --manifest "$ROOT/docs/rulesets/rules-v1.json" \
  --rpc-url "$RPC" \
  --chain-id "$CHAIN_ID" \
  --contract-address "$ruleset_address"

echo "deployed decision registry $address tx $tx code $code_hash"
echo "deployed ruleset registry $ruleset_address tx $ruleset_tx code $ruleset_code_hash"
echo "deployed transfer log $transfer_address tx $transfer_tx code $transfer_code_hash"


