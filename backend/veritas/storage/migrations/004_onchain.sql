CREATE TABLE IF NOT EXISTS onchain_cursor (
    cursor_id INTEGER PRIMARY KEY CHECK (cursor_id = 1),
    chain_id INTEGER NOT NULL,
    contract_address TEXT NOT NULL,
    last_block_number INTEGER NOT NULL,
    last_block_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS onchain_transfer_refs (
    transaction_id TEXT PRIMARY KEY REFERENCES transactions (transaction_id),
    chain_id INTEGER NOT NULL,
    block_number INTEGER NOT NULL,
    block_hash TEXT NOT NULL,
    tx_hash TEXT NOT NULL,
    log_index INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
