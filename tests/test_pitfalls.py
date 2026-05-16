"""
tests/test_pitfalls.py — Tests for tools/pitfalls.py
"""

import pytest
from tools.pitfalls import lsl_get_pitfalls, lsl_check_code


class TestGetPitfalls:

    def test_returns_all_pitfalls_when_no_filter(self):
        result = lsl_get_pitfalls()
        assert result["count"] == 4
        assert len(result["pitfalls"]) == 4

    def test_filter_by_category(self):
        result = lsl_get_pitfalls(category="unsupported_syntax")
        assert result["count"] == 2
        for p in result["pitfalls"]:
            assert p["category"] == "unsupported_syntax"

    def test_filter_by_ai_source(self):
        result = lsl_get_pitfalls(ai_source="kiro")
        # lang_001, func_001 are kiro; syn_001/syn_002 are "both" which also match
        assert result["count"] >= 2
        for p in result["pitfalls"]:
            assert p["ai_source"] in ("kiro", "both")

    def test_invalid_category_returns_error(self):
        result = lsl_get_pitfalls(category="invented_category")
        assert "error" in result
        assert "valid_categories" in result

    def test_pitfall_structure(self):
        result = lsl_get_pitfalls()
        for p in result["pitfalls"]:
            assert "id" in p
            assert "category" in p
            assert "title" in p
            assert "bad_example" in p
            assert "good_example" in p
            assert "ai_specific" in p
            assert "portable_only" in p

    def test_filters_reflected_in_response(self):
        result = lsl_get_pitfalls(category="reserved_words")
        assert result["filters"]["category"] == "reserved_words"

    def test_reserved_words_category(self):
        result = lsl_get_pitfalls(category="reserved_words")
        assert result["count"] == 1
        assert result["pitfalls"][0]["id"] == "lang_001"

    def test_nonexistent_functions_category(self):
        result = lsl_get_pitfalls(category="nonexistent_functions")
        assert result["count"] == 1
        assert result["pitfalls"][0]["id"] == "func_001"


class TestCheckCode:

    # ── Clean code ────────────────────────────────────────────────────────────

    def test_clean_code_returns_no_issues(self):
        code = """
default {
    state_entry() {
        llSay(0, "Hello");
    }
}
"""
        result = lsl_check_code(code)
        assert result["clean"] is True
        assert result["issues"] == []

    def test_empty_input(self):
        result = lsl_check_code("")
        assert result["clean"] is True

    def test_whitespace_only_input(self):
        result = lsl_check_code("   \n  ")
        assert result["clean"] is True

    # ── Nonexistent functions ─────────────────────────────────────────────────

    def test_detects_llStringReplace(self):
        code = 'string s = llStringReplace(src, "old", "new");'
        result = lsl_check_code(code)
        assert result["clean"] is False
        ids = [i["pitfall_id"] for i in result["issues"]]
        assert "func_001" in ids

    def test_nonexistent_function_includes_suggestion(self):
        code = 'string s = llStringReplace(src, "old", "new");'
        result = lsl_check_code(code)
        issue = next(i for i in result["issues"] if i["pitfall_id"] == "func_001")
        assert issue["suggestion"] is not None
        assert "llReplaceSubString" in issue["suggestion"]

    def test_nonexistent_function_includes_line_number(self):
        code = "string x;\nstring s = llStringReplace(src, old, new);"
        result = lsl_check_code(code)
        issue = next(i for i in result["issues"] if i["pitfall_id"] == "func_001")
        assert issue["line"] == 2

    # ── Ternary operator ──────────────────────────────────────────────────────

    def test_detects_ternary_operator(self):
        code = "integer x = (a > 0) ? 1 : 0;"
        result = lsl_check_code(code)
        assert result["clean"] is False
        ids = [i["pitfall_id"] for i in result["issues"]]
        assert "syn_001" in ids

    def test_ternary_includes_line_number(self):
        code = "integer a = 1;\ninteger x = (a > 0) ? 1 : 0;"
        result = lsl_check_code(code)
        issue = next(i for i in result["issues"] if i["pitfall_id"] == "syn_001")
        assert issue["line"] == 2

    # ── Switch statement ──────────────────────────────────────────────────────

    def test_detects_switch_statement(self):
        code = "switch(channel) { case 1: llSay(0, 'hi'); break; }"
        result = lsl_check_code(code)
        assert result["clean"] is False
        ids = [i["pitfall_id"] for i in result["issues"]]
        assert "syn_002" in ids

    # ── Reserved words ────────────────────────────────────────────────────────

    def test_detects_type_as_variable_name(self):
        code = "key key = llGetOwner();"
        result = lsl_check_code(code)
        assert result["clean"] is False
        ids = [i["pitfall_id"] for i in result["issues"]]
        assert "lang_001" in ids

    def test_valid_variable_name_not_flagged(self):
        code = "key owner = llGetOwner();"
        result = lsl_check_code(code)
        assert result["clean"] is True

    # ── Multiple issues ───────────────────────────────────────────────────────

    def test_multiple_issues_detected(self):
        code = (
            "key key = llGetOwner();\n"
            "string s = llStringReplace(key, 'a', 'b');\n"
            "integer x = (s == '') ? 1 : 0;\n"
        )
        result = lsl_check_code(code)
        assert result["clean"] is False
        assert len(result["issues"]) >= 3

    def test_issues_sorted_by_line(self):
        code = (
            "string s = llStringReplace(src, 'a', 'b');\n"
            "key key = llGetOwner();\n"
        )
        result = lsl_check_code(code)
        lines = [i["line"] for i in result["issues"]]
        assert lines == sorted(lines)

    def test_no_duplicate_issues_same_line(self):
        code = "key key = llGetOwner();"
        result = lsl_check_code(code)
        seen = set()
        for issue in result["issues"]:
            key = (issue["pitfall_id"], issue["line"])
            assert key not in seen, f"Duplicate issue: {key}"
            seen.add(key)

    # ── Issue structure ───────────────────────────────────────────────────────

    def test_issue_has_required_fields(self):
        code = "string s = llStringReplace(src, old, new);"
        result = lsl_check_code(code)
        for issue in result["issues"]:
            assert "pitfall_id" in issue
            assert "category" in issue
            assert "title" in issue
            assert "line" in issue
            assert "match" in issue
            assert "suggestion" in issue
