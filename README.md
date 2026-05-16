# lsl-mcp

A Model Context Protocol (MCP) server providing accurate LSL (Linden Scripting Language) reference data to AI coding assistants. Grounded in the official Second Life wiki, with a curated database of AI-specific pitfalls.

## Motivation

AI coding assistants (Claude Code, Kiro, etc.) frequently produce incorrect LSL — hallucinated function names, unsupported syntax, and wrong signatures. This server gives those tools a live, authoritative reference to query against rather than relying on training data.

## Design Goals

- **Portable LSL only** — no Firestorm-specific syntax
- **AI-aware** — pitfalls are categorised and tagged by which tool produced them
- **Git-tracked** — JSON is the source of truth; SQLite is always derivable
- **Incrementally maintainable** — new pitfalls are captured via CLI as they are discovered

---

## Project Structure

```
lsl-mcp/
├── server.py              # MCP server entrypoint
├── db/
│   ├── schema.sql         # Table definitions
│   └── lsl.db             # SQLite database (gitignored)
├── data/
│   ├── functions/         # One JSON file per LSL function (source of truth)
│   ├── pitfalls.json      # Language pitfalls collection (source of truth)
│   └── constants.json     # LSL constants
├── scripts/
│   ├── scrape_wiki.py     # Populates data/functions/ from the LSL wiki
│   ├── load_db.py         # Imports JSON data into lsl.db
│   └── add_pitfall.py     # CLI tool for adding new pitfalls
├── tools/
│   ├── lookup.py          # lsl_lookup_function, lsl_search
│   ├── pitfalls.py        # lsl_get_pitfalls, lsl_check_code
│   └── reference.py       # lsl_list_events, lsl_constants
└── pyproject.toml
```

---

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

---

## Initial Setup

### 1. Install dependencies

Using uv (recommended):

```bash
uv sync
```

Using pip:

```bash
pip install -e .
```

For development (includes pytest):

```bash
uv sync --dev
# or
pip install -e ".[dev]"
```

### 2. Scrape the LSL wiki

Populates `data/functions/` with one JSON file per function. Approximately 700 functions; takes several minutes due to polite request throttling.

```bash
python scripts/scrape_wiki.py
```

Test a single function first:

```bash
python scripts/scrape_wiki.py --function llListen --dry-run
```

### 2. Initialise the database

Creates `db/lsl.db` from `db/schema.sql` and loads all JSON data.

```bash
python scripts/load_db.py
```

### 3. Connect to Claude Code

Register the server with Claude Code (personal scope):

```bash
# using uv (recommended)
claude mcp add --transport stdio lsl -- uv run /path/to/lsl-mcp/server.py

# using python directly
claude mcp add --transport stdio lsl -- python /path/to/lsl-mcp/server.py
```

Or add a `.mcp.json` to your project root for project-wide sharing:

```json
{
  "mcpServers": {
    "lsl": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "/path/to/lsl-mcp/server.py"]
    }
  }
}
```

Verify the server is connected:

```bash
claude mcp list
```

---

## MCP Tools

| Tool | Description |
|------|-------------|
| `lookup_function(name)` | Exact or fuzzy match on function name. Returns full record including signature, parameters, caveats, and known AI pitfalls. Falls back to `did_you_mean` on miss. |
| `search_functions(query, limit?)` | Full-text search across function names and descriptions. Returns ranked summary list. |
| `get_pitfalls(category?, ai_source?)` | Returns all pitfall entries, optionally filtered by category or source tool. |
| `check_code(code)` | Scans raw LSL source for known AI-generated mistakes. Returns line numbers and suggestions. |
| `list_events(name?)` | Returns all valid LSL event signatures, or looks up one by name. |
| `get_constants(category?, name?)` | Returns constants by category or direct name lookup. |

### Recommended AI workflow

```
Before starting an LSL task:
    get_pitfalls()               ← full briefing on known mistakes

While writing LSL:
    lookup_function("llFoo")     ← verify signature before use
    list_events("touch_start")   ← verify event name and parameters
    get_constants("permissions")  ← browse constants by category

Before presenting code to the user:
    check_code(generated_lsl)    ← catch mistakes before they reach the user
```

---

## Pitfall Categories

| Category | Description |
|----------|-------------|
| `reserved_words` | LSL type names or keywords used as variable identifiers |
| `nonexistent_functions` | Hallucinated function names with no LSL equivalent |
| `unsupported_syntax` | Syntax valid in other languages but a compile error in LSL |
| `scoping` | Global variable assumptions or state scoping errors |
| `type_coercion` | Implicit casting that LSL does not perform |
| `state_behavior` | Unexpected behavior around state changes |

---

## Adding a Pitfall

When an AI tool produces incorrect LSL, capture it:

```bash
python scripts/add_pitfall.py \
  --category nonexistent_functions \
  --title "llStringReplace does not exist in LSL" \
  --bad "llStringReplace(src, old, new)" \
  --good "llReplaceSubString(src, pattern, replacement, count)" \
  --ai-source kiro \
  --notes "llStringReplace is a plausible-sounding hallucination, likely confused with string replace conventions in other languages."
```

Then sync the database and commit:

```bash
python scripts/load_db.py --only pitfalls
git add data/pitfalls.json
git commit -m "pitfall(func_001): llStringReplace does not exist [kiro]"
```

### Claude-assisted capture

Describe the mistake to Claude in plain language. Claude will format it into the correct schema and emit the exact CLI command to run. You verify, run it, and commit. Claude never writes to the database directly — the CLI is the deterministic protocol.

### `--dry-run`

Preview what would be written without touching any files:

```bash
python scripts/add_pitfall.py --category unsupported_syntax --title "..." --dry-run
```

---

## Refreshing Wiki Data

Re-scrape all functions and reload:

```bash
python scripts/scrape_wiki.py --overwrite
python scripts/load_db.py --only functions
```

Re-scrape a single function:

```bash
python scripts/scrape_wiki.py --function llReplaceSubString
python scripts/load_db.py --only functions
```

---

## Database

`db/lsl.db` is **gitignored** — it is always fully derivable from the JSON sources via `load_db.py`. Only `data/` and `db/schema.sql` are version-controlled.

To rebuild from scratch:

```bash
python scripts/load_db.py --reset
```

---

## Pitfall ID Format

IDs are assigned automatically by `add_pitfall.py` based on category:

| Category | Prefix | Example |
|----------|--------|---------|
| `reserved_words` | `lang` | `lang_001` |
| `nonexistent_functions` | `func` | `func_001` |
| `unsupported_syntax` | `syn` | `syn_001` |
| `scoping` | `scope` | `scope_001` |
| `type_coercion` | `type` | `type_001` |
| `state_behavior` | `state` | `state_001` |

---

## Known Pitfalls

| ID | Category | Issue | Source |
|----|----------|-------|--------|
| `lang_001` | `reserved_words` | `key` used as variable name | kiro |
| `func_001` | `nonexistent_functions` | `llStringReplace` does not exist | kiro |
| `syn_001` | `unsupported_syntax` | Ternary operator not supported | kiro, claude-code |
| `syn_002` | `unsupported_syntax` | Switch statements not supported | kiro, claude-code |

---

## Testing

```bash
# Run all tests
python3 -m pytest

# Verbose output
python3 -m pytest -v

# Single module
python3 -m pytest tests/test_pitfalls.py
```

Tests use an in-memory SQLite fixture database built from `db/schema.sql` — no real `lsl.db` or network access required. The `conftest.py` fixture patches `DB_PATH` in all tool modules automatically.

| Test file | Coverage |
|-----------|----------|
| `test_lookup.py` | `lsl_lookup_function`, `lsl_search` |
| `test_pitfalls.py` | `lsl_get_pitfalls`, `lsl_check_code` |
| `test_reference.py` | `lsl_list_events`, `lsl_constants` |
| `test_add_pitfall.py` | ID generation logic in `add_pitfall.py` |

---

## gitignore

```
db/lsl.db
data/functions/
data/scrape_errors.json
__pycache__/
*.pyc
.venv/
```

> `data/functions/` is gitignored because it is fully regenerable from the wiki. Only `data/pitfalls.json` and `data/constants.json` are committed — these contain hand-curated data that cannot be scraped.
