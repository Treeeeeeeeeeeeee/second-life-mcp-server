#!/usr/bin/env python3
"""
add_pitfall.py — Add a new LSL language pitfall to the database and pitfalls.json.

Usage:
    python scripts/add_pitfall.py \\
        --category unsupported_syntax \\
        --title "Ternary operator not supported" \\
        --bad "x > 0 ? 1 : 0" \\
        --good "if (x > 0) x = 1;" \\
        --ai-source kiro \\
        --notes "Models trained on C-family languages emit ternary expressions."

Categories:
    reserved_words        Type names or keywords used as identifiers
    nonexistent_functions Hallucinated function names
    unsupported_syntax    Valid in other languages, compile error in LSL
    scoping               Global variable assumptions, state scoping errors
    type_coercion         Implicit casting that LSL does not perform
    state_behavior        Unexpected behavior around state changes
"""

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT        = Path(__file__).resolve().parent.parent
DB_PATH     = ROOT / "db" / "lsl.db"
PITFALLS_JSON = ROOT / "data" / "pitfalls.json"

# ── Constants ────────────────────────────────────────────────────────────────

VALID_CATEGORIES = [
    "reserved_words",
    "nonexistent_functions",
    "unsupported_syntax",
    "scoping",
    "type_coercion",
    "state_behavior",
]

VALID_AI_SOURCES = ["kiro", "claude-code", "both"]

CATEGORY_PREFIX = {
    "reserved_words":        "lang",
    "nonexistent_functions": "func",
    "unsupported_syntax":    "syn",
    "scoping":               "scope",
    "type_coercion":         "type",
    "state_behavior":        "state",
}

# ── ID generation ────────────────────────────────────────────────────────────

def next_id(category: str, existing_ids: list[str]) -> str:
    """Generate the next sequential ID for a category, e.g. func_003."""
    prefix = CATEGORY_PREFIX[category]
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    used = [
        int(m.group(1))
        for pid in existing_ids
        if (m := pattern.match(pid))
    ]
    next_num = max(used, default=0) + 1
    return f"{prefix}_{next_num:03d}"

# ── JSON helpers ─────────────────────────────────────────────────────────────

def load_pitfalls_json() -> list[dict]:
    if not PITFALLS_JSON.exists():
        return []
    with PITFALLS_JSON.open() as f:
        return json.load(f)

def save_pitfalls_json(pitfalls: list[dict]) -> None:
    PITFALLS_JSON.parent.mkdir(parents=True, exist_ok=True)
    with PITFALLS_JSON.open("w") as f:
        json.dump(pitfalls, f, indent=2)
        f.write("\n")

# ── SQLite helpers ───────────────────────────────────────────────────────────

def db_connect() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"[error] Database not found at {DB_PATH}")
        print("        Run scripts/load_db.py first to initialise the database.")
        sys.exit(1)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def insert_pitfall(con: sqlite3.Connection, entry: dict) -> None:
    con.execute(
        """
        INSERT INTO pitfalls
            (id, category, title, bad_example, good_example, notes,
             ai_specific, portable_only, ai_source, created_at)
        VALUES
            (:id, :category, :title, :bad_example, :good_example, :notes,
             :ai_specific, :portable_only, :ai_source, :created_at)
        """,
        entry,
    )
    con.commit()

def id_exists_in_db(con: sqlite3.Connection, pitfall_id: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM pitfalls WHERE id = ?", (pitfall_id,)
    ).fetchone()
    return row is not None

# ── CLI ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Add an LSL language pitfall to pitfalls.json and lsl.db",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--category", "-c",
        required=True,
        choices=VALID_CATEGORIES,
        help="Pitfall category",
    )
    p.add_argument(
        "--title", "-t",
        required=True,
        help="Short descriptive title",
    )
    p.add_argument(
        "--bad", "-b",
        default=None,
        metavar="CODE",
        help="Example of incorrect code",
    )
    p.add_argument(
        "--good", "-g",
        default=None,
        metavar="CODE",
        help="Example of correct code",
    )
    p.add_argument(
        "--notes", "-n",
        default=None,
        help="Additional notes or explanation",
    )
    p.add_argument(
        "--ai-source",
        default=None,
        choices=VALID_AI_SOURCES,
        help="Which AI tool produced this mistake (kiro, claude-code, both)",
    )
    p.add_argument(
        "--id",
        default=None,
        help="Override auto-generated ID (e.g. func_002)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the entry without writing anything",
    )
    return p

# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    args = build_parser().parse_args()

    # Load existing pitfalls for ID generation
    existing = load_pitfalls_json()
    existing_ids = [e["id"] for e in existing]

    # Resolve ID
    pitfall_id = args.id if args.id else next_id(args.category, existing_ids)

    # Check for collisions
    if pitfall_id in existing_ids:
        print(f"[error] ID '{pitfall_id}' already exists in pitfalls.json")
        sys.exit(1)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    entry = {
        "id":           pitfall_id,
        "category":     args.category,
        "title":        args.title,
        "bad_example":  args.bad,
        "good_example": args.good,
        "notes":        args.notes,
        "ai_specific":  1,
        "portable_only": 1,
        "ai_source":    args.ai_source,
        "created_at":   now,
    }

    # ── Dry run ──
    if args.dry_run:
        print("\n[dry-run] Entry that would be written:\n")
        print(json.dumps(entry, indent=2))
        print("\n[dry-run] Git commit message:\n")
        source_tag = f" [{args.ai_source}]" if args.ai_source else ""
        print(f"  pitfall({pitfall_id}): {args.title}{source_tag}")
        return

    # ── Write JSON ──
    existing.append(entry)
    save_pitfalls_json(existing)
    print(f"[ok] Written to {PITFALLS_JSON}")

    # ── Write SQLite ──
    try:
        con = db_connect()
        if id_exists_in_db(con, pitfall_id):
            print(f"[warn] ID '{pitfall_id}' already exists in database — skipping DB insert")
        else:
            insert_pitfall(con, entry)
            print(f"[ok] Inserted into {DB_PATH}")
    except sqlite3.Error as e:
        print(f"[error] Database write failed: {e}")
        print("        pitfalls.json was updated. Re-run load_db.py to sync.")
        sys.exit(1)

    # ── Suggested git commit ──
    source_tag = f" [{args.ai_source}]" if args.ai_source else ""
    print(f"\n[git] Suggested commit:")
    print(f"  git add data/pitfalls.json")
    print(f"  git commit -m \"pitfall({pitfall_id}): {args.title}{source_tag}\"")

if __name__ == "__main__":
    main()
