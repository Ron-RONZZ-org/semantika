"""Tests for the triple template system — loader, executor, API, handler."""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from semantika.server.templates.executor import expand_template
from semantika.server.templates.loader import list_templates, load_template
from semantika.server.templates.models import TemplateParam, TriplePattern, TripleTemplate

from semantika.server.app import create_app


@pytest.fixture(scope="class")
def client() -> TestClient:
    """Return a TestClient with an isolated test DB."""
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def sample_template_yaml(tmp_path: Path) -> Path:
    """Create a sample template YAML file in tmp_path."""
    content = {
        "name": "book",
        "description": "Add a book with author and ISBN",
        "params": [
            {"name": "subject", "label": "Book node", "type": "node", "required": True},
            {"name": "author", "label": "Author", "type": "node", "required": True},
            {"name": "isbn", "label": "ISBN", "type": "string", "required": True},
            {"name": "title", "label": "Title", "type": "string", "required": False},
        ],
        "triples": [
            "{subject} hasAuthor {author}",
            "{subject} hasISBN {isbn} --str",
            "{subject} hasTitle {title} --str",
        ],
    }
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir(exist_ok=True)
    filepath = templates_dir / "book.yaml"
    filepath.write_text(yaml.dump(content), encoding="utf-8")
    return filepath


@pytest.fixture
def patch_config_to_tmp(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point ``config_dir()`` to ``tmp_path`` for loader tests."""
    monkeypatch.setattr("lightercore.paths.config_dir", lambda: tmp_path)
    monkeypatch.setattr("semantika.server.templates.loader.config_dir", lambda: tmp_path)


@pytest.fixture
def sample_template(sample_template_yaml: Path, patch_config_to_tmp: None) -> TripleTemplate:
    """Load the sample template (config patched to tmp_path)."""
    return load_template("book")


@pytest.fixture
def patch_templates_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the templates config dir to a temp directory. Returns the dir."""
    fake_config = tmp_path
    templates_dir = fake_config / "templates"
    templates_dir.mkdir(exist_ok=True)
    monkeypatch.setattr("lightercore.paths.config_dir", lambda: fake_config)
    monkeypatch.setattr("semantika.server.templates.loader.config_dir", lambda: fake_config)
    return templates_dir


# ── Loader tests ─────────────────────────────────────────────────────────────


class TestTemplateLoader:
    def test_load_template_by_name(self, sample_template_yaml: Path, patch_config_to_tmp: None) -> None:
        tpl = load_template("book")
        assert tpl is not None
        assert tpl.name == "book"
        assert "book" in tpl.description

    def test_load_template_case_insensitive(self, sample_template_yaml: Path, patch_config_to_tmp: None) -> None:
        tpl = load_template("BOOK")
        assert tpl is not None
        assert tpl.name == "book"

    def test_load_nonexistent_returns_none(self) -> None:
        assert load_template("nonexistent") is None

    def test_list_templates(self, sample_template_yaml: Path, patch_config_to_tmp: None) -> None:
        templates = list_templates()
        names = [t.name for t in templates]
        assert "book" in names

    def test_params_parsed(self, sample_template_yaml: Path, patch_config_to_tmp: None) -> None:
        tpl = load_template("book")
        assert tpl is not None
        assert len(tpl.params) == 4
        subject = tpl.params[0]
        assert subject.name == "subject"
        assert subject.type == "node"
        assert subject.required is True

    def test_triples_parsed(self, sample_template_yaml: Path, patch_config_to_tmp: None) -> None:
        tpl = load_template("book")
        assert tpl is not None
        assert len(tpl.triples) == 3
        # Check first triple: URI reference (no flag)
        assert tpl.triples[0].subject_template == "{subject}"
        assert tpl.triples[0].predicate_template == "hasAuthor"
        assert tpl.triples[0].flags == {}
        # Check second triple: str flag
        assert "hasISBN" in tpl.triples[1].raw
        assert tpl.triples[1].flags.get("str") == ""

    def test_skip_invalid_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from lightercore.paths import config_dir
        fake_config = tmp_path
        (fake_config / "templates").mkdir()
        (fake_config / "templates" / "bad.yaml").write_text("not: valid: yaml: [", encoding="utf-8")
        (fake_config / "templates" / "good.yaml").write_text(
            yaml.dump({"name": "good", "description": "ok", "params": [], "triples": []}),
            encoding="utf-8",
        )
        monkeypatch.setattr("semantika.server.templates.loader.config_dir", lambda: fake_config)
        templates = list_templates()
        names = [t.name for t in templates]
        assert "good" in names
        assert "bad" not in names  # bad file is skipped

    def test_empty_yml_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.yaml"
        f.write_text("", encoding="utf-8")
        # Should not crash — returns None
        from semantika.server.templates.loader import _parse_file
        result = _parse_file(f)
        assert result is None


# ── Executor tests ───────────────────────────────────────────────────────


def _make_string_template() -> TripleTemplate:
    """Return a template where all params are ``string`` type (no node resolution)."""
    return TripleTemplate(
        name="test",
        description="Test template",
        params=[
            TemplateParam(name="subject", label="Subject", type="string", required=True),
            TemplateParam(name="author", label="Author", type="string", required=True),
            TemplateParam(name="isbn", label="ISBN", type="string", required=True),
            TemplateParam(name="title", label="Title", type="string", required=False),
        ],
        triples=[
            TriplePattern(raw="{subject} hasAuthor {author}", subject_template="{subject}", predicate_template="hasAuthor", object_template="{author}"),
            TriplePattern(raw="{subject} hasISBN {isbn} --str", subject_template="{subject}", predicate_template="hasISBN", object_template="{isbn}", flags={"str": ""}),
            TriplePattern(raw="{subject} hasTitle {title} --str", subject_template="{subject}", predicate_template="hasTitle", object_template="{title}", flags={"str": ""}),
        ],
    )


class TestTemplateExpander:
    def test_expand_all_params(self) -> None:
        tpl = _make_string_template()
        values = {"subject": "MyBook", "author": "Tolkien", "isbn": "9780547928227", "title": "The Hobbit"}
        triples = expand_template(tpl, values)
        assert len(triples) == 3
        # First triple: URI reference (no flag — string type still goes URI by default)
        assert triples[0]["subject_id"] == "MyBook"
        assert triples[0]["predicate_id"] == "hasAuthor"
        assert triples[0]["object_value"] == "Tolkien"
        assert triples[0]["object_type"] == "uri"
        # Second triple: string literal (--str flag)
        assert triples[1]["predicate_id"] == "hasISBN"
        assert triples[1]["object_value"] == "9780547928227"
        assert triples[1]["object_type"] == "literal"

    def test_skip_optional_empty(self) -> None:
        """Title is optional and empty → only 2 triples."""
        tpl = _make_string_template()
        values = {"subject": "MyBook", "author": "Tolkien", "isbn": "12345", "title": ""}
        triples = expand_template(tpl, values)
        assert len(triples) == 2  # title triple skipped

    def test_all_required_missing(self) -> None:
        tpl = _make_string_template()
        values = {"subject": "X", "author": "Y", "isbn": "Z"}
        triples = expand_template(tpl, values)
        assert len(triples) == 2  # title not provided → skipped

    def test_empty_optional_param_skips_triple(self) -> None:
        """Triple referencing an optional param with empty value is skipped."""
        tpl = TripleTemplate(name="test", description="", params=[
            TemplateParam(name="x", label="X", type="string", required=False),
        ], triples=[
            TriplePattern(raw="{x} {p} {y}", subject_template="{x}", predicate_template="{p}", object_template="{y}"),
        ])
        triples = expand_template(tpl, {"x": ""})
        assert len(triples) == 0

    def test_filled_optional_produces_triple(self) -> None:
        tpl = TripleTemplate(name="test", description="", params=[
            TemplateParam(name="x", label="X", type="string", required=False),
        ], triples=[
            TriplePattern(raw="{x} {p} {y}", subject_template="{x}", predicate_template="{p}", object_template="{y}"),
        ])
        triples = expand_template(tpl, {"x": "val"})
        assert len(triples) == 1


# ── API route tests ──────────────────────────────────────────────────────


class TestTripleTemplatesAPI:
    def test_list_templates_endpoint(self, client, patch_templates_dir, sample_template_yaml) -> None:
        resp = client.get("/api/v1/triple-templates/list")
        assert resp.status_code == 200
        data = resp.json()
        names = [t["name"] for t in data]
        assert "book" in names

    def test_get_template_endpoint(self, client, patch_templates_dir, sample_template_yaml) -> None:
        resp = client.get("/api/v1/triple-templates/book")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "book"
        assert len(data["params"]) == 4
        assert len(data["triples"]) == 3

    def test_get_template_not_found(self, client) -> None:
        resp = client.get("/api/v1/triple-templates/nonexistent")
        assert resp.status_code == 404

    def test_expand_endpoint(self, client, patch_templates_dir) -> None:
        """Expand endpoint works with a simple template (no node resolution needed)."""
        from pathlib import Path
        templates_dir = patch_templates_dir
        simple_yaml = templates_dir / "simple.yaml"
        import yaml as pyyaml
        simple_yaml.write_text(pyyaml.dump({
            "name": "simple",
            "description": "Simple test",
            "params": [
                {"name": "a", "label": "A", "type": "string", "required": True},
                {"name": "b", "label": "B", "type": "string", "required": False},
            ],
            "triples": ["{a} relatesTo {b} --str"],
        }), encoding="utf-8")

        resp = client.post("/api/v1/triple-templates/expand", json={
            "name": "simple",
            "values": {"a": "hello", "b": ""},
        })
        assert resp.status_code == 200, resp.json()
        data = resp.json()
        assert data["count"] == 0  # b is optional and empty → skipped
        assert data["template"] == "simple"

    def test_expand_endpoint_missing_name(self, client) -> None:
        resp = client.post("/api/v1/triple-templates/expand", json={})
        assert resp.status_code == 400

    def test_expand_endpoint_not_found(self, client) -> None:
        resp = client.post("/api/v1/triple-templates/expand", json={"name": "nonexistent", "values": {}})
        assert resp.status_code == 404

    def test_execute_endpoint_missing_required(self, client, patch_templates_dir, sample_template_yaml) -> None:
        resp = client.post("/api/v1/triple-templates/execute", json={
            "name": "book",
            "values": {"subject": "MyBook"},  # missing author, isbn
        })
        assert resp.status_code == 400
        assert "Missing required" in resp.json()["detail"]

    def test_save_endpoint(self, client, patch_templates_dir) -> None:
        yaml_content = "name: test\n"
        resp = client.post("/api/v1/triple-templates/save", json={"yaml": yaml_content, "name": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "saved" in data["data"]["message"].lower()

    def test_save_endpoint_no_yaml(self, client) -> None:
        resp = client.post("/api/v1/triple-templates/save", json={})
        assert resp.status_code == 400

    def test_save_endpoint_infers_name(self, client, patch_templates_dir) -> None:
        yaml_content = "name: inferred\n"
        resp = client.post("/api/v1/triple-templates/save", json={"yaml": yaml_content})
        assert resp.status_code == 200
        assert "inferred" in resp.json()["data"]["message"]


# ── Handler tests (via !triple add --template) ────────────────────────────


def test_triple_add_template_missing_params_returns_form(
    client, patch_templates_dir, sample_template_yaml,
) -> None:
    """!triple add --template book without required params → form-required."""
    resp = client.post("/api/v1/command", json={
        "tokens": ["triple", "add"],
        "flags": {"template": "book"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "form-required"
    assert data["data"]["templateName"] == "book"
    assert "subject" in data["data"]["missing"]


def test_triple_add_template_not_found(client) -> None:
    """Template not found with interactive form → form-required with message."""
    resp = client.post("/api/v1/command", json={
        "tokens": ["triple", "add"],
        "flags": {"template": "nonexistent"},
    })
    assert resp.status_code == 200
    data = resp.json()
    # Because triple.add is interactive, CommandValidationError routes to form-required
    assert data["type"] == "form-required"
    message = (data.get("data") or {}).get("message", "") or ""
    assert "nonexistent" in message or "not found" in message


# ── Template command handler tests (!template list/view/save) ───────────


def test_template_list_empty(client, patch_templates_dir) -> None:
    """!template list with no templates returns empty list."""
    resp = client.post("/api/v1/command", json={
        "tokens": ["template", "list"],
        "flags": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "status"
    assert data["data"]["count"] == 0
    assert data["data"]["templates"] == []


def test_template_list_with_template(client, patch_templates_dir, sample_template_yaml) -> None:
    """!template list returns available templates."""
    resp = client.post("/api/v1/command", json={
        "tokens": ["template", "list"],
        "flags": {},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "status"
    assert data["data"]["count"] >= 1
    names = [t["name"] for t in data["data"]["templates"]]
    assert "book" in names


def test_template_view_found(client, patch_templates_dir, sample_template_yaml) -> None:
    """!template view returns the full template structure."""
    resp = client.post("/api/v1/command", json={
        "tokens": ["template", "view"],
        "flags": {"name": "book"},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "status"
    assert data["data"]["name"] == "book"
    assert len(data["data"]["params"]) == 4
    assert len(data["data"]["triples"]) == 3


def test_template_view_not_found(client) -> None:
    """!template view with nonexistent name returns error."""
    resp = client.post("/api/v1/command", json={
        "tokens": ["template", "view"],
        "flags": {"name": "nonexistent"},
    })
    # template.view has no interactive form → CommandValidationError → HTTP 400
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.json()}"
    detail = str(resp.json().get("detail", {}))
    assert "not found" in detail.lower()


def test_template_save(client, patch_templates_dir) -> None:
    """!template save writes a valid YAML template to disk."""
    yaml_content = (
        "name: test-save\n"
        "description: Test save\n"
        "params:\n"
        "  - name: x\n"
        "    label: X\n"
        "    type: string\n"
        "    required: true\n"
        "triples:\n"
        '  - "{x} hasTitle {x} --str"\n'
    )
    resp = client.post("/api/v1/command", json={
        "tokens": ["template", "save"],
        "flags": {"yaml": yaml_content},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "status"
    assert "saved" in data["data"]["message"].lower()
    assert data["data"]["name"] == "test-save"

    # Verify the file was actually written
    from pathlib import Path
    templates_dir = patch_templates_dir
    saved_file = templates_dir / "test-save.yaml"
    assert saved_file.exists()
    content = saved_file.read_text(encoding="utf-8")
    assert "hasTitle" in content


def test_template_save_invalid_yaml(client) -> None:
    """!template save with invalid YAML returns error."""
    resp = client.post("/api/v1/command", json={
        "tokens": ["template", "save"],
        "flags": {"yaml": "not: valid: yaml: ["},
    })
    # template.save has no interactive form → CommandValidationError → HTTP 400
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.json()}"


def test_template_save_no_name(client) -> None:
    """!template save with YAML lacking a name field returns error."""
    resp = client.post("/api/v1/command", json={
        "tokens": ["template", "save"],
        "flags": {"yaml": "description: no-name\n"},
    })
    # template.save has no interactive form → CommandValidationError → HTTP 400
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.json()}"
