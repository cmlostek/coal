-- Coal Discord Bot — Supabase (PostgreSQL) Schema
-- Upload this file via: Supabase Dashboard → SQL Editor → paste & run

-- ─────────────────────────────────────────────
-- death_log
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS death_log (
    log_id  SERIAL PRIMARY KEY,
    id      TEXT,           -- Discord user ID (or '0' for anonymous)
    cntr    INTEGER,        -- Sequential death number
    reason  TEXT            -- Cause of death (nullable)
);

-- ─────────────────────────────────────────────
-- balances  (economy system)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS balances (
    user_id    BIGINT PRIMARY KEY,         -- Discord user snowflake
    balance    INTEGER DEFAULT 1000,
    last_daily TEXT    DEFAULT NULL,       -- 'YYYY-MM-DD'
    last_work  TEXT    DEFAULT NULL        -- 'YYYY-MM-DD HH:MM:SS.ffffff'
);

-- ─────────────────────────────────────────────
-- levels  (XP system)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS levels (
    id     BIGINT  PRIMARY KEY,            -- Discord user snowflake
    level  INTEGER DEFAULT 1,
    xp     INTEGER DEFAULT 0
);

-- ─────────────────────────────────────────────
-- reminders
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS reminders (
    id          TEXT    PRIMARY KEY,       -- 8-char hex token, e.g. 'A3F891C2'
    user_id     BIGINT  NOT NULL,
    channel_id  BIGINT  NOT NULL,
    remind_at   TEXT    NOT NULL,          -- ISO-8601 UTC datetime string
    message     TEXT    NOT NULL
);

-- ─────────────────────────────────────────────
-- user_stats  (message + voice tracking)
-- ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS user_stats (
    user_id       BIGINT  NOT NULL,
    guild_id      BIGINT  NOT NULL,
    messages_sent INTEGER DEFAULT 0,
    voice_seconds INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
);
