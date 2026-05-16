"""
tests/test_reference.py — Tests for tools/reference.py
"""

import pytest
from tools.reference import lsl_list_events, lsl_constants


class TestListEvents:

    def test_returns_all_events_when_no_name(self):
        result = lsl_list_events()
        assert result["count"] == 3
        assert len(result["events"]) == 3

    def test_all_events_have_name_and_signature(self):
        result = lsl_list_events()
        for e in result["events"]:
            assert "name" in e
            assert "signature" in e
            assert "description" in e

    def test_exact_event_lookup(self):
        result = lsl_list_events(name="listen")
        assert result["name"] == "listen"
        assert "channel" in result["signature"]

    def test_event_lookup_returns_parameters(self):
        result = lsl_list_events(name="listen")
        assert "parameters" in result
        assert len(result["parameters"]) == 4
        assert result["parameters"][0]["name"] == "channel"

    def test_case_insensitive_event_lookup(self):
        result = lsl_list_events(name="LISTEN")
        assert result["name"] == "listen"

    def test_partial_event_lookup(self):
        result = lsl_list_events(name="touch")
        assert result["name"] == "touch_start"

    def test_event_miss_returns_error_and_valid_list(self):
        result = lsl_list_events(name="nonexistent_event")
        assert "error" in result
        assert "valid_events" in result
        assert isinstance(result["valid_events"], list)
        assert "listen" in result["valid_events"]

    def test_valid_events_list_is_complete(self):
        result = lsl_list_events(name="nonexistent_event")
        # Should list all fixture events
        assert set(result["valid_events"]) == {"listen", "touch_start", "state_entry"}

    def test_event_with_no_parameters(self):
        result = lsl_list_events(name="state_entry")
        assert result["parameters"] == []

    def test_since_version_field_present(self):
        result = lsl_list_events(name="listen")
        assert "since_version" in result


class TestGetConstants:

    def test_returns_all_constants_when_no_filter(self):
        result = lsl_constants()
        assert result["total"] == 5
        assert len(result["constants"]) == 5

    def test_response_includes_category_summary(self):
        result = lsl_constants()
        assert "categories" in result
        assert isinstance(result["categories"], dict)

    def test_filter_by_category(self):
        result = lsl_constants(category="permissions")
        assert result["count"] == 1
        assert result["constants"][0]["name"] == "PERMISSION_TAKE_CONTROLS"

    def test_invalid_category_returns_error(self):
        result = lsl_constants(category="invented_category")
        assert "error" in result
        assert "valid_categories" in result

    def test_direct_name_lookup(self):
        result = lsl_constants(name="NULL_KEY")
        assert result["name"] == "NULL_KEY"
        assert result["type"] == "key"
        assert "0000" in result["value"]

    def test_name_lookup_case_insensitive(self):
        result = lsl_constants(name="null_key")
        assert result["name"] == "NULL_KEY"

    def test_name_miss_returns_error_and_suggestions(self):
        result = lsl_constants(name="NULL_NONEXISTENT")
        assert "error" in result
        assert "did_you_mean" in result

    def test_name_miss_suggestions_are_list(self):
        result = lsl_constants(name="NULL_NONEXISTENT")
        assert isinstance(result["did_you_mean"], list)

    def test_constant_structure(self):
        result = lsl_constants()
        for c in result["constants"]:
            assert "name" in c
            assert "type" in c
            assert "value" in c
            assert "deprecated" in c

    def test_name_takes_precedence_over_category(self):
        # Even if category is also supplied, name wins
        result = lsl_constants(category="math", name="NULL_KEY")
        assert result["name"] == "NULL_KEY"
        assert result["category"] == "string"  # fixture: NULL_KEY is in "string" category

    def test_math_category(self):
        result = lsl_constants(category="math")
        names = [c["name"] for c in result["constants"]]
        assert "TRUE" in names
        assert "FALSE" in names

    def test_deprecated_field_is_bool(self):
        result = lsl_constants(name="NULL_KEY")
        assert isinstance(result["deprecated"], bool)
