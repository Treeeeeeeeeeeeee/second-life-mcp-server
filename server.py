#!/usr/bin/env python3
"""
server.py — LSL MCP server entrypoint.

Exposes LSL reference data and AI pitfall detection to MCP clients
(Claude Code, Kiro, etc.) via stdio transport.

Usage:
    python server.py

Register with Claude Code:
    claude mcp add --transport stdio lsl -- python /path/to/lsl-mcp/server.py

Or add to .mcp.json for project-wide sharing:
    {
      "mcpServers": {
        "lsl": {
          "type": "stdio",
          "command": "python",
          "args": ["/path/to/lsl-mcp/server.py"]
        }
      }
    }

IMPORTANT: stdio servers must never write to stdout except via the MCP
protocol. All logging goes to stderr.
"""

import sys
import logging
from pathlib import Path

# Ensure tools/ and project root are importable
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "ERROR: fastmcp not installed. Run: pip install fastmcp",
        file=sys.stderr,
    )
    sys.exit(1)

from tools.lookup import lsl_lookup_function, lsl_search
from tools.pitfalls import lsl_get_pitfalls, lsl_check_code
from tools.reference import lsl_list_events, lsl_constants

# ── Logging — stderr only, never stdout ──────────────────────────────────────

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="[lsl-mcp] %(levelname)s %(message)s",
)
log = logging.getLogger("lsl-mcp")

# ── Server ────────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="lsl",
    instructions="""
You have access to an authoritative LSL (Linden Scripting Language) reference
for Second Life scripting. Use these tools to verify function signatures,
check for known AI-generated mistakes, and look up constants and events
before writing or suggesting LSL code.

Key rules for LSL (portable, non-Firestorm):
- No ternary operators (? :)
- No switch statements
- No global variables — only global constants
- Type names are reserved: integer, float, string, key, vector, rotation, list
- Always verify function names before using them

Recommended workflow:
1. Call lsl_check_code() on any LSL you generate before presenting it.
2. Call lsl_lookup_function() when unsure of a signature.
3. Call lsl_list_events() to verify an event name exists.
4. Call lsl_get_pitfalls() at the start of an LSL task for a full briefing.
""".strip(),
)

# ── Tool registration ─────────────────────────────────────────────────────────

@mcp.tool()
def lookup_function(name: str) -> dict:
    """
    Look up an LSL function by name.

    Returns the full function record: signature, parameters, return type,
    delay, energy cost, caveats, examples, related functions, and any known
    AI-specific pitfalls associated with this function.

    Falls back to fuzzy matching if the exact name is not found, and returns
    a 'did_you_mean' list when no match exists at all — helping catch
    hallucinated function names.

    Args:
        name: Function name, e.g. "llListen" or "llReplaceSubString".
    """
    log.info("lookup_function(%r)", name)
    return lsl_lookup_function(name)


@mcp.tool()
def search_functions(query: str, limit: int = 10) -> dict:
    """
    Full-text search across LSL function names and descriptions.

    Use when you know roughly what a function does but not its exact name.
    Returns a ranked summary list — call lookup_function for the full record.

    Args:
        query: Keywords or natural language, e.g. "listen channel message"
               or "set prim texture face".
        limit: Maximum results to return (default 10, max 25).
    """
    log.info("search_functions(%r, limit=%d)", query, limit)
    return lsl_search(query, limit)


@mcp.tool()
def get_pitfalls(
    category: str | None = None,
    ai_source: str | None = None,
) -> dict:
    """
    Return known LSL pitfalls for AI coding assistants.

    Call with no arguments for a full briefing before starting an LSL task.
    Filter by category or by which AI tool produced the mistake.

    Args:
        category:  reserved_words | nonexistent_functions | unsupported_syntax
                   | scoping | type_coercion | state_behavior
        ai_source: kiro | claude-code | both
    """
    log.info("get_pitfalls(category=%r, ai_source=%r)", category, ai_source)
    return lsl_get_pitfalls(category, ai_source)


@mcp.tool()
def check_code(code: str) -> dict:
    """
    Scan an LSL code snippet for known AI-generated pitfalls.

    Checks for nonexistent function calls, unsupported syntax (ternary
    operators, switch statements), reserved words used as variable names,
    and other patterns from the pitfalls database.

    Call this on any LSL you generate before presenting it to the user.
    Returns line numbers and suggestions for each issue found.

    Args:
        code: Raw LSL source code as a string.
    """
    log.info("check_code(%d chars)", len(code))
    return lsl_check_code(code)


@mcp.tool()
def list_events(name: str | None = None) -> dict:
    """
    Return valid LSL event signatures.

    Call with no arguments to get all events and verify an event name exists.
    Call with a name to get the full signature and parameter details.

    Args:
        name: Optional event name, e.g. "listen" or "touch_start".
              Omit to return all events.
    """
    log.info("list_events(name=%r)", name)
    return lsl_list_events(name)


@mcp.tool()
def get_constants(
    category: str | None = None,
    name: str | None = None,
) -> dict:
    """
    Return LSL constants, optionally filtered by category or name.

    Call with no arguments to see available categories and total count.
    Use category to browse a group (e.g. "permissions", "prim_params").
    Use name for a direct lookup (e.g. "NULL_KEY", "PERMISSION_TAKE_CONTROLS").

    Args:
        category: Optional category filter. See response for valid categories.
        name:     Optional exact constant name. Takes precedence over category.
    """
    log.info("get_constants(category=%r, name=%r)", category, name)
    return lsl_constants(category, name)


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Starting LSL MCP server (stdio)")
    mcp.run(transport="stdio")
