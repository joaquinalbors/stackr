-- Apexa Supabase schema
-- Run this in the Supabase SQL editor to create the required tables.

-- Users table
CREATE TABLE IF NOT EXISTS users (
    email       TEXT PRIMARY KEY,
    name        TEXT,
    password_hash TEXT,
    acct_type   TEXT DEFAULT 'creator',
    plan        TEXT DEFAULT 'free',
    tier        TEXT DEFAULT 'free',
    stripe_customer_id TEXT,
    api_keys    JSONB DEFAULT '[]'::jsonb,
    created_at  TIMESTAMPTZ DEFAULT now(),
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Auto-update updated_at on row changes
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS users_updated_at ON users;
CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- Plaid access tokens
CREATE TABLE IF NOT EXISTS plaid_tokens (
    user_id      TEXT PRIMARY KEY,
    access_token TEXT,          -- encrypted at the application layer
    item_id      TEXT,
    institution  TEXT,
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_stripe_customer ON users(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_plaid_tokens_item ON plaid_tokens(item_id);
