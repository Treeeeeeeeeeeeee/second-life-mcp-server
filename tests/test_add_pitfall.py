"""
tests/test_add_pitfall.py — Tests for scripts/add_pitfall.py

Tests the ID generation logic and entry construction without touching
the filesystem or database.
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from add_pitfall import next_id, CATEGORY_PREFIX


class TestNextId:

    def test_first_id_for_empty_list(self):
        assert next_id("reserved_words", []) == "lang_001"

    def test_first_id_nonexistent_functions(self):
        assert next_id("nonexistent_functions", []) == "func_001"

    def test_first_id_unsupported_syntax(self):
        assert next_id("unsupported_syntax", []) == "syn_001"

    def test_increments_from_existing(self):
        existing = ["lang_001", "lang_002"]
        assert next_id("reserved_words", existing) == "lang_003"

    def test_does_not_increment_other_categories(self):
        # func IDs should not affect lang ID sequence
        existing = ["func_001", "func_002", "func_003"]
        assert next_id("reserved_words", existing) == "lang_001"

    def test_handles_gaps_in_sequence(self):
        # Should use max + 1, not fill gaps
        existing = ["lang_001", "lang_005"]
        assert next_id("reserved_words", existing) == "lang_006"

    def test_zero_pads_to_three_digits(self):
        existing = [f"lang_{i:03d}" for i in range(1, 10)]
        assert next_id("reserved_words", existing) == "lang_010"

    def test_all_category_prefixes(self):
        for category, prefix in CATEGORY_PREFIX.items():
            result = next_id(category, [])
            assert result == f"{prefix}_001"

    def test_mixed_categories_dont_interfere(self):
        existing = ["lang_001", "func_001", "syn_001", "syn_002"]
        assert next_id("unsupported_syntax", existing) == "syn_003"
        assert next_id("reserved_words", existing) == "lang_002"
        assert next_id("nonexistent_functions", existing) == "func_002"
