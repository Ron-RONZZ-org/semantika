"""Tests for the context store and ``!context.get`` command handler.

Tests cover:
- Context store CRUD (init, clear, get)
- Entity collection into context (node.add, predicate.add, search, template.list)
- ``context.get`` dispatch
- Post-loop validation helpers

The shared ``services`` fixture (from conftest) provides an isolated DB
with proper ``get_services()`` patching.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

# Trigger handler registration
from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.handlers.context import (
    _current_context_session,
    clear_context,
    collect_into_context,
    get_context,
    get_filtered_context,
    init_context,
)
from semantika.server.command.registry import dispatch, dispatch_path


# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def ctx_session() -> str:
    """Create a fresh context store and return its session ID."""
    sid = "test-session-001"
    init_context(sid)
    _current_context_session.set(sid)
    yield sid
    clear_context(sid)
    _current_context_session.set(None)


# ── Context store CRUD ─────────────────────────────────────────────────


class TestContextStore:
    """init_context, get_context, clear_context, get_filtered_context."""

    def test_init_returns_empty(self) -> None:
        sid = "test-init"
        ctx = init_context(sid)
        assert ctx["nodes"]["created"] == []
        assert ctx["nodes"]["found"] == []
        assert ctx["predicates"]["created"] == []
        assert ctx["predicates"]["found"] == []
        assert ctx["templates"] == []
        clear_context(sid)

    def test_init_is_retrievable(self) -> None:
        sid = "test-retrieve"
        init_context(sid)
        ctx = get_context(sid)
        assert "nodes" in ctx
        assert "predicates" in ctx
        assert "templates" in ctx
        clear_context(sid)

    def test_clear_removes(self) -> None:
        sid = "test-clear"
        init_context(sid)
        clear_context(sid)
        assert get_context(sid) == {}

    def test_get_filtered_nodes(self) -> None:
        sid = "test-filtered"
        init_context(sid)
        collect_into_context(
            sid, "node.add",
            {"data": {"node": {"node_id": "NODE_001", "labels": {"en": "Test"}}}},
        )
        filtered = get_filtered_context(sid, "nodes")
        assert "nodes" in filtered
        assert len(filtered["nodes"]) == 1
        assert filtered["nodes"][0]["id"] == "NODE_001"
        assert "predicates" not in filtered
        clear_context(sid)

    def test_get_filtered_predicates(self) -> None:
        sid = "test-filtered-pred"
        init_context(sid)
        collect_into_context(
            sid, "predicate.add",
            {"data": {"predicate": {"predicate_id": "ex:hasTest", "labels": {"en": "has test"}}}},
        )
        filtered = get_filtered_context(sid, "predicates")
        assert len(filtered["predicates"]) == 1
        assert filtered["predicates"][0]["id"] == "ex:hasTest"
        clear_context(sid)

    def test_get_filtered_templates(self) -> None:
        sid = "test-filtered-tpl"
        init_context(sid)
        collect_into_context(
            sid, "template.list",
            {"templates": [{"name": "test-tpl", "description": "A test", "param_count": 2}]},
        )
        filtered = get_filtered_context(sid, "templates")
        assert len(filtered["templates"]) == 1
        assert filtered["templates"][0]["name"] == "test-tpl"
        clear_context(sid)

    def test_get_filtered_all(self) -> None:
        sid = "test-filtered-all"
        init_context(sid)
        filtered = get_filtered_context(sid, "all")
        assert "nodes" in filtered
        assert "predicates" in filtered
        assert "templates" in filtered
        clear_context(sid)

    def test_get_filtered_unknown_returns_empty(self) -> None:
        sid = "test-filtered-unknown"
        init_context(sid)
        filtered = get_filtered_context(sid, "nonexistent")
        assert filtered == {}
        clear_context(sid)

    def test_get_filtered_no_session(self) -> None:
        filtered = get_filtered_context("nonexistent", "all")
        assert filtered == {"nodes": [], "predicates": [], "templates": []}


# ── Collect into context ───────────────────────────────────────────────


class TestCollectIntoContext:
    """collect_into_context for various tool paths."""

    def test_collect_node_add(self, ctx_session: str) -> None:
        result = {"data": {"node": {"node_id": "MY_NODE", "labels": {"en": "My Node"}}}}
        collect_into_context(ctx_session, "node.add", result)
        ctx = get_context(ctx_session)
        assert len(ctx["nodes"]["created"]) == 1
        assert ctx["nodes"]["created"][0]["id"] == "MY_NODE"

    def test_collect_node_add_deduplicates(self, ctx_session: str) -> None:
        result = {"data": {"node": {"node_id": "DUP", "labels": {"en": "Dup"}}}}
        collect_into_context(ctx_session, "node.add", result)
        collect_into_context(ctx_session, "node.add", result)
        ctx = get_context(ctx_session)
        assert len(ctx["nodes"]["created"]) == 1

    def test_collect_predicate_add(self, ctx_session: str) -> None:
        result = {"data": {"predicate": {"predicate_id": "ex:test", "labels": {"en": "test"}}}}
        collect_into_context(ctx_session, "predicate.add", result)
        ctx = get_context(ctx_session)
        assert len(ctx["predicates"]["created"]) == 1
        assert ctx["predicates"]["created"][0]["id"] == "ex:test"

    def test_collect_node_search(self, ctx_session: str) -> None:
        result = {
            "type": "node-list",
            "data": [
                {"node_id": "EXISTING_1", "labels": {"en": "Existing 1"}},
                {"node_id": "EXISTING_2", "labels": {"en": "Existing 2"}},
            ],
        }
        collect_into_context(ctx_session, "node.search", result)
        ctx = get_context(ctx_session)
        assert len(ctx["nodes"]["found"]) == 2

    def test_collect_node_search_skip_created(self, ctx_session: str) -> None:
        # First create a node
        collect_into_context(
            ctx_session, "node.add",
            {"data": {"node": {"node_id": "CREATED_1", "labels": {"en": "Created"}}}},
        )
        # Then search returns it — should not appear in "found"
        result = {
            "type": "node-list",
            "data": [{"node_id": "CREATED_1", "labels": {"en": "Created"}}],
        }
        collect_into_context(ctx_session, "node.search", result)
        ctx = get_context(ctx_session)
        assert len(ctx["nodes"]["created"]) == 1
        assert len(ctx["nodes"]["found"]) == 0

    def test_collect_template_list(self, ctx_session: str) -> None:
        result = {
            "templates": [
                {"name": "tpl1", "description": "Template 1", "param_count": 2},
            ],
            "count": 1,
        }
        collect_into_context(ctx_session, "template.list", result)
        ctx = get_context(ctx_session)
        assert len(ctx["templates"]) == 1
        assert ctx["templates"][0]["name"] == "tpl1"

    def test_collect_noop_for_unknown_path(self, ctx_session: str) -> None:
        result = {"type": "status", "data": {"message": "hello"}}
        collect_into_context(ctx_session, "unknown.path", result)
        ctx = get_context(ctx_session)
        assert len(ctx["nodes"]["created"]) == 0
        assert len(ctx["nodes"]["found"]) == 0
        assert len(ctx["predicates"]["created"]) == 0
        assert len(ctx["predicates"]["found"]) == 0
        assert len(ctx["templates"]) == 0

    def test_collect_noop_for_no_session(self) -> None:
        # Should not raise
        collect_into_context("nonexistent", "node.add", {"node": {"node_id": "X"}})

    def test_collect_normalises_labels_json_string(self, ctx_session: str) -> None:
        labels_json = json.dumps({"en": "JSON Label"})
        result = {"data": {"node": {"node_id": "JSON_NODE", "labels": labels_json}}}
        collect_into_context(ctx_session, "node.add", result)
        ctx = get_context(ctx_session)
        assert ctx["nodes"]["created"][0]["labels"]["en"] == "JSON Label"

    def test_collect_normalises_labels_plain_string(self, ctx_session: str) -> None:
        result = {"data": {"node": {"node_id": "PLAIN", "labels": "Plain Label"}}}
        collect_into_context(ctx_session, "node.add", result)
        ctx = get_context(ctx_session)
        assert ctx["nodes"]["created"][0]["labels"]["en"] == "Plain Label"

    def test_collect_normalises_labels_missing(self, ctx_session: str) -> None:
        result = {"data": {"node": {"node_id": "NO_LABEL"}}}
        collect_into_context(ctx_session, "node.add", result)
        ctx = get_context(ctx_session)
        assert ctx["nodes"]["created"][0]["labels"] == {}


# ── context.get dispatch ───────────────────────────────────────────────


class TestContextGetHandler:
    """!context.get dispatch handler."""

    def test_context_get_no_session(self) -> None:
        _current_context_session.set(None)
        result = dispatch(["context", "get"], {"type": "all"})
        assert result["type"] == "status"
        assert "No context available" in result["data"]["message"]

    def test_context_get_with_data(self, ctx_session: str) -> None:
        # Populate context with some data
        collect_into_context(
            ctx_session, "node.add",
            {"data": {"node": {"node_id": "MY_NODE", "labels": {"en": "My Node"}}}},
        )
        result = dispatch(["context", "get"], {"type": "all"})
        assert result["type"] == "context"
        assert len(result["data"]["nodes"]) == 1
        assert result["data"]["nodes"][0]["id"] == "MY_NODE"

    def test_context_get_type_nodes(self, ctx_session: str) -> None:
        collect_into_context(
            ctx_session, "node.add",
            {"data": {"node": {"node_id": "N1", "labels": {"en": "Node 1"}}}},
        )
        result = dispatch(["context", "get"], {"type": "nodes"})
        assert result["type"] == "context"
        assert len(result["data"]["nodes"]) == 1
        assert "predicates" not in result["data"]

    def test_context_get_uses_positional_arg(self, ctx_session: str) -> None:
        collect_into_context(
            ctx_session, "node.add",
            {"data": {"node": {"node_id": "N1", "labels": {"en": "Node 1"}}}},
        )
        result = dispatch(["context", "get", "nodes"], {})
        assert result["type"] == "context"
        assert len(result["data"]["nodes"]) == 1


# ── T3 Validation helpers ──────────────────────────────────────────────


class TestTripleValidation:
    """_validate_triple_refs via module-level import."""

    def test_validate_clean_context(self, ctx_session: str) -> None:
        """No errors when all referenced entities exist."""
        collect_into_context(
            ctx_session, "node.add",
            {"data": {"node": {"node_id": "SUBJ", "labels": {"en": "Subject"}}}},
        )
        collect_into_context(
            ctx_session, "node.add",
            {"data": {"node": {"node_id": "OBJ", "labels": {"en": "Object"}}}},
        )
        collect_into_context(
            ctx_session, "predicate.add",
            {"data": {"predicate": {"predicate_id": "ex:rel", "labels": {"en": "rel"}}}},
        )

        # Import the validation function
        from semantika.server.routes.prompt_commands_text_to_triple import _validate_triple_refs

        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "triple_add",
                            "arguments": json.dumps({
                                "subject_id": "SUBJ",
                                "predicate_id": "ex:rel",
                                "object_value": "OBJ",
                                "object_type": "uri",
                            }),
                        }
                    }
                ],
            }
        ]
        errors = _validate_triple_refs(messages, ctx_session)
        assert errors == []

    def test_validate_missing_subject(self, ctx_session: str) -> None:
        from semantika.server.routes.prompt_commands_text_to_triple import _validate_triple_refs

        collect_into_context(
            ctx_session, "predicate.add",
            {"data": {"predicate": {"predicate_id": "ex:rel", "labels": {"en": "rel"}}}},
        )
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "triple_add",
                            "arguments": json.dumps({
                                "subject_id": "MISSING_SUBJ",
                                "predicate_id": "ex:rel",
                                "object_value": "OBJ",
                                "object_type": "uri",
                            }),
                        }
                    }
                ],
            }
        ]
        errors = _validate_triple_refs(messages, ctx_session)
        assert len(errors) == 2  # MISSING_SUBJ + OBJ (uri type, also missing)
        assert any("MISSING_SUBJ" in e for e in errors)

    def test_validate_missing_predicate(self, ctx_session: str) -> None:
        from semantika.server.routes.prompt_commands_text_to_triple import _validate_triple_refs

        collect_into_context(
            ctx_session, "node.add",
            {"data": {"node": {"node_id": "NODE", "labels": {"en": "Node"}}}},
        )
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "triple_add",
                            "arguments": json.dumps({
                                "subject_id": "NODE",
                                "predicate_id": "ex:missing_pred",
                                "object_value": "hello",
                                "object_type": "literal",
                            }),
                        }
                    }
                ],
            }
        ]
        errors = _validate_triple_refs(messages, ctx_session)
        assert len(errors) == 1
        assert "ex:missing_pred" in errors[0]

    def test_validate_literal_object_skip(self, ctx_session: str) -> None:
        """Literal objects should not be validated as node IDs."""
        from semantika.server.routes.prompt_commands_text_to_triple import _validate_triple_refs

        collect_into_context(
            ctx_session, "node.add",
            {"data": {"node": {"node_id": "NODE", "labels": {"en": "Node"}}}},
        )
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "triple_add",
                            "arguments": json.dumps({
                                "subject_id": "NODE",
                                "predicate_id": "ex:hasTitle",
                                "object_value": "Some Title",
                                "object_type": "literal",
                            }),
                        }
                    }
                ],
            }
        ]
        # Even without predicate in context, object is literal so not checked
        errors = _validate_triple_refs(messages, ctx_session)
        # predicate is still checked
        assert len(errors) == 1
        assert "ex:hasTitle" in errors[0]

    def test_validate_deduplicates(self, ctx_session: str) -> None:
        """Same error appearing multiple times should be deduplicated."""
        from semantika.server.routes.prompt_commands_text_to_triple import _validate_triple_refs

        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "function": {
                            "name": "triple_add",
                            "arguments": json.dumps({
                                "subject_id": "MISSING",
                                "predicate_id": "ex:rel",
                                "object_value": "obj",
                                "object_type": "uri",
                            }),
                        }
                    },
                    {
                        "function": {
                            "name": "triple_add",
                            "arguments": json.dumps({
                                "subject_id": "MISSING",
                                "predicate_id": "ex:rel2",
                                "object_value": "obj2",
                                "object_type": "uri",
                            }),
                        }
                    },
                ],
            }
        ]
        errors = _validate_triple_refs(messages, ctx_session)
        # 5 unique errors: MISSING, ex:rel, ex:rel2, obj, obj2
        assert len(errors) == 5
        assert len([e for e in errors if "MISSING" in e]) == 1  # deduplicated (same value)
        obj_errors = [e for e in errors if "object node" in e]
        assert len(obj_errors) == 2  # obj and obj2 are different values


class TestBuildCorrectivePrompt:
    """_build_corrective_prompt formatting."""

    def test_build_includes_available_ids(self, ctx_session: str) -> None:
        from semantika.server.routes.prompt_commands_text_to_triple import _build_corrective_prompt

        collect_into_context(
            ctx_session, "node.add",
            {"data": {"node": {"node_id": "AVAIL_NODE", "labels": {"en": "Available Node"}}}},
        )
        prompt = _build_corrective_prompt(
            ["!triple.add: subject node 'BAD' not found"],
            ctx_session,
        )
        assert "BAD" in prompt
        assert "AVAIL_NODE" in prompt
        assert "context.get(type=all)" in prompt
