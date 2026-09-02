-- app/database/schema.sql

CREATE TABLE IF NOT EXISTS agent_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payer_agent_id TEXT NOT NULL,
    x402_transaction_hash TEXT UNIQUE NOT NULL,
    amount_paid_usdc REAL NOT NULL,
    skill_requested TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_verified BOOLEAN DEFAULT FALSE
);