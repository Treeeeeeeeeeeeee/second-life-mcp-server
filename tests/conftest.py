"""
conftest.py — Shared pytest fixtures for lsl-mcp tests.

Builds an in-memory SQLite database pre-loaded with a small set of
representative fixtures so tests never depend on the real lsl.db or
network access.
"""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Fixture data ──────────────────────────────────────────────────────────────

FIXTURE_FUNCTIONS = [
    {
        "name": "llListen",
        "signature": "integer llListen(integer channel, string name, key id, string msg)",
        "return_type": "integer",
        "description": "Sets a listener for messages on the given channel.",
        "delay": 0.0,
        "energy": 10.0,
        "mono_only": False,
        "deprecated": False,
        "since_version": None,
        "parameters": [
            {"position": 0, "name": "channel", "type": "integer", "description": "Channel to listen on"},
            {"position": 1, "name": "name",    "type": "string",  "description": "Filter by speaker name"},
            {"position": 2, "name": "id",      "type": "key",     "description": "Filter by UUID"},
            {"position": 3, "name": "msg",     "type": "string",  "description": "Filter by message content"},
        ],
        "caveats": [
            "Counts against the 65 listen limit per script.",
            "Persists across state changes unless explicitly removed.",
        ],
        "examples": [],
        "related": ["llListenRemove", "llListenControl"],
    },
    {
        "name": "llReplaceSubString",
        "signature": "string llReplaceSubString(string src, string pattern, string replacement, integer count)",
        "return_type": "string",
        "description": "Replaces occurrences of pattern in src with replacement.",
        "delay": 0.0,
        "energy": 10.0,
        "mono_only": False,
        "deprecated": False,
        "since_version": None,
        "parameters": [
            {"position": 0, "name": "src",         "type": "string",  "description": "Source string"},
            {"position": 1, "name": "pattern",     "type": "string",  "description": "Pattern to replace"},
            {"position": 2, "name": "replacement", "type": "string",  "description": "Replacement string"},
            {"position": 3, "name": "count",       "type": "integer", "description": "Max replacements; 0 = all"},
        ],
        "caveats": [],
        "examples": [],
        "related": [],
    },
    {
        "name": "llSay",
        "signature": "llSay(integer channel, string message)",
        "return_type": "void",
        "description": "Says message on channel.",
        "delay": 0.0,
        "energy": 10.0,
        "mono_only": False,
        "deprecated": False,
        "since_version": None,
        "parameters": [
            {"position": 0, "name": "channel", "type": "integer", "description": "Channel"},
            {"position": 1, "name": "message", "type": "string",  "description": "Message text"},
        ],
        "caveats": [],
        "examples": [],
        "related": ["llShout", "llWhisper"],
    },
]

FIXTURE_EVENTS = [
    {
        "name": "listen",
        "signature": "listen(integer channel, string name, key id, string message)",
        "description": "Triggered when a listened message is received.",
        "since_version": None,
        "parameters": [
            {"position": 0, "name": "channel", "type": "integer", "description": "Channel"},
            {"position": 1, "name": "name",    "type": "string",  "description": "Speaker name"},
            {"position": 2, "name": "id",      "type": "key",     "description": "Speaker UUID"},
            {"position": 3, "name": "message", "type": "string",  "description": "Message content"},
        ],
    },
    {
        "name": "touch_start",
        "signature": "touch_start(integer num_detected)",
        "description": "Triggered when an avatar starts touching the object.",
        "since_version": None,
        "parameters": [
            {"position": 0, "name": "num_detected", "type": "integer", "description": "Number of touching agents"},
        ],
    },
    {
        "name": "state_entry",
        "signature": "state_entry()",
        "description": "Triggered on entering a state.",
        "since_version": None,
        "parameters": [],
    },
]

FIXTURE_CONSTANTS = [
    {"name": "NULL_KEY",   "type": "key",     "value": "00000000-0000-0000-0000-000000000000", "category": "string",      "description": "A null/empty key value."},
    {"name": "TRUE",       "type": "integer", "value": "1",                                    "category": "math",        "description": "Boolean true."},
    {"name": "FALSE",      "type": "integer", "value": "0",                                    "category": "math",        "description": "Boolean false."},
    {"name": "PUBLIC_CHANNEL", "type": "integer", "value": "0",                               "category": "channels",    "description": "The public chat channel."},
    {"name": "PERMISSION_TAKE_CONTROLS", "type": "integer", "value": "4",                     "category": "permissions", "description": "Permission to take controls."},
]

FIXTURE_PITFALLS = [
    {
        "id":           "lang_001",
        "category":     "reserved_words",
        "title":        "LSL type name used as variable name",
        "bad_example":  "key key = llGetOwner();",
        "good_example": "key owner = llGetOwner();",
        "notes":        "All primitive type names are reserved in LSL.",
        "ai_specific":  1,
        "portable_only": 1,
        "ai_source":    "kiro",
        "created_at":   "2026-01-01T00:00:00Z",
    },
    {
        "id":           "func_001",
        "category":     "nonexistent_functions",
        "title":        "llStringReplace does not exist in LSL",
        "bad_example":  "llStringReplace(src, old, new)",
        "good_example": "llReplaceSubString(src, pattern, replacement, count)",
        "notes":        "llStringReplace is a hallucination.",
        "ai_specific":  1,
        "portable_only": 1,
        "ai_source":    "kiro",
        "created_at":   "2026-01-01T00:00:00Z",
    },
    {
        "id":           "syn_001",
        "category":     "unsupported_syntax",
        "title":        "Ternary operator not supported in LSL",
        "bad_example":  "integer x = (a > 0) ? 1 : 0;",
        "good_example": "integer x;\nif (a > 0) x = 1;\nelse x = 0;",
        "notes":        "LSL has no ternary operator.",
        "ai_specific":  1,
        "portable_only": 1,
        "ai_source":    "both",
        "created_at":   "2026-01-01T00:00:00Z",
    },
    {
        "id":           "syn_002",
        "category":     "unsupported_syntax",
        "title":        "Switch statements not supported in LSL",
        "bad_example":  "switch(channel) { case 1: break; }",
        "good_example": "Use if/else if chains.",
        "notes":        "No switch in portable LSL.",
        "ai_specific":  1,
        "portable_only": 1,
        "ai_source":    "both",
        "created_at":   "2026-01-01T00:00:00Z",
    },
]


# ── DB builder ────────────────────────────────────────────────────────────────

def _build_test_db(con: sqlite3.Connection) -> None:
    schema = (ROOT / "db" / "schema.sql").read_text()
    con.executescript(schema)

    for f in FIXTURE_FUNCTIONS:
        con.execute(
            """
            INSERT INTO functions
                (name, signature, return_type, description, energy_cost, delay,
                 mono_only, deprecated, since_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f["name"], f["signature"], f["return_type"], f["description"],
                f.get("energy"), f.get("delay"),
                int(f.get("mono_only", False)), int(f.get("deprecated", False)),
                f.get("since_version"),
            ),
        )
        fid = con.execute(
            "SELECT id FROM functions WHERE name = ?", (f["name"],)
        ).fetchone()[0]

        for p in f.get("parameters", []):
            con.execute(
                "INSERT INTO function_parameters (function_id, position, name, type, description) VALUES (?,?,?,?,?)",
                (fid, p["position"], p["name"], p["type"], p.get("description")),
            )
        for c in f.get("caveats", []):
            con.execute(
                "INSERT INTO function_caveats (function_id, caveat) VALUES (?,?)", (fid, c)
            )
        for r in f.get("related", []):
            con.execute(
                "INSERT INTO function_related (function_id, related_name) VALUES (?,?)", (fid, r)
            )

    for e in FIXTURE_EVENTS:
        con.execute(
            "INSERT INTO events (name, signature, description, since_version) VALUES (?,?,?,?)",
            (e["name"], e["signature"], e["description"], e.get("since_version")),
        )
        eid = con.execute(
            "SELECT id FROM events WHERE name = ?", (e["name"],)
        ).fetchone()[0]
        for p in e.get("parameters", []):
            con.execute(
                "INSERT INTO event_parameters (event_id, position, name, type, description) VALUES (?,?,?,?,?)",
                (eid, p["position"], p["name"], p["type"], p.get("description")),
            )

    for c in FIXTURE_CONSTANTS:
        con.execute(
            "INSERT INTO constants (name, type, value, category, description, deprecated) VALUES (?,?,?,?,?,?)",
            (c["name"], c["type"], c["value"], c.get("category"), c.get("description"), 0),
        )

    for p in FIXTURE_PITFALLS:
        con.execute(
            """
            INSERT INTO pitfalls
                (id, category, title, bad_example, good_example, notes,
                 ai_specific, portable_only, ai_source, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                p["id"], p["category"], p["title"], p["bad_example"],
                p["good_example"], p["notes"], p["ai_specific"],
                p["portable_only"], p["ai_source"], p["created_at"],
            ),
        )

    con.commit()


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory) -> Path:
    """
    Build a temporary SQLite database from schema + fixtures.
    Scoped to the session so it is created once and shared across all tests.
    """
    db_path = tmp_path_factory.mktemp("db") / "lsl_test.db"
    con = sqlite3.connect(db_path)
    con.execute("PRAGMA foreign_keys=ON")
    _build_test_db(con)
    con.close()
    return db_path


@pytest.fixture(autouse=True)
def patch_db_path(test_db_path, monkeypatch):
    """
    Redirect all DB_PATH references in tool modules to the test database.
    Applied automatically to every test.
    """
    monkeypatch.setattr("tools.lookup.DB_PATH",    test_db_path)
    monkeypatch.setattr("tools.pitfalls.DB_PATH",  test_db_path)
    monkeypatch.setattr("tools.reference.DB_PATH", test_db_path)
