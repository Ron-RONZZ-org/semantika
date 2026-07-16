"""Attachment-based node creation subcommands (photo, video, file, code).

Moved from the former ``node_specialised.py`` when the ``!node add`` command
tree was reorganised into groups.  Now accessible as::

    !node add attachment photo|video|file|code

These create semantically typed nodes with file attachments and auto-generated
triples.  The ``!node add attachment code`` command also supports inline code
paste via ``--code``, which stores content directly in the database (no file
attachment).
"""

from __future__ import annotations

import logging

from semantika.graph.db import get_services
from semantika.server.command.errors import CommandValidationError
from semantika.server.command.handlers.node_helpers import (
    attach_file_and_create_node,
    parse_dimension,
    resolve_node_refs,
)
from semantika.server.command.registry import command, group_command

logger = logging.getLogger(__name__)


@group_command("node.add.attachment",
               description="Create file-attachment nodes (photo, video, file, code)")
def cmd_node_add_attachment_root(remaining: list[str], flags: dict[str, str]) -> dict:
    """Attachment node creation group — use subcommands.

    Available:
      !node add attachment photo — Create a photo node with file attachment
      !node add attachment video — Create a video node with file attachment
      !node add attachment file  — Create a document node with file attachment
      !node add attachment code  — Create a source code node with file attachment
    """
    return {"type": "status", "title": "Attachment Node Commands", "data": {
        "_summary": (
            "Available !node add attachment commands:\n"
            "  !node add attachment photo — Create a photo node with file attachment\n"
            "  !node add attachment video — Create a video node with file attachment\n"
            "  !node add attachment file  — Create a document node with file attachment\n"
            "  !node add attachment code  — Create a source code node with file attachment"
        )
    }}


@command("node.add.attachment.photo",
         description="Create a photo node with file attachment",
         interactive=True,
         flags=[
             {"name": "path", "type": "string", "required": True,
              "help": "Path or URL to the photo file",
              "placeholder": "/path/to/photo.jpg or https://example.com/photo.jpg"},
             {"name": "id", "type": "string",
              "help": "Explicit node ID",
              "placeholder": "MY_PHOTO_001"},
             {"name": "dimension", "type": "string",
              "help": "Image dimensions (e.g. 1920x1080)",
              "placeholder": "1920x1080"},
             {"name": "object", "type": "string",
              "help": "Node IDs this photo depicts (comma-separated)",
              "placeholder": "ALICE,BOB"},
             {"name": "canonical-link", "type": "string",
              "help": "Original source URL",
              "placeholder": "https://example.com/photo.jpg"},
             {"name": "no-copy", "type": "flag",
              "help": "Store reference only, do not copy file"},
         ])
def cmd_node_add_photo(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a photo node with file attachment and semantic triples.

    Auto-creates:
    - File metadata triples (``:hasFilePath``, ``:hasFileMime``, etc.)
    - ``rdf:type`` triple to ``PHOTO``
    - ``sm:depicts`` triples for each ``--object``
    - ``sm:dimension`` triple if ``--dimension`` is provided
    - ``sm:canonicalLink`` triple if ``--canonical-link`` is provided
    """
    svc = get_services()
    path = flags.get("path", "")
    if not path:
        path = remaining[0] if remaining else ""
    if not path:
        raise CommandValidationError("Specify --path to the photo file")

    labels_raw = flags.get("labels") or ""
    explicit_id = flags.get("id", "")
    no_copy = "no-copy" in flags or flags.get("no-copy", "").lower() in ("true", "1", "yes")
    canonical_link = flags.get("canonical-link", "") or ""
    dimension = parse_dimension(flags.get("dimension", "") or "")
    object_nodes = resolve_node_refs(svc, flags.get("object", "") or "", "object")

    extra_fields: list[tuple[str, str, str, str]] = []
    svc["builtin_type"].ensure_predicates(["sm:depicts", "sm:dimension", "sm:canonicalLink"])

    for obj_id in object_nodes:
        extra_fields.append(("sm:depicts", obj_id, "uri", ""))
    if dimension:
        extra_fields.append(("sm:dimension", dimension, "literal", ""))

    result = attach_file_and_create_node(
        svc, labels_raw, path, "img", "PHOTO",
        explicit_id=explicit_id,
        no_copy=no_copy,
        canonical_link=canonical_link,
        extra_fields=extra_fields,
    )

    response_data: dict = {
        "message": ". ".join(result["message_parts"]),
        "node": result["node"],
    }
    if result["file_triples"]:
        response_data["file_triples"] = result["file_triples"]
    if result["semantic_triples"]:
        response_data["semantic_triples"] = result["semantic_triples"]

    return {"type": "status", "data": response_data}


@command("node.add.attachment.video",
         description="Create a video node with file attachment",
         interactive=True,
         flags=[
             {"name": "path", "type": "string", "required": True,
              "help": "Path or URL to the video file",
              "placeholder": "/path/to/video.mp4 or https://example.com/video.mp4"},
             {"name": "id", "type": "string",
              "help": "Explicit node ID",
              "placeholder": "MY_VIDEO_001"},
             {"name": "dimension", "type": "string",
              "help": "Dimensions (e.g. 1920x1080)",
              "placeholder": "1920x1080"},
             {"name": "object", "type": "string",
              "help": "Node IDs this video depicts (comma-separated)",
              "placeholder": "ALICE,BOB"},
             {"name": "canonical-link", "type": "string",
              "help": "Original source URL",
              "placeholder": "https://example.com/video.mp4"},
             {"name": "no-copy", "type": "flag",
              "help": "Store reference only, do not copy file"},
         ])
def cmd_node_add_video(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a video node with file attachment and semantic triples.

    Auto-creates:
    - File metadata triples (``:hasFilePath``, ``:hasFileMime``, etc.)
    - ``rdf:type`` triple to ``VIDEO``
    - ``sm:depicts`` triples for each ``--object``
    - ``sm:dimension`` triple if ``--dimension`` is provided
    - ``sm:canonicalLink`` triple if ``--canonical-link`` is provided
    """
    svc = get_services()
    path = flags.get("path", "")
    if not path:
        path = remaining[0] if remaining else ""
    if not path:
        raise CommandValidationError("Specify --path to the video file")

    labels_raw = flags.get("labels") or ""
    explicit_id = flags.get("id", "")
    no_copy = "no-copy" in flags or flags.get("no-copy", "").lower() in ("true", "1", "yes")
    canonical_link = flags.get("canonical-link", "") or ""
    dimension = parse_dimension(flags.get("dimension", "") or "")
    object_nodes = resolve_node_refs(svc, flags.get("object", "") or "", "object")

    extra_fields: list[tuple[str, str, str, str]] = []
    svc["builtin_type"].ensure_predicates(["sm:depicts", "sm:dimension", "sm:canonicalLink"])

    for obj_id in object_nodes:
        extra_fields.append(("sm:depicts", obj_id, "uri", ""))
    if dimension:
        extra_fields.append(("sm:dimension", dimension, "literal", ""))

    result = attach_file_and_create_node(
        svc, labels_raw, path, "vid", "VIDEO",
        explicit_id=explicit_id,
        no_copy=no_copy,
        canonical_link=canonical_link,
        extra_fields=extra_fields,
    )

    response_data: dict = {
        "message": ". ".join(result["message_parts"]),
        "node": result["node"],
    }
    if result["file_triples"]:
        response_data["file_triples"] = result["file_triples"]
    if result["semantic_triples"]:
        response_data["semantic_triples"] = result["semantic_triples"]

    return {"type": "status", "data": response_data}


@command("node.add.attachment.file",
         description="Create a document node with file attachment",
         interactive=True,
         flags=[
             {"name": "path", "type": "string", "required": True,
              "help": "Path or URL to the file",
              "placeholder": "/path/to/doc.pdf or https://example.com/doc.pdf"},
             {"name": "id", "type": "string",
              "help": "Explicit node ID",
              "placeholder": "MY_DOC_001"},
             {"name": "theme", "type": "string",
              "help": "Node IDs representing this document's themes (comma-separated)",
              "placeholder": "ALICE,BOB"},
             {"name": "canonical-link", "type": "string",
              "help": "Original source URL",
              "placeholder": "https://example.com/doc.pdf"},
             {"name": "no-copy", "type": "flag",
              "help": "Store reference only, do not copy file"},
         ])
def cmd_node_add_file(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a document node with file attachment and theme triples.

    Auto-creates:
    - File metadata triples
    - ``rdf:type`` triple to ``DOCUMENT``
    - ``sm:theme`` triples for each ``--theme``
    - ``sm:canonicalLink`` triple if ``--canonical-link`` is provided
    """
    svc = get_services()
    path = flags.get("path", "")
    if not path:
        path = remaining[0] if remaining else ""
    if not path:
        raise CommandValidationError("Specify --path to the file")

    labels_raw = flags.get("labels") or ""
    explicit_id = flags.get("id", "")
    no_copy = "no-copy" in flags or flags.get("no-copy", "").lower() in ("true", "1", "yes")
    canonical_link = flags.get("canonical-link", "") or ""
    theme_nodes = resolve_node_refs(svc, flags.get("theme", "") or "", "theme")

    extra_fields: list[tuple[str, str, str, str]] = []
    svc["builtin_type"].ensure_predicates(["sm:theme", "sm:canonicalLink"])

    for theme_id in theme_nodes:
        extra_fields.append(("sm:theme", theme_id, "uri", ""))

    result = attach_file_and_create_node(
        svc, labels_raw, path, "doc", "DOCUMENT",
        explicit_id=explicit_id,
        no_copy=no_copy,
        canonical_link=canonical_link,
        extra_fields=extra_fields,
    )

    response_data: dict = {
        "message": ". ".join(result["message_parts"]),
        "node": result["node"],
    }
    if result["file_triples"]:
        response_data["file_triples"] = result["file_triples"]
    if result["semantic_triples"]:
        response_data["semantic_triples"] = result["semantic_triples"]

    return {"type": "status", "data": response_data}


# ── Language autocomplete list (shared with frontend) ────────────────────

COMMON_LANGUAGES: list[str] = [
    "python", "javascript", "typescript", "rust", "go", "java",
    "cpp", "c", "csharp", "ruby", "php", "swift", "kotlin",
    "shell", "bash", "sql", "yaml", "json", "html", "css",
    "markdown", "latex", "r", "matlab", "lua", "perl",
    "scala", "dart", "haskell", "elixir", "clojure",
]


@command("node.add.attachment.code",
         description="Create a source code node",
         interactive=True,
         flags=[
             # Group "source" — mutually exclusive: paste code OR provide a file
             {"name": "code", "type": "code", "group": "source",
              "help": "Paste source code inline",
              "placeholder": "print('hello world')"},
             {"name": "path", "type": "string", "group": "source",
              "help": "Path or URL to the source code file",
              "placeholder": "/path/to/script.py or https://example.com/app.js"},
             {"name": "lang", "type": "string", "required": True,
              "help": "Programming language (e.g. python, javascript)",
              "placeholder": "python",
              "suggestions": COMMON_LANGUAGES},
             {"name": "id", "type": "string",
              "help": "Explicit node ID",
              "placeholder": "MY_SCRIPT_001"},
             {"name": "canonical-link", "type": "string",
              "help": "Original source URL",
              "placeholder": "https://github.com/user/repo/blob/main/app.js"},
         ])
def cmd_node_add_code(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a source code node — either from inline paste or file.

    Two modes (mutually exclusive):
    - **Inline paste** (default): ``--code`` with the source text content.
      The code is stored directly in the ``code_content`` database column.
      No file attachment is needed — ``--no-copy`` is irrelevant.
    - **File upload**: ``--path`` to a source code file on disk.  The file is
      copied to the data directory (or referenced if ``--no-copy`` is set).

    Auto-creates:
    - ``rdf:type`` triple to ``SOURCE_CODE``
    - ``sm:programmingLanguage`` triple with the language value
    - ``sm:canonicalLink`` triple if ``--canonical-link`` is provided
    - For file uploads: file metadata triples (``:hasFilePath``, etc.)
    """
    svc = get_services()
    code = flags.get("code", "")
    path = flags.get("path", "")

    if not code and not path:
        raise CommandValidationError(
            "Provide source code via --code (paste) or a file via --path"
        )

    lang = flags.get("lang", "")
    if not lang:
        lang = remaining[1] if len(remaining) > 1 else ""
    if not lang:
        raise CommandValidationError(
            "Specify --lang for the programming language"
        )

    labels_raw = flags.get("labels") or ""
    explicit_id = flags.get("id", "")
    canonical_link = flags.get("canonical-link", "") or ""

    svc["builtin_type"].ensure_builtins()
    svc["builtin_type"].ensure_predicates(["sm:programmingLanguage", "sm:canonicalLink"])

    if code:
        # ── Inline code path: store directly in DB ──────────────────
        return _create_inline_code_node(svc, code, lang, labels_raw, explicit_id, canonical_link)
    else:
        # ── File upload path: existing attach-file logic ─────────────
        if not path:
            path = remaining[0] if remaining else ""
        if not path:
            raise CommandValidationError("Specify --path to the source code file")

        no_copy = "no-copy" in flags or flags.get("no-copy", "").lower() in ("true", "1", "yes")

        extra_fields: list[tuple[str, str, str, str]] = []
        extra_fields.append(("sm:programmingLanguage", lang, "literal", ""))

        result = attach_file_and_create_node(
            svc, labels_raw, path, "doc", "SOURCE_CODE",
            explicit_id=explicit_id,
            no_copy=no_copy,
            canonical_link=canonical_link,
            extra_fields=extra_fields,
        )

        response_data: dict = {
            "message": ". ".join(result["message_parts"]),
            "node": result["node"],
        }
        if result["file_triples"]:
            response_data["file_triples"] = result["file_triples"]
        if result["semantic_triples"]:
            response_data["semantic_triples"] = result["semantic_triples"]

        return {"type": "status", "data": response_data}


def _create_inline_code_node(
    svc: dict,
    code: str,
    lang: str,
    labels_raw: str,
    explicit_id: str,
    canonical_link: str,
) -> dict:
    """Create a SOURCE_CODE node with inline code stored in the DB.

    This path skips file attachment entirely — code content is stored
    directly in the ``code_content`` column of the ``nodes`` table, making
    it FTS5-searchable.
    """
    import json

    # Parse labels
    if labels_raw:
        try:
            labels_dict = json.loads(labels_raw) if labels_raw.startswith("{") else None
        except (json.JSONDecodeError, TypeError):
            labels_dict = None
        payload = {"labels": labels_dict} if labels_dict else {"labels": {"en": labels_raw}}
    else:
        payload = {"labels": {}}

    if explicit_id:
        payload["node_id"] = explicit_id

    # Attach code content and language to the node data
    payload["code_content"] = code
    payload["code_language"] = lang

    try:
        node = svc["node"].create(payload)
    except ValueError as e:
        raise CommandValidationError(str(e))

    node_id_val = node["node_id"]
    msg_parts = [f"Created node {node_id_val}"]
    if labels_raw:
        msg_parts.append(f"with label \"{labels_raw}\"")
    msg_parts.append("(inline code)")

    semantic_triples: list[dict] = []
    arc_targets: list[tuple[str, str]] = [("SOURCE_CODE", "rdf:type")]

    if canonical_link:
        arc_targets.append((canonical_link, "sm:canonicalLink"))

    try:
        # Create type and canonical-link triples
        for target, pred in arc_targets:
            # sm:canonicalLink holds a URL string, not a node reference —
            # use 'literal' type to avoid FK constraint on nodes table.
            obj_type = "literal" if pred == "sm:canonicalLink" else "uri"
            try:
                t = svc["triple"].add(
                    subject_id=node_id_val,
                    predicate_id=pred,
                    object_value=target,
                    object_type=obj_type,
                )
                semantic_triples.append(t)
            except ValueError:
                pass  # Duplicate — skip

        # Create programming language literal triple
        try:
            lang_triple = svc["triple"].add(
                subject_id=node_id_val,
                predicate_id="sm:programmingLanguage",
                object_value=lang,
                object_type="literal",
            )
            semantic_triples.append(lang_triple)
        except ValueError:
            pass

        msg_parts.append(f"with {len(semantic_triples)} triple(s)")
    except Exception:
        # Roll back node on failure
        logger.warning("Rolling back node %s after post-creation failure", node_id_val)
        try:
            svc["node"].delete(node_id_val, soft=False)
        except Exception as rb_err:
            logger.error("Rollback delete of node %s also failed: %s", node_id_val, rb_err)
        raise

    return {
        "type": "status",
        "data": {
            "message": ". ".join(msg_parts),
            "node": node,
            "semantic_triples": semantic_triples,
        },
    }
