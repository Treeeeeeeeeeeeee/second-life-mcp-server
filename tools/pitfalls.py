"""
tools/pitfalls.py — Pitfall query and code checking tools for the LSL MCP server.

Tools exposed:
    lsl_get_pitfalls(category?)   Return pitfall entries, optionally filtered.
    lsl_check_code(code)          Scan a code snippet for known pitfalls.
"""

import re
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


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id":           row["id"],
        "category":     row["category"],
        "title":        row["title"],
        "bad_example":  row["bad_example"],
        "good_example": row["good_example"],
        "notes":        row["notes"],
        "ai_specific":  bool(row["ai_specific"]),
        "portable_only": bool(row["portable_only"]),
        "ai_source":    row["ai_source"],
        "created_at":   row["created_at"],
    }


# ── Tools ─────────────────────────────────────────────────────────────────────

VALID_CATEGORIES = {
    "reserved_words",
    "nonexistent_functions",
    "unsupported_syntax",
    "scoping",
    "type_coercion",
    "state_behavior",
}


def lsl_get_pitfalls(category: str | None = None, ai_source: str | None = None) -> dict:
    """
    Return known LSL pitfalls for AI coding assistants.

    Call with no arguments to get all pitfalls. Filter by category or by
    which AI tool produced the mistake.

    Args:
        category:  One of: reserved_words, nonexistent_functions,
                   unsupported_syntax, scoping, type_coercion, state_behavior.
                   Omit to return all categories.
        ai_source: One of: kiro, claude-code, both.
                   Omit to return pitfalls from all sources.

    Returns:
        dict with keys:
            count    — number of pitfalls returned
            filters  — the filters that were applied
            pitfalls — list of pitfall records
    """
    if category and category not in VALID_CATEGORIES:
        return {
            "error": f"Unknown category '{category}'.",
            "valid_categories": sorted(VALID_CATEGORIES),
        }

    con    = _connect()
    query  = "SELECT * FROM pitfalls WHERE 1=1"
    params: list = []

    if category:
        query += " AND category = ?"
        params.append(category)

    if ai_source:
        query += " AND (ai_source = ? OR ai_source = 'both')"
        params.append(ai_source)

    query += " ORDER BY category, id"

    rows = con.execute(query, params).fetchall()

    return {
        "count":   len(rows),
        "filters": {"category": category, "ai_source": ai_source},
        "pitfalls": [_row_to_dict(r) for r in rows],
    }


# ── Code checker ──────────────────────────────────────────────────────────────

# Patterns that detect each pitfall category in raw LSL source.
# Each entry: (pitfall_id, compiled_regex, human-readable match description)
# These are supplemented at runtime with DB entries that have bad_example set.

_STATIC_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # Ternary operator
    (
        "syn_001",
        re.compile(r"\?\s*\S+\s*:", re.S),
        "Ternary operator `? :` detected — not supported in LSL",
    ),
    # Switch statement
    (
        "syn_002",
        re.compile(r"\bswitch\s*\(", re.S),
        "`switch` statement detected — not supported in portable LSL",
    ),
    # Type names used as variable names (declaration pattern)
    (
        "lang_001",
        re.compile(
            r"\b(integer|float|string|key|vector|rotation|list)\s+"
            r"(integer|float|string|key|vector|rotation|list)\s*[=;,\)]",
            re.S,
        ),
        "LSL type name used as variable name — type names are reserved identifiers",
    ),
]

# Nonexistent functions we know about — built from DB at check time
_KNOWN_FAKE_FUNCTIONS = [
    "llStringReplace",
    # expanded at runtime from pitfalls table
]


def lsl_check_code(code: str) -> dict:
    """
    Scan an LSL code snippet for known AI-generated pitfalls.

    Checks for:
      - Nonexistent function calls
      - Unsupported syntax (ternary operators, switch statements)
      - Reserved words used as variable names
      - Other patterns from the pitfalls database

    Does NOT perform full LSL compilation or type checking — use the
    in-world script editor for that. This tool catches the specific class
    of mistakes AI tools commonly make.

    Args:
        code: Raw LSL source code as a string.

    Returns:
        dict with keys:
            clean    — True if no issues found
            issues   — list of detected issues, each with:
                           pitfall_id, category, title, line, match, suggestion
    """
    if not code or not code.strip():
        return {"clean": True, "issues": [], "note": "Empty input."}

    con    = _connect()
    issues = []
    lines  = code.splitlines()

    # ── 1. Nonexistent function calls ────────────────────────────────────────

    # Pull all nonexistent_functions pitfalls from DB
    fake_rows = con.execute(
        "SELECT * FROM pitfalls WHERE category = 'nonexistent_functions'"
    ).fetchall()

    fake_functions: dict[str, sqlite3.Row] = {}
    for row in fake_rows:
        # Extract function name from bad_example if present
        if row["bad_example"]:
            m = re.match(r"(ll\w+|os\w+)", row["bad_example"])
            if m:
                fake_functions[m.group(1)] = row

    # Also include static list
    for fname in _KNOWN_FAKE_FUNCTIONS:
        if fname not in fake_functions:
            fake_functions[fname] = None  # no DB row, bare detection

    for fname, pitfall_row in fake_functions.items():
        pattern = re.compile(rf"\b{re.escape(fname)}\s*\(")
        for lineno, line in enumerate(lines, 1):
            if pattern.search(line):
                issues.append({
                    "pitfall_id": pitfall_row["id"] if pitfall_row else "func_unknown",
                    "category":   "nonexistent_functions",
                    "title":      f"`{fname}` does not exist in LSL",
                    "line":       lineno,
                    "match":      line.strip(),
                    "suggestion": pitfall_row["good_example"] if pitfall_row else
                                  f"Check the LSL wiki — `{fname}` has no equivalent.",
                })

    # ── 2. Static syntax patterns ─────────────────────────────────────────────

    for pitfall_id, pattern, description in _STATIC_PATTERNS:
        # Fetch the DB row for richer output
        db_row = con.execute(
            "SELECT * FROM pitfalls WHERE id = ?", (pitfall_id,)
        ).fetchone()

        for lineno, line in enumerate(lines, 1):
            if pattern.search(line):
                issues.append({
                    "pitfall_id": pitfall_id,
                    "category":   db_row["category"] if db_row else "unsupported_syntax",
                    "title":      db_row["title"] if db_row else description,
                    "line":       lineno,
                    "match":      line.strip(),
                    "suggestion": db_row["good_example"] if db_row else
                                  "Rewrite without this construct.",
                })

    # ── 3. FTS scan for additional bad_example patterns ───────────────────────
    # For pitfalls that have a bad_example but aren't covered by static patterns,
    # do a simple token presence check.

    extra_rows = con.execute(
        """
        SELECT * FROM pitfalls
        WHERE bad_example IS NOT NULL
          AND category NOT IN ('nonexistent_functions')
          AND id NOT IN (?, ?, ?)
        """,
        ("syn_001", "syn_002", "lang_001"),
    ).fetchall()

    for row in extra_rows:
        bad = row["bad_example"]
        if not bad:
            continue
        # Extract a meaningful token to search for
        token = re.search(r"[\w]+", bad)
        if not token:
            continue
        tok = token.group(0)
        if len(tok) < 4:
            continue
        tok_pattern = re.compile(rf"\b{re.escape(tok)}\b")
        for lineno, line in enumerate(lines, 1):
            if tok_pattern.search(line):
                # Avoid duplicate issues
                already = any(
                    i["pitfall_id"] == row["id"] and i["line"] == lineno
                    for i in issues
                )
                if not already:
                    issues.append({
                        "pitfall_id": row["id"],
                        "category":   row["category"],
                        "title":      row["title"],
                        "line":       lineno,
                        "match":      line.strip(),
                        "suggestion": row["good_example"] or row["notes"],
                    })

    # Deduplicate by (pitfall_id, line)
    seen   = set()
    unique = []
    for issue in issues:
        key = (issue["pitfall_id"], issue["line"])
        if key not in seen:
            seen.add(key)
            unique.append(issue)

    unique.sort(key=lambda i: i["line"])

    return {
        "clean":  len(unique) == 0,
        "issues": unique,
    }
