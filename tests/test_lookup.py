"""
tests/test_lookup.py — Tests for tools/lookup.py
"""

import pytest
from tools.lookup import lsl_lookup_function, lsl_search


class TestLookupFunction:

    def test_exact_match(self):
        result = lsl_lookup_function("llListen")
        assert result["name"] == "llListen"
        assert "integer" in result["signature"]

    def test_case_insensitive_match(self):
        result = lsl_lookup_function("lllisten")
        assert result["name"] == "llListen"

    def test_returns_parameters(self):
        result = lsl_lookup_function("llListen")
        params = result["parameters"]
        assert len(params) == 4
        assert params[0]["name"] == "channel"
        assert params[0]["type"] == "integer"

    def test_returns_caveats(self):
        result = lsl_lookup_function("llListen")
        assert len(result["caveats"]) == 2
        assert any("65" in c for c in result["caveats"])

    def test_returns_related(self):
        result = lsl_lookup_function("llListen")
        assert "llListenRemove" in result["related"]
        assert "llListenControl" in result["related"]

    def test_returns_known_ai_pitfalls(self):
        # llReplaceSubString should surface the llStringReplace pitfall
        result = lsl_lookup_function("llReplaceSubString")
        assert "known_ai_pitfalls" in result
        pitfall_ids = [p["id"] for p in result["known_ai_pitfalls"]]
        assert "func_001" in pitfall_ids

    def test_prefix_match(self):
        # "llReplace" should find llReplaceSubString
        result = lsl_lookup_function("llReplace")
        assert result["name"] == "llReplaceSubString"

    def test_miss_returns_error(self):
        result = lsl_lookup_function("llDoesNotExist")
        assert "error" in result
        assert "did_you_mean" in result

    def test_miss_did_you_mean_is_list(self):
        result = lsl_lookup_function("llDoesNotExist")
        assert isinstance(result["did_you_mean"], list)

    def test_return_type_present(self):
        result = lsl_lookup_function("llListen")
        assert result["return_type"] == "integer"

    def test_void_return_type(self):
        result = lsl_lookup_function("llSay")
        assert result["return_type"] == "void"

    def test_mono_only_field_present(self):
        result = lsl_lookup_function("llListen")
        assert "mono_only" in result
        assert result["mono_only"] is False

    def test_deprecated_field_present(self):
        result = lsl_lookup_function("llListen")
        assert "deprecated" in result
        assert result["deprecated"] is False


class TestSearch:

    def test_returns_results_for_known_term(self):
        result = lsl_search("listen")
        assert result["count"] > 0
        names = [r["name"] for r in result["results"]]
        assert "llListen" in names

    def test_result_structure(self):
        result = lsl_search("say")
        assert "query" in result
        assert "count" in result
        assert "results" in result
        for r in result["results"]:
            assert "name" in r
            assert "signature" in r
            assert "description" in r

    def test_description_is_excerpt(self):
        result = lsl_search("listen")
        for r in result["results"]:
            assert len(r["description"]) <= 200

    def test_limit_is_respected(self):
        result = lsl_search("l", limit=1)
        assert len(result["results"]) <= 1

    def test_limit_cap_at_25(self):
        result = lsl_search("l", limit=999)
        assert len(result["results"]) <= 25

    def test_no_results_returns_empty_list(self):
        result = lsl_search("xyzzy_nonexistent_query_abc")
        assert result["count"] == 0
        assert result["results"] == []
