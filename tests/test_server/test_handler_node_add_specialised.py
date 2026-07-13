"""Unit tests for specialised node-add subcommands via dispatch().

Tests use isolated test databases and mocked get_services()
(defined in ``conftest.py``).
"""

from __future__ import annotations

import pytest

from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.helpers import safe_json_loads as _sjs
from semantika.server.command.registry import dispatch


@pytest.fixture
def seeded(services: dict) -> dict:
    """Create seed predicates and nodes for test dependencies."""
    ps = services["predicate"]
    ns = services["node"]
    ps.create({"predicate_id": "ex:knows", "labels": {"en": "knows"}})
    ps.create({"predicate_id": "ex:authored", "labels": {"en": "authored"}})
    ns.create({"node_id": "ALICE", "labels": {"en": "Alice"}})
    ns.create({"node_id": "BOB", "labels": {"en": "Bob"}})
    ns.create({"node_id": "PYTHON", "labels": {"en": "Python"}})
    return services


# ── Helpers ──────────────────────────────────────────────────────────────


def test_parse_dimension(services: dict):
    """Test the parse_dimension helper via node.add.photo --dimension."""
    from semantika.server.command.handlers.node_helpers import parse_dimension
    assert parse_dimension("1920x1080") == "1920x1080"
    assert parse_dimension("800x600") == "800x600"
    assert parse_dimension("") is None
    with pytest.raises(Exception, match="Invalid dimension"):
        parse_dimension("abc")


def test_resolve_node_refs_resolves(seeded: dict):
    """resolve_node_refs should resolve single and multiple node references."""
    from semantika.server.command.handlers.node_helpers import resolve_node_refs
    result = resolve_node_refs(seeded, "ALICE", "object")
    assert result == ["ALICE"]

    result = resolve_node_refs(seeded, "ALICE,BOB", "object")
    assert result == ["ALICE", "BOB"]


def test_resolve_node_refs_not_found(services: dict):
    """resolve_node_refs should raise on unresolvable reference."""
    from semantika.server.command.handlers.node_helpers import resolve_node_refs
    with pytest.raises(Exception, match="not found"):
        resolve_node_refs(services, "NONEXISTENT", "theme")


def test_resolve_node_refs_empty(services: dict):
    """resolve_node_refs should return empty list for empty input."""
    from semantika.server.command.handlers.node_helpers import resolve_node_refs
    assert resolve_node_refs(services, "", "object") == []


# ── Specialised node.add.photo ──────────────────────────────────────────


class TestNodeAddPhoto:
    def test_photo_missing_path(self):
        """Missing --path should raise."""
        with pytest.raises(Exception, match="Specify --path"):
            dispatch(["node", "add", "photo"], {})

    def test_photo_no_copy_flag(self, seeded: dict, tmp_path):
        """Photo with --no-copy should store reference only."""
        p = tmp_path / "test.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0")  # minimal JPEG
        result = dispatch(
            ["node", "add", "photo"],
            {"path": str(p), "no-copy": "true"},
        )
        assert result["type"] == "status"
        node = result["data"]["node"]
        assert node["node_id"] is not None

    def test_photo_with_object(self, seeded: dict, tmp_path):
        """Photo with --object should create sm:depicts triples."""
        p = tmp_path / "sunset.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0")
        result = dispatch(
            ["node", "add", "photo"],
            {"path": str(p), "object": "ALICE,BOB", "no-copy": "true"},
        )
        assert result["type"] == "status"
        assert len(result["data"].get("semantic_triples", [])) >= 2

    def test_photo_with_dimension(self, seeded: dict, tmp_path):
        """Photo with --dimension should create sm:dimension triple."""
        p = tmp_path / "dim_test.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0")
        result = dispatch(
            ["node", "add", "photo"],
            {"path": str(p), "dimension": "1920x1080", "no-copy": "true"},
        )
        assert result["type"] == "status"

    def test_photo_with_canonical_link(self, seeded: dict, tmp_path):
        """Photo with --canonical-link should create sm:canonicalLink triple."""
        p = tmp_path / "cl_test.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0")
        result = dispatch(
            ["node", "add", "photo"],
            {"path": str(p), "canonical-link": "https://example.com/photo.jpg", "no-copy": "true"},
        )
        assert result["type"] == "status"

    def test_photo_with_id(self, seeded: dict, tmp_path):
        """Photo with --id should use the given node ID."""
        p = tmp_path / "id_test.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0")
        result = dispatch(
            ["node", "add", "photo"],
            {"path": str(p), "id": "MY_PHOTO_001", "no-copy": "true"},
        )
        assert result["type"] == "status"
        assert result["data"]["node"]["node_id"] == "MY_PHOTO_001"


# ── Specialised node.add.video ──────────────────────────────────────────


class TestNodeAddVideo:
    def test_video_missing_path(self):
        with pytest.raises(Exception, match="Specify --path"):
            dispatch(["node", "add", "video"], {})

    def test_video_no_copy(self, seeded: dict, tmp_path):
        p = tmp_path / "test.mp4"
        p.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        result = dispatch(
            ["node", "add", "video"],
            {"path": str(p), "no-copy": "true"},
        )
        assert result["type"] == "status"

    def test_video_with_object(self, seeded: dict, tmp_path):
        p = tmp_path / "vid.mp4"
        p.write_bytes(b"\x00\x00\x00\x18ftypmp42")
        result = dispatch(
            ["node", "add", "video"],
            {"path": str(p), "object": "ALICE", "no-copy": "true"},
        )
        assert result["type"] == "status"
        assert len(result["data"].get("semantic_triples", [])) >= 1


# ── Specialised node.add.file ───────────────────────────────────────────


class TestNodeAddFile:
    def test_file_missing_path(self):
        with pytest.raises(Exception, match="Specify --path"):
            dispatch(["node", "add", "file"], {})

    def test_file_no_copy(self, seeded: dict, tmp_path):
        p = tmp_path / "doc.pdf"
        p.write_bytes(b"%PDF-1.4")
        result = dispatch(
            ["node", "add", "file"],
            {"path": str(p), "no-copy": "true"},
        )
        assert result["type"] == "status"

    def test_file_with_theme(self, seeded: dict, tmp_path):
        p = tmp_path / "report.pdf"
        p.write_bytes(b"%PDF-1.4")
        result = dispatch(
            ["node", "add", "file"],
            {"path": str(p), "theme": "ALICE,BOB", "no-copy": "true"},
        )
        assert result["type"] == "status"
        assert len(result["data"].get("semantic_triples", [])) >= 2


# ── Specialised node.add.code ───────────────────────────────────────────


class TestNodeAddCode:
    def test_code_missing_path(self):
        with pytest.raises(Exception, match="Specify --path"):
            dispatch(["node", "add", "code"], {})

    def test_code_missing_lang(self, seeded: dict, tmp_path):
        """Missing --lang should raise."""
        p = tmp_path / "script.py"
        p.write_text("print('hello')")
        with pytest.raises(Exception, match="Specify --lang"):
            dispatch(["node", "add", "code"], {"path": str(p), "no-copy": "true"})

    def test_code_no_copy(self, seeded: dict, tmp_path):
        p = tmp_path / "script.py"
        p.write_text("print('hello')")
        result = dispatch(
            ["node", "add", "code"],
            {"path": str(p), "lang": "python", "no-copy": "true"},
        )
        assert result["type"] == "status"
        # Should have sm:programmingLanguage triple
        assert len(result["data"].get("semantic_triples", [])) >= 1

    def test_code_with_canonical_link(self, seeded: dict, tmp_path):
        p = tmp_path / "app.js"
        p.write_text("console.log('hi')")
        result = dispatch(
            ["node", "add", "code"],
            {"path": str(p), "lang": "javascript", "canonical-link": "https://example.com/app.js", "no-copy": "true"},
        )
        assert result["type"] == "status"


# ── Removed flags error messages ────────────────────────────────────────


class TestRemovedFlags:
    def test_img_flag_raises(self):
        """Old --img flag should raise a clear error."""
        with pytest.raises(Exception, match="has been removed"):
            dispatch(["node", "add"], {"labels": "Test", "img": "/path.jpg"})

    def test_attachment_flag_raises(self):
        with pytest.raises(Exception, match="has been removed"):
            dispatch(["node", "add"], {"labels": "Test", "attachment": "/path.mp4"})

    def test_file_flag_raises(self):
        with pytest.raises(Exception, match="has been removed"):
            dispatch(["node", "add"], {"labels": "Test", "file": "/path.pdf"})

    def test_in_place_flag_raises(self):
        with pytest.raises(Exception, match="has been removed"):
            dispatch(["node", "add"], {"labels": "Test", "in-place": "true"})

    def test_move_flag_raises(self):
        with pytest.raises(Exception, match="has been removed"):
            dispatch(["node", "add"], {"labels": "Test", "move": "true"})


# ── Command tree verification ──────────────────────────────────────────


class TestSpecialisedNodeInTree:
    """Verify the new subcommands appear in the command tree."""

    def test_tree_has_photo(self):
        from semantika.server.command.registry import get_command_tree
        tree = get_command_tree()
        node_entry = next((n for n in tree if n["name"] == "node"), None)
        assert node_entry is not None
        add_entry = next(
            (c for c in node_entry.get("children", []) if c["name"] == "add"),
            None,
        )
        assert add_entry is not None
        child_names = [c["name"] for c in add_entry.get("children", [])]
        assert "photo" in child_names
        assert "video" in child_names
        assert "file" in child_names
        assert "code" in child_names

    def test_photo_has_required_flags(self):
        from semantika.server.command.registry import get_command_tree, get_handler_metadata
        meta = get_handler_metadata("node.add.photo")
        assert meta is not None
        flags = {f["name"] for f in meta.get("flags", [])}
        assert "path" in flags
        assert "dimension" in flags
        assert "object" in flags
        assert "canonical-link" in flags
        assert "no-copy" in flags

    def test_code_has_lang(self):
        from semantika.server.command.registry import get_handler_metadata
        meta = get_handler_metadata("node.add.code")
        assert meta is not None
        flags = {f["name"] for f in meta.get("flags", [])}
        assert "lang" in flags


# ── Node-view response type tests ────────────────────────────────────────


class TestNodeViewType:
    """Verify node.view returns ``node-view`` type for built-in type nodes."""

    def test_regular_node_returns_status(self, services: dict):
        """A plain node without built-in type returns type ``status``."""
        ns = services["node"]
        ns.create({"node_id": "PLAIN", "labels": {"en": "Plain node"}})
        result = dispatch(["node", "view", "PLAIN"], {})
        assert result["type"] == "status"

    def test_builtin_node_without_file_returns_status(self, services: dict):
        """A built-in type node without a file attachment still returns ``status``."""
        bts = services["builtin_type"]
        bts.ensure_builtins()
        ns = services["node"]
        ns.create({"node_id": "EMPTY_PHOTO", "labels": {"en": "Empty Photo"}})
        # Add rdf:type triple to sm:Photo
        ts = services["triple"]
        ts.add("EMPTY_PHOTO", "rdf:type", "sm:Photo", object_type="uri")
        result = dispatch(["node", "view", "EMPTY_PHOTO"], {})
        assert result["type"] == "status"

    def test_photo_node_with_file_returns_node_view(self, services: dict, tmp_path):
        """A photo-type node with a file returns type ``node-view`` with file_url."""
        # Create photo node via specialised command
        p = tmp_path / "test_view.jpg"
        p.write_bytes(b"\xff\xd8\xff\xe0")
        result = dispatch(
            ["node", "add", "photo"],
            {"path": str(p), "no-copy": "true"},
        )
        assert result["type"] == "status"
        node_id = result["data"]["node"]["node_id"]

        # Now view it
        view_result = dispatch(["node", "view"], {"id": node_id})
        assert view_result["type"] == "node-view"
        assert "file_url" in view_result["data"]
        assert view_result["data"]["node_type"] == "photo"
        assert view_result["data"]["file_url"].endswith(node_id)

    def test_code_node_with_file_returns_node_view(self, services: dict, tmp_path):
        """A code-type node with a file returns type ``node-view``."""
        p = tmp_path / "test_view.py"
        p.write_text("print('hello')")
        result = dispatch(
            ["node", "add", "code"],
            {"path": str(p), "lang": "python", "no-copy": "true"},
        )
        assert result["type"] == "status"
        node_id = result["data"]["node"]["node_id"]

        view_result = dispatch(["node", "view"], {"id": node_id})
        assert view_result["type"] == "node-view"
        assert view_result["data"]["node_type"] == "code"
