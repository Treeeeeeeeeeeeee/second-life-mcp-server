"""
tools/lookup.py — Function lookup and search tools for the LSL MCP server.

Tools exposed:
    lsl_lookup_function(name)   Exact or fuzzy match on function name.
    lsl_search(query)           Full-text search across functions.
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

def _hydrate_function(con: sqlite3.Connection, row: sqlite3.Row) -> dict:
    """
    Given a functions row, fetch all child records and return a complete dict.
    """
    fid = row["id"]

    params = con.execute(
        """
        SELECT position, name, type, description
        FROM function_parameters
        WHERE function_id = ?
        ORDER BY position
        """,
        (fid,),
    ).fetchall()

    caveats = con.execute(
        "SELECT caveat FROM function_caveats WHERE function_id = ?", (fid,)
    ).fetchall()

    examples = con.execute(
        "SELECT example FROM function_examples WHERE function_id = ?", (fid,)
    ).fetchall()

    related = con.execute(
        "SELECT related_name FROM function_related WHERE function_id = ?", (fid,)
    ).fetchall()

    permissions = con.execute(
        "SELECT permission FROM function_permissions WHERE function_id = ?", (fid,)
    ).fetchall()

    scope = con.execute(
        "SELECT scope, allowed FROM function_scope WHERE function_id = ?", (fid,)
    ).fetchall()

    pitfalls = con.execute(
        """
        SELECT id, category, title, bad_example, good_example, notes, ai_source
        FROM pitfalls
        WHERE category = 'nonexistent_functions'
           OR (bad_example LIKE '%' || ? || '%')
        """,
        (row["name"],),
    ).fetchall()

    return {
        "name":          row["name"],
        "signature":     row["signature"],
        "return_type":   row["return_type"],
        "description":   row["description"],
        "delay":         row["delay"],
        "energy_cost":   row["energy_cost"],
        "mono_only":     bool(row["mono_only"]),
        "deprecated":    bool(row["deprecated"]),
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
        "caveats":              [c["caveat"] for c in caveats],
        "examples":             [e["example"] for e in examples],
        "related":              [r["related_name"] for r in related],
        "permissions_required": [p["permission"] for p in permissions],
        "scope":                [{"scope": s["scope"], "allowed": bool(s["allowed"])} for s in scope],
        "known_ai_pitfalls": [
            {
                "id":          p["id"],
                "category":    p["category"],
                "title":       p["title"],
                "bad_example": p["bad_example"],
                "good_example": p["good_example"],
                "notes":       p["notes"],
                "ai_source":   p["ai_source"],
            }
            for p in pitfalls
        ],
    }


# ── Tools ─────────────────────────────────────────────────────────────────────

def lsl_lookup_function(name: str) -> dict:
    """
    Look up an LSL function by name.

    Tries an exact match first, then falls back to a case-insensitive prefix
    match, then a LIKE search. Returns the full function record including
    parameters, caveats, examples, related functions, and any known AI pitfalls
    associated with this function.

    If the name does not match any real LSL function, returns an error dict
    with a 'did_you_mean' list of close matches.

    Args:
        name: The function name to look up, e.g. "llListen" or "lllisten".

    Returns:
        dict with keys: name, signature, return_type, description, parameters,
        delay, energy_cost, mono_only, deprecated, caveats, examples, related,
        permissions_required, scope, known_ai_pitfalls.
        On failure: {"error": str, "did_you_mean": list[str]}
    """
    con = _connect()

    # 1. Exact match (case-insensitive)
    row = con.execute(
        "SELECT * FROM functions WHERE lower(name) = lower(?)", (name,)
    ).fetchone()

    # 2. Prefix match
    if not row:
        row = con.execute(
            "SELECT * FROM functions WHERE lower(name) LIKE lower(?)",
            (name.rstrip("%") + "%",),
        ).fetchone()

    # 3. Substring match
    if not row:
        row = con.execute(
            "SELECT * FROM functions WHERE lower(name) LIKE lower(?)",
            (f"%{name}%",),
        ).fetchone()

    if not row:
        # Suggest close matches via FTS
        suggestions = con.execute(
            "SELECT name FROM functions_fts WHERE name MATCH ? LIMIT 5",
            (name,),
        ).fetchall()
        return {
            "error": f"No LSL function found matching '{name}'.",
            "did_you_mean": [s["name"] for s in suggestions],
        }

    return _hydrate_function(con, row)


def lsl_search(query: str, limit: int = 10) -> dict:
    """
    Full-text search across LSL function names and descriptions.

    Useful when you know roughly what a function does but not its exact name.
    Returns a ranked list of matches with name, signature, and a description
    excerpt — not full records. Use lsl_lookup_function for the full record.

    Args:
        query: Natural language or keyword query, e.g. "listen channel message"
               or "set prim texture".
        limit: Maximum number of results to return (default 10, max 25).

    Returns:
        dict with key "results": list of {name, signature, description, rank}
    """
    limit = min(limit, 25)
    con   = _connect()

    rows = con.execute(
        """
        SELECT
            f.name,
            f.signature,
            f.description,
            f.deprecated,
            fts.rank
        FROM functions_fts fts
        JOIN functions f ON f.id = fts.rowid
        WHERE functions_fts MATCH ?
        ORDER BY fts.rank
        LIMIT ?
        """,
        (query, limit),
    ).fetchall()

    # Fallback: LIKE search on name if FTS returns nothing
    if not rows:
        rows = con.execute(
            """
            SELECT name, signature, description, deprecated, 0 AS rank
            FROM functions
            WHERE lower(name) LIKE lower(?)
               OR lower(description) LIKE lower(?)
            LIMIT ?
            """,
            (f"%{query}%", f"%{query}%", limit),
        ).fetchall()

    return {
        "query":   query,
        "count":   len(rows),
        "results": [
            {
                "name":        r["name"],
                "signature":   r["signature"],
                "description": (r["description"] or "")[:200],  # excerpt only
                "deprecated":  bool(r["deprecated"]),
            }
            for r in rows
        ],
    }
