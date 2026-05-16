"""
tools/reference.py — Event and constant reference tools for the LSL MCP server.

Tools exposed:
    lsl_list_events(name?)        Return all valid LSL events, or look up one by name.
    lsl_constants(category?)      Return LSL constants, optionally filtered by category.
"""

import sqlite3
from pathlib import Path

# ── DB connection ─────────────────────────────────────────────────────────────

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "db" / "lsl.db"


def _connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise RuntimeError(
            f"Database not found at {DB_PATH}. "
            "Run scripts/scrape_wiki.py then scripts/load_db.py first."
        )
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


# ── Hydration ─────────────────────────────────────────────────────────────────

def _hydrate_event(con: sqlite3.Connection, row: sqlite3.Row) -> dict:
    params = con.execute(
        """
        SELECT position, name, type, description
        FROM event_parameters
        WHERE event_id = ?
        ORDER BY position
        """,
        (row["id"],),
    ).fetchall()

    return {
        "name":          row["name"],
        "signature":     row["signature"],
        "description":   row["description"],
        "since_version": row["since_version"],
        "parameters": [
            {
                "position":    p["position"],
                "name":        p["name"],
                "type":        p["type"],
                "description": p["description"],
            }
            for p in params
        ],
    }


# ── Tools ─────────────────────────────────────────────────────────────────────

def lsl_list_events(name: str | None = None) -> dict:
    """
    Return valid LSL event signatures.

    Events are the entry points of LSL scripts (state_entry, touch_start,
    listen, timer, etc.). AI tools sometimes invent event names that do not
    exist — use this tool to verify an event name before using it.

    Args:
        name: Optional event name to look up exactly, e.g. "listen" or
              "touch_start". Omit to return all events.

    Returns:
        If name provided:
            Single event record with keys: name, signature, description,
            since_version, parameters.
            On miss: {"error": str, "valid_events": list[str]}
        If name omitted:
            {"count": int, "events": list of {name, signature, description}}
    """
    con = _connect()

    if name:
        # Exact match first, then case-insensitive
        row = con.execute(
            "SELECT * FROM events WHERE lower(name) = lower(?)", (name,)
        ).fetchone()

        if not row:
            # Substring fallback
            row = con.execute(
                "SELECT * FROM events WHERE lower(name) LIKE lower(?)",
                (f"%{name}%",),
            ).fetchone()

        if not row:
            all_names = con.execute(
                "SELECT name FROM events ORDER BY name"
            ).fetchall()
            return {
                "error": f"No LSL event found matching '{name}'.",
                "valid_events": [r["name"] for r in all_names],
            }

        return _hydrate_event(con, row)

    # Return all events — summary only (no parameters)
    rows = con.execute(
        "SELECT * FROM events ORDER BY name"
    ).fetchall()

    return {
        "count": len(rows),
        "events": [
            {
                "name":        r["name"],
                "signature":   r["signature"],
                "description": r["description"],
            }
            for r in rows
        ],
    }


# ── Constants ─────────────────────────────────────────────────────────────────

# Canonical category list — used for validation and discovery
CONSTANT_CATEGORIES = [
    "agent_info",
    "attach_points",
    "camera",
    "channels",
    "chat",
    "click_action",
    "controls",
    "dataserver",
    "http",
    "inventory",
    "link",
    "list",
    "math",
    "object",
    "parcel",
    "permissions",
    "prim_params",
    "region",
    "sensor",
    "sound",
    "status",
    "string",
    "texture",
    "vehicle",
]


def lsl_constants(category: str | None = None, name: str | None = None) -> dict:
    """
    Return LSL constants, optionally filtered by category or looked up by name.

    Args:
        category: Optional category filter. Call lsl_constants() with no args
                  to see the list of valid categories in the response.
        name:     Optional exact constant name to look up, e.g. "NULL_KEY" or
                  "PERMISSION_TAKE_CONTROLS". Takes precedence over category.

    Returns:
        If name provided:
            Single constant record: {name, type, value, category, description, deprecated}
            On miss: {"error": str, "did_you_mean": list[str]}
        If category provided:
            {"category": str, "count": int, "constants": list of records}
        If neither:
            {"categories": list[str], "total": int,
             "constants": list of all records}
    """
    con = _connect()

    # ── Single constant lookup ────────────────────────────────────────────────
    if name:
        row = con.execute(
            "SELECT * FROM constants WHERE lower(name) = lower(?)", (name,)
        ).fetchone()

        if not row:
            # Substring fallback
            suggestions = con.execute(
                """
                SELECT name FROM constants
                WHERE lower(name) LIKE lower(?)
                ORDER BY name
                LIMIT 8
                """,
                (f"%{name}%",),
            ).fetchall()
            return {
                "error": f"No LSL constant found matching '{name}'.",
                "did_you_mean": [s["name"] for s in suggestions],
            }

        return {
            "name":        row["name"],
            "type":        row["type"],
            "value":       row["value"],
            "category":    row["category"],
            "description": row["description"],
            "deprecated":  bool(row["deprecated"]),
        }

    # ── Category filter ───────────────────────────────────────────────────────
    if category:
        if category not in CONSTANT_CATEGORIES:
            return {
                "error": f"Unknown category '{category}'.",
                "valid_categories": CONSTANT_CATEGORIES,
            }

        rows = con.execute(
            """
            SELECT name, type, value, category, description, deprecated
            FROM constants
            WHERE category = ?
            ORDER BY name
            """,
            (category,),
        ).fetchall()

        return {
            "category":  category,
            "count":     len(rows),
            "constants": [
                {
                    "name":        r["name"],
                    "type":        r["type"],
                    "value":       r["value"],
                    "description": r["description"],
                    "deprecated":  bool(r["deprecated"]),
                }
                for r in rows
            ],
        }

    # ── All constants ─────────────────────────────────────────────────────────
    rows = con.execute(
        """
        SELECT name, type, value, category, description, deprecated
        FROM constants
        ORDER BY category, name
        """,
    ).fetchall()

    # Summarise by category for the response header
    category_counts: dict[str, int] = {}
    for r in rows:
        cat = r["category"] or "uncategorised"
        category_counts[cat] = category_counts.get(cat, 0) + 1

    return {
        "total":      len(rows),
        "categories": category_counts,
        "constants": [
            {
                "name":        r["name"],
                "type":        r["type"],
                "value":       r["value"],
                "category":    r["category"],
                "description": r["description"],
                "deprecated":  bool(r["deprecated"]),
            }
            for r in rows
        ],
    }
