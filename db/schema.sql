-- LSL MCP Database Schema
-- Portable LSL only (no Firestorm-specific syntax)

PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ─────────────────────────────────────────
-- Functions
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS functions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    signature       TEXT NOT NULL,
    return_type     TEXT NOT NULL,
    description     TEXT,
    energy_cost     REAL,
    delay           REAL,       -- seconds
    mono_only       INTEGER NOT NULL DEFAULT 0,  -- boolean
    deprecated      INTEGER NOT NULL DEFAULT 0,  -- boolean
    since_version   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS function_parameters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    function_id     INTEGER NOT NULL REFERENCES functions(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,  -- 0-indexed parameter order
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,
    description     TEXT
);

CREATE TABLE IF NOT EXISTS function_caveats (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    function_id     INTEGER NOT NULL REFERENCES functions(id) ON DELETE CASCADE,
    caveat          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS function_examples (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    function_id     INTEGER NOT NULL REFERENCES functions(id) ON DELETE CASCADE,
    example         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS function_related (
    function_id     INTEGER NOT NULL REFERENCES functions(id) ON DELETE CASCADE,
    related_name    TEXT NOT NULL,  -- name only, not FK, wiki may reference nonexistent
    PRIMARY KEY (function_id, related_name)
);

-- Permissions some functions require via llRequestPermissions
CREATE TABLE IF NOT EXISTS function_permissions (
    function_id     INTEGER NOT NULL REFERENCES functions(id) ON DELETE CASCADE,
    permission      TEXT NOT NULL,  -- e.g. PERMISSION_TAKE_CONTROLS
    PRIMARY KEY (function_id, permission)
);

-- Where a function can be used
CREATE TABLE IF NOT EXISTS function_scope (
    function_id     INTEGER NOT NULL REFERENCES functions(id) ON DELETE CASCADE,
    scope           TEXT NOT NULL,  -- 'object', 'attachment', 'hud', 'npc', 'no_script_parcel'
    allowed         INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (function_id, scope)
);

-- ─────────────────────────────────────────
-- Events
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    signature       TEXT NOT NULL,
    description     TEXT,
    since_version   TEXT
);

CREATE TABLE IF NOT EXISTS event_parameters (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        INTEGER NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL,
    description     TEXT
);

-- ─────────────────────────────────────────
-- Constants
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS constants (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    type            TEXT NOT NULL,
    value           TEXT NOT NULL,
    category        TEXT,           -- e.g. 'permissions', 'prim_params', 'agent_info'
    description     TEXT,
    deprecated      INTEGER NOT NULL DEFAULT 0
);

-- ─────────────────────────────────────────
-- Language Pitfalls
-- ─────────────────────────────────────────

CREATE TABLE IF NOT EXISTS pitfalls (
    id              TEXT PRIMARY KEY,   -- e.g. 'lang_001', 'func_001', 'syn_001'
    category        TEXT NOT NULL,      -- reserved_words | nonexistent_functions | unsupported_syntax | scoping | type_coercion | state_behavior
    title           TEXT NOT NULL,
    bad_example     TEXT,
    good_example    TEXT,
    notes           TEXT,
    ai_specific     INTEGER NOT NULL DEFAULT 1,
    portable_only   INTEGER NOT NULL DEFAULT 1,
    ai_source       TEXT,               -- 'kiro' | 'claude-code' | 'both' | null
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────
-- Full-text search
-- ─────────────────────────────────────────

CREATE VIRTUAL TABLE IF NOT EXISTS functions_fts USING fts5(
    name,
    description,
    content='functions',
    content_rowid='id'
);

CREATE VIRTUAL TABLE IF NOT EXISTS pitfalls_fts USING fts5(
    title,
    notes,
    bad_example,
    content='pitfalls',
    content_rowid='rowid'
);

-- Keep FTS in sync
CREATE TRIGGER IF NOT EXISTS functions_ai AFTER INSERT ON functions BEGIN
    INSERT INTO functions_fts(rowid, name, description)
    VALUES (new.id, new.name, new.description);
END;

CREATE TRIGGER IF NOT EXISTS functions_au AFTER UPDATE ON functions BEGIN
    INSERT INTO functions_fts(functions_fts, rowid, name, description)
    VALUES ('delete', old.id, old.name, old.description);
    INSERT INTO functions_fts(rowid, name, description)
    VALUES (new.id, new.name, new.description);
END;

CREATE TRIGGER IF NOT EXISTS functions_ad AFTER DELETE ON functions BEGIN
    INSERT INTO functions_fts(functions_fts, rowid, name, description)
    VALUES ('delete', old.id, old.name, old.description);
END;

-- ─────────────────────────────────────────
-- Indexes
-- ─────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_functions_name       ON functions(name);
CREATE INDEX IF NOT EXISTS idx_constants_category   ON constants(category);
CREATE INDEX IF NOT EXISTS idx_pitfalls_category    ON pitfalls(category);
CREATE INDEX IF NOT EXISTS idx_pitfalls_ai_source   ON pitfalls(ai_source);
CREATE INDEX IF NOT EXISTS idx_func_params_func     ON function_parameters(function_id);
