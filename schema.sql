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

-- ── Agency tables ──────────────────────────────────────────────────────────

-- Agency profiles
CREATE TABLE IF NOT EXISTS agencies (
    agency_id   TEXT PRIMARY KEY,
    name        TEXT,
    ein         TEXT,
    contact_email TEXT,
    owner_email TEXT,
    platforms   JSONB DEFAULT '[]'::jsonb,
    estimated_volume TEXT,
    stripe_connect_account TEXT,
    status      TEXT DEFAULT 'active',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Agency creator roster
CREATE TABLE IF NOT EXISTS agency_creators (
    id          TEXT PRIMARY KEY,
    agency_id   TEXT,
    creator_name TEXT,
    creator_email TEXT,
    platform    TEXT,
    split_percentage NUMERIC DEFAULT 80,
    status      TEXT DEFAULT 'invited',
    stripe_account_id TEXT,
    monthly_volume NUMERIC DEFAULT 0,
    total_volume NUMERIC DEFAULT 0,
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- Payout history
CREATE TABLE IF NOT EXISTS agency_payouts (
    payout_id   TEXT PRIMARY KEY,
    agency_id   TEXT,
    timestamp   TIMESTAMPTZ DEFAULT now(),
    method      TEXT DEFAULT 'ach',
    total_gross NUMERIC,
    total_agency_cut NUMERIC,
    total_processing_fee NUMERIC,
    total_net   NUMERIC,
    creator_payouts JSONB DEFAULT '[]'::jsonb,
    status      TEXT DEFAULT 'completed'
);

CREATE INDEX IF NOT EXISTS idx_agency_creators_agency ON agency_creators(agency_id);
CREATE INDEX IF NOT EXISTS idx_agency_payouts_agency ON agency_payouts(agency_id);
