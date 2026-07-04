"""Tests for node_helpers.py — label extraction, ID sanitization, normalization."""

from __future__ import annotations

import pytest

from semantika.graph.node_helpers import (
    extract_label_text,
    extract_definition_text,
    get_label_from_node,
    sanitize_node_id,
    normalize_label_to_id,
)


class TestExtractLabelText:
    def test_dict_input(self):
        result = extract_label_text({"en": "Dog", "fr": "Chien"})
        assert "Dog" in result
        assert "Chien" in result

    def test_json_string_input(self):
        result = extract_label_text('{"en": "Cat"}')
        assert result == "Cat"

    def test_empty_dict(self):
        assert extract_label_text({}) == ""

    def test_none_value_filtered(self):
        result = extract_label_text({"en": "Hello", "fr": None})
        assert result == "Hello"

    def test_invalid_json(self):
        assert extract_label_text("not json") == ""

    def test_non_dict_value(self):
        assert extract_label_text("just a string") == ""

    def test_type_error_handled(self):
        assert extract_label_text(None) == ""  # type: ignore[arg-type]


class TestExtractDefinitionText:
    def test_dict_input(self):
        result = extract_definition_text({"en": "A canine"})
        assert result == "A canine"

    def test_json_string(self):
        result = extract_definition_text('{"en": "Feline animal"}')
        assert result == "Feline animal"

    def test_empty(self):
        assert extract_definition_text({}) == ""

    def test_invalid(self):
        assert extract_definition_text(None) == ""  # type: ignore[arg-type]


class TestGetLabelFromNode:
    def test_preferred_lang(self):
        node = {"labels": {"en": "Dog", "fr": "Chien"}, "node_id": "DOG"}
        assert get_label_from_node(node, preferred_lang="en") == "Dog"
        assert get_label_from_node(node, preferred_lang="fr") == "Chien"

    def test_fallback_to_first_label(self):
        node = {"labels": {"fr": "Chien"}, "node_id": "DOG"}
        assert get_label_from_node(node) == "Chien"

    def test_fallback_to_truncated_id(self):
        node = {"node_id": "VERY_LONG_NODE_ID_THAT_EXCEEDS_16_CHARS"}
        result = get_label_from_node(node)
        assert len(result) == 16

    def test_short_id_fallback(self):
        node = {"node_id": "SHORTID"}
        assert get_label_from_node(node) == "SHORTID"

    def test_labels_json_string(self):
        node = {"labels": '{"en": "Dog"}', "node_id": "DOG"}
        assert get_label_from_node(node) == "Dog"

    def test_invalid_labels_json(self):
        node = {"labels": "not json", "node_id": "DOG"}
        assert get_label_from_node(node) == "DOG"

    def test_empty_labels_dict(self):
        node = {"labels": {}, "node_id": "EMPTY"}
        assert get_label_from_node(node) == "EMPTY"

    def test_none_labels(self):
        node = {"labels": None, "node_id": "NONE"}  # type: ignore[dict-item]
        result = get_label_from_node(node)
        assert result == "NONE"

    def test_preferred_lang_not_present(self):
        node = {"labels": {"en": "Hello"}, "node_id": "HELLO"}
        assert get_label_from_node(node, preferred_lang="de") == "Hello"


class TestSanitizeNodeId:
    def test_normal_id_passes_through(self):
        assert sanitize_node_id("HELLO_WORLD") == "HELLO_WORLD"

    def test_strips_whitespace(self):
        assert sanitize_node_id("  HELLO  ") == "HELLO"

    def test_removes_invisible_unicode(self):
        # U+200B is zero-width space (Cf category)
        dirty = "HELLO\u200BWORLD"
        assert sanitize_node_id(dirty) == "HELLOWORLD"

    def test_removes_control_chars(self):
        dirty = "HELLO\x00WORLD"
        assert sanitize_node_id(dirty) == "HELLOWORLD"

    def test_preserves_tabs(self):
        assert sanitize_node_id("HELLO\tWORLD") == "HELLO\tWORLD"

    def test_preserves_spaces(self):
        assert sanitize_node_id("HELLO WORLD") == "HELLO WORLD"


class TestNormalizeLabelToId:
    def test_basic_label(self):
        assert normalize_label_to_id("My Concept") == "MY_CONCEPT"

    def test_accented_chars(self):
        assert normalize_label_to_id("Déjà Vu") == "DEJA_VU"

    def test_mixed_case(self):
        assert normalize_label_to_id("Hello World") == "HELLO_WORLD"

    def test_special_chars_removed(self):
        assert normalize_label_to_id("Price (USD)") == "PRICE_USD"

    def test_leading_trailing_underscores_stripped(self):
        assert normalize_label_to_id("  hello  ") == "HELLO"

    def test_empty_after_stripping(self):
        assert normalize_label_to_id("!!!") == "_UNLABELED"

    def test_multiple_spaces_collapsed(self):
        assert normalize_label_to_id("a   b") == "A_B"

    def test_numbers_preserved(self):
        assert normalize_label_to_id("Test 123") == "TEST_123"

    def test_unicode_to_ascii(self):
        assert normalize_label_to_id("Café") == "CAFE"
