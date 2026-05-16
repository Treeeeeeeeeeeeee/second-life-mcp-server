#!/usr/bin/env python3
"""
load_db.py — Initialise the SQLite database from schema.sql and import
all JSON data from data/functions/, data/pitfalls.json, and data/constants.json.

Usage:
    # Full init + load (safe to re-run — uses upsert)
    python scripts/load_db.py

    # Re-load only pitfalls (fast, useful after add_pitfall.py)
    python scripts/load_db.py --only pitfalls

    # Re-load only functions
    python scripts/load_db.py --only functions

    # Re-load only constants
    python scripts/load_db.py --only constants

    # Wipe and rebuild from scratch
    python scripts/load_db.py --reset
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT          = Path(__file__).resolve().parent.parent
DB_PATH       = ROOT / "db" / "lsl.db"
SCHEMA_PATH   = ROOT / "db" / "schema.sql"
FUNCTIONS_DIR = ROOT / "data" / "functions"
PITFALLS_JSON = ROOT / "data" / "pitfalls.json"
CONSTANTS_JSON = ROOT / "data" / "constants.json"

# ── DB connection ─────────────────────────────────────────────────────────────

def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    return con

# ── Schema ────────────────────────────────────────────────────────────────────

def apply_schema(con: sqlite3.Connection) -> None:
    if not SCHEMA_PATH.exists():
        print(f"[error] Schema not found at {SCHEMA_PATH}")
        sys.exit(1)
    sql = SCHEMA_PATH.read_text()
    con.executescript(sql)
    con.commit()
    print(f"[ok] Schema applied from {SCHEMA_PATH.relative_to(ROOT)}")

def drop_all(con: sqlite3.Connection) -> None:
    """Drop all tables for a clean rebuild."""
    tables = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    con.executescript(
        "\n".join(f"DROP TABLE IF EXISTS [{r['name']}];" for r in tables)
    )
    con.commit()
    print("[ok] All tables dropped")

# ── Functions ─────────────────────────────────────────────────────────────────

def load_functions(con: sqlite3.Connection) -> None:
    files = sorted(FUNCTIONS_DIR.glob("*.json"))
    if not files:
        print(f"[warn] No function JSON files found in {FUNCTIONS_DIR.relative_to(ROOT)}")
        print("       Run scripts/scrape_wiki.py first.")
        return

    ok = skip = err = 0

    for path in files:
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(f"  [error] {path.name}: {e}")
            err += 1
            continue

        name = data.get("name")
        if not name:
            print(f"  [error] {path.name}: missing 'name' field")
            err += 1
            continue

        try:
            _upsert_function(con, data)
            ok += 1
        except sqlite3.Error as e:
            print(f"  [error] {name}: {e}")
            err += 1

    con.commit()
    print(f"[ok] Functions: {ok} upserted, {skip} skipped, {err} errors")


def _upsert_function(con: sqlite3.Connection, d: dict) -> None:
    con.execute(
        """
        INSERT INTO functions
            (name, signature, return_type, description, energy_cost, delay,
             mono_only, deprecated, since_version, updated_at)
        VALUES
            (:name, :signature, :return_type, :description, :energy, :delay,
             :mono_only, :deprecated, :since_version, datetime('now'))
        ON CONFLICT(name) DO UPDATE SET
            signature     = excluded.signature,
            return_type   = excluded.return_type,
            description   = excluded.description,
            energy_cost   = excluded.energy_cost,
            delay         = excluded.delay,
            mono_only     = excluded.mono_only,
            deprecated    = excluded.deprecated,
            since_version = excluded.since_version,
            updated_at    = datetime('now')
        """,
        {
            "name":          d["name"],
            "signature":     d.get("signature"),
            "return_type":   d.get("return_type", "void"),
            "description":   d.get("description"),
            "energy":        d.get("energy"),
            "delay":         d.get("delay"),
            "mono_only":     int(bool(d.get("mono_only", False))),
            "deprecated":    int(bool(d.get("deprecated", False))),
            "since_version": d.get("since_version"),
        },
    )

    func_id = con.execute(
        "SELECT id FROM functions WHERE name = ?", (d["name"],)
    ).fetchone()["id"]

    # Clear and re-insert child rows (simplest upsert for list relations)
    for table in (
        "function_parameters",
        "function_caveats",
        "function_examples",
        "function_related",
        "function_permissions",
        "function_scope",
    ):
        con.execute(f"DELETE FROM {table} WHERE function_id = ?", (func_id,))

    for param in d.get("parameters", []):
        con.execute(
            """
            INSERT INTO function_parameters
                (function_id, position, name, type, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            (func_id, param.get("position", 0), param["name"],
             param["type"], param.get("description")),
        )

    for caveat in d.get("caveats", []):
        con.execute(
            "INSERT INTO function_caveats (function_id, caveat) VALUES (?, ?)",
            (func_id, caveat),
        )

    for example in d.get("examples", []):
        con.execute(
            "INSERT INTO function_examples (function_id, example) VALUES (?, ?)",
            (func_id, example),
        )

    for related in d.get("related", []):
        con.execute(
            "INSERT INTO function_related (function_id, related_name) VALUES (?, ?)",
            (func_id, related),
        )

    for perm in d.get("permissions_required", []):
        con.execute(
            "INSERT INTO function_permissions (function_id, permission) VALUES (?, ?)",
            (func_id, perm),
        )

    for scope_entry in d.get("scope", []):
        con.execute(
            """
            INSERT INTO function_scope (function_id, scope, allowed)
            VALUES (?, ?, ?)
            """,
            (func_id, scope_entry["scope"], int(scope_entry.get("allowed", True))),
        )

# ── Pitfalls ──────────────────────────────────────────────────────────────────

def load_pitfalls(con: sqlite3.Connection) -> None:
    if not PITFALLS_JSON.exists():
        print(f"[warn] {PITFALLS_JSON.relative_to(ROOT)} not found — skipping pitfalls")
        return

    try:
        entries = json.loads(PITFALLS_JSON.read_text())
    except json.JSONDecodeError as e:
        print(f"[error] pitfalls.json: {e}")
        return

    ok = err = 0

    for entry in entries:
        pid = entry.get("id")
        if not pid:
            print(f"  [error] pitfall missing 'id': {entry}")
            err += 1
            continue
        try:
            con.execute(
                """
                INSERT INTO pitfalls
                    (id, category, title, bad_example, good_example, notes,
                     ai_specific, portable_only, ai_source, created_at)
                VALUES
                    (:id, :category, :title, :bad_example, :good_example, :notes,
                     :ai_specific, :portable_only, :ai_source, :created_at)
                ON CONFLICT(id) DO UPDATE SET
                    category     = excluded.category,
                    title        = excluded.title,
                    bad_example  = excluded.bad_example,
                    good_example = excluded.good_example,
                    notes        = excluded.notes,
                    ai_specific  = excluded.ai_specific,
                    portable_only = excluded.portable_only,
                    ai_source    = excluded.ai_source
                """,
                {
                    "id":           pid,
                    "category":     entry.get("category"),
                    "title":        entry.get("title"),
                    "bad_example":  entry.get("bad_example"),
                    "good_example": entry.get("good_example"),
                    "notes":        entry.get("notes"),
                    "ai_specific":  int(bool(entry.get("ai_specific", True))),
                    "portable_only": int(bool(entry.get("portable_only", True))),
                    "ai_source":    entry.get("ai_source"),
                    "created_at":   entry.get("created_at", ""),
                },
            )
            ok += 1
        except sqlite3.Error as e:
            print(f"  [error] pitfall {pid}: {e}")
            err += 1

    con.commit()
    print(f"[ok] Pitfalls: {ok} upserted, {err} errors")

# ── Constants ─────────────────────────────────────────────────────────────────

def load_constants(con: sqlite3.Connection) -> None:
    if not CONSTANTS_JSON.exists():
        print(f"[warn] {CONSTANTS_JSON.relative_to(ROOT)} not found — skipping constants")
        return

    try:
        entries = json.loads(CONSTANTS_JSON.read_text())
    except json.JSONDecodeError as e:
        print(f"[error] constants.json: {e}")
        return

    ok = err = 0

    for entry in entries:
        name = entry.get("name")
        if not name:
            print(f"  [error] constant missing 'name': {entry}")
            err += 1
            continue
        try:
            con.execute(
                """
                INSERT INTO constants
                    (name, type, value, category, description, deprecated)
                VALUES
                    (:name, :type, :value, :category, :description, :deprecated)
                ON CONFLICT(name) DO UPDATE SET
                    type        = excluded.type,
                    value       = excluded.value,
                    category    = excluded.category,
                    description = excluded.description,
                    deprecated  = excluded.deprecated
                """,
                {
                    "name":        name,
                    "type":        entry.get("type", "integer"),
                    "value":       str(entry.get("value", "")),
                    "category":    entry.get("category"),
                    "description": entry.get("description"),
                    "deprecated":  int(bool(entry.get("deprecated", False))),
                },
            )
            ok += 1
        except sqlite3.Error as e:
            print(f"  [error] constant {name}: {e}")
            err += 1

    con.commit()
    print(f"[ok] Constants: {ok} upserted, {err} errors")

# ── Main ──────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Initialise lsl.db and load data from JSON sources"
    )
    p.add_argument(
        "--only",
        choices=["functions", "pitfalls", "constants"],
        default=None,
        help="Load only one data type (schema is always checked)",
    )
    p.add_argument(
        "--reset",
        action="store_true",
        help="Drop all tables and rebuild from scratch",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    con  = connect()

    if args.reset:
        confirm = input("[warn] This will wipe all data. Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)
        drop_all(con)

    apply_schema(con)

    if args.only == "functions":
        load_functions(con)
    elif args.only == "pitfalls":
        load_pitfalls(con)
    elif args.only == "constants":
        load_constants(con)
    else:
        load_functions(con)
        load_pitfalls(con)
        load_constants(con)

    con.close()
    print(f"\n[done] Database at {DB_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
