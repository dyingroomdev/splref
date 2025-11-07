-- SQLite schema -----------------------------------------------------------
BEGIN;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NULL,
    first_name TEXT NULL,
    last_name TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS affiliates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_user_id INTEGER NOT NULL,
    invite_link TEXT NOT NULL UNIQUE,
    link_code TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_affiliates_owner FOREIGN KEY (owner_user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT uq_affiliates_owner UNIQUE (owner_user_id)
);

CREATE TABLE IF NOT EXISTS attributions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    joined_user_id INTEGER NOT NULL,
    affiliate_id INTEGER NOT NULL,
    joined_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at TIMESTAMP NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'revoked')),
    note TEXT NULL,
    last_seen_ip TEXT NULL,
    source_subnet TEXT NULL,
    CONSTRAINT fk_attributions_joined_user FOREIGN KEY (joined_user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_attributions_affiliate FOREIGN KEY (affiliate_id) REFERENCES affiliates (id) ON DELETE CASCADE,
    CONSTRAINT uq_attributions_joined_user UNIQUE (joined_user_id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK (type IN ('join', 'leave', 'promote', 'revoke')),
    user_id INTEGER NOT NULL,
    affiliate_id INTEGER NULL,
    raw JSON NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_events_user FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    CONSTRAINT fk_events_affiliate FOREIGN KEY (affiliate_id) REFERENCES affiliates (id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_affiliates_owner_user_id ON affiliates (owner_user_id);
CREATE INDEX IF NOT EXISTS idx_attributions_affiliate_id ON attributions (affiliate_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_attributions_joined_user_id ON attributions (joined_user_id);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events (user_id);
CREATE INDEX IF NOT EXISTS idx_events_affiliate_id ON events (affiliate_id);

COMMIT;


-- PostgreSQL schema -------------------------------------------------------
BEGIN;

DO $block$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'attribution_status') THEN
        CREATE TYPE attribution_status AS ENUM ('pending', 'verified', 'revoked');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'event_type') THEN
        CREATE TYPE event_type AS ENUM ('join', 'leave', 'promote', 'revoke');
    END IF;
END;
$block$;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT NULL,
    first_name TEXT NULL,
    last_name TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS affiliates (
    id BIGSERIAL PRIMARY KEY,
    owner_user_id BIGINT NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
    invite_link TEXT NOT NULL UNIQUE,
    link_code TEXT NOT NULL UNIQUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS attributions (
    id BIGSERIAL PRIMARY KEY,
    joined_user_id BIGINT NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
    affiliate_id BIGINT NOT NULL REFERENCES affiliates (id) ON DELETE CASCADE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    verified_at TIMESTAMPTZ NULL,
    status attribution_status NOT NULL DEFAULT 'pending',
    note VARCHAR(255) NULL,
    last_seen_ip VARCHAR(45) NULL,
    source_subnet VARCHAR(64) NULL
);

CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    type event_type NOT NULL,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    affiliate_id BIGINT NULL REFERENCES affiliates (id) ON DELETE SET NULL,
    raw JSONB NOT NULL DEFAULT '{}'::JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_affiliates_owner_user_id ON affiliates (owner_user_id);
CREATE INDEX IF NOT EXISTS idx_attributions_affiliate_id ON attributions (affiliate_id);
CREATE INDEX IF NOT EXISTS idx_events_user_id ON events (user_id);
CREATE INDEX IF NOT EXISTS idx_events_affiliate_id ON events (affiliate_id);

COMMIT;
