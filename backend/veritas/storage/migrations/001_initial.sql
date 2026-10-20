CREATE TABLE IF NOT EXISTS banks (
    bank_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    bank_id TEXT NOT NULL REFERENCES banks (bank_id),
    opened_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_id TEXT PRIMARY KEY,
    from_account_id TEXT NOT NULL REFERENCES accounts (account_id),
    to_account_id TEXT NOT NULL REFERENCES accounts (account_id),
    amount_minor INTEGER NOT NULL CHECK (amount_minor > 0),
    event_time TEXT NOT NULL,
    currency TEXT NOT NULL CHECK (currency = 'USD'),
    scenario_id TEXT,
    CHECK (from_account_id <> to_account_id)
);

CREATE INDEX IF NOT EXISTS idx_transactions_event_time
    ON transactions (event_time, transaction_id);

CREATE TABLE IF NOT EXISTS scenario_ground_truth (
    ground_truth_id TEXT PRIMARY KEY,
    scenario_id TEXT NOT NULL,
    transaction_id TEXT REFERENCES transactions (transaction_id),
    account_id TEXT REFERENCES accounts (account_id),
    label TEXT NOT NULL,
    CHECK (transaction_id IS NOT NULL OR account_id IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS dataset_manifest (
    manifest_id INTEGER PRIMARY KEY CHECK (manifest_id = 1),
    seed INTEGER NOT NULL,
    scale TEXT NOT NULL,
    account_count INTEGER NOT NULL,
    transaction_count INTEGER NOT NULL,
    content_sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_snapshots (
    snapshot_id TEXT PRIMARY KEY,
    transaction_id TEXT NOT NULL REFERENCES transactions (transaction_id),
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    digest_hex TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    decision_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    transaction_id TEXT NOT NULL REFERENCES transactions (transaction_id),
    risk_score INTEGER NOT NULL,
    decision_category TEXT NOT NULL,
    reason_codes TEXT NOT NULL,
    model_version TEXT NOT NULL,
    ruleset_version TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evidence_receipts (
    decision_id TEXT PRIMARY KEY REFERENCES decisions (decision_id),
    canonical_text TEXT NOT NULL,
    digest_hex TEXT NOT NULL,
    signature_b64 TEXT NOT NULL,
    signing_key_id TEXT NOT NULL,
    signature_algorithm TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS anchor_outbox (
    job_id TEXT PRIMARY KEY,
    decision_id TEXT NOT NULL UNIQUE REFERENCES decisions (decision_id),
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL,
    next_retry_at TEXT,
    submitted_tx_hash TEXT,
    block_number INTEGER,
    error_category TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chain_config (
    config_id INTEGER PRIMARY KEY CHECK (config_id = 1),
    chain_id INTEGER,
    registry_address TEXT,
    deployment_tx_hash TEXT,
    signer_allowlist_json TEXT
);
