"""File attachment API routes — upload, download, delete node attachments."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile
from pydantic import BaseModel

from semantika.graph.db import get_services
from semantika.graph.file_helpers import (
    classify_attachment,
    copy_file,
    delete_file,
    detect_mime,
    download_file,
    get_file_size,
    is_managed_file,
    move_file,
)

router = APIRouter()


class FileAttachRequest(BaseModel):
    node_id: str
    source: str  # file path or URL
    move: bool = False
    en_loko: bool = False  # store as reference (no file operation)


@router.post("/attach")
async def attach_file(req: FileAttachRequest):
    """Attach a file (local path or URL) to a node.

    Copies/downloads the file into the managed storage directory and
    creates ``:hasFilePath``, ``:hasFileMime``, ``:hasFileSize``, and
    optionally ``:hasFileSource`` triples on the node.
    """
    svc = get_services()
    node = svc["node"].resolve_node_id_prefix(req.node_id)
    if not node:
        raise HTTPException(404, f"Node not found: {req.node_id}")

    node_id = node["node_id"]
    triples_data: list[dict] = []

    if req.en_loko:
        # Reference only — no file operation
        triples_data = [
            {"predicate": ":hasFilePath", "object": req.source, "object_type": "literal"},
        ]
    else:
        source_lower = req.source.strip().lower()
        is_url = source_lower.startswith(("http://", "https://"))

        try:
            if is_url:
                stored_path = download_file(req.source, node_id)
                source_path = req.source
            elif req.move:
                stored_path = move_file(Path(req.source), node_id)
                source_path = None
            else:
                stored_path = copy_file(Path(req.source), node_id)
                source_path = req.source
        except (FileNotFoundError, OSError, ValueError) as e:
            raise HTTPException(400, f"File error: {e}")

        mime_type = detect_mime(stored_path)
        file_size = get_file_size(stored_path)

        triples_data = [
            {"predicate": ":hasFilePath", "object": str(stored_path), "object_type": "literal"},
            {"predicate": ":hasFileMime", "object": mime_type, "object_type": "literal"},
            {"predicate": ":hasFileSize", "object": str(file_size), "object_type": "literal",
             "object_datatype": "xsd:integer"},
        ]
        if source_path:
            triples_data.append({
                "predicate": ":hasFileSource", "object": source_path, "object_type": "literal",
            })

    # Create triples
    created = []
    for td in triples_data:
        try:
            triple = svc["triple"].add(
                subject_id=node_id,
                predicate_id=td["predicate"],
                object_value=td["object"],
                object_type=td.get("object_type", "literal"),
                object_datatype=td.get("object_datatype"),
            )
            created.append(triple)
        except ValueError as e:
            raise HTTPException(400, str(e))

    return {"triples": created}


@router.get("/by-node/{node_id}")
async def get_attachments(node_id: str):
    """Get file attachment triples for a node."""
    svc = get_services()
    node = svc["node"].resolve_node_id_prefix(node_id)
    if not node:
        raise HTTPException(404, f"Node not found: {node_id}")

    file_paths = svc["triple"].get_by_sp(node["node_id"], ":hasFilePath")
    result = []
    for fp in file_paths:
        path_str = fp["object_value"]
        mime_row = svc["triple"].get_by_sp(node["node_id"], ":hasFileMime")
        size_row = svc["triple"].get_by_sp(node["node_id"], ":hasFileSize")
        result.append({
            "path": path_str,
            "mime": mime_row[0]["object_value"] if mime_row else None,
            "size": size_row[0]["object_value"] if size_row else None,
        })
    return {"attachments": result}


@router.delete("/by-node/{node_id}")
async def delete_attachments(node_id: str):
    """Delete all file attachment triples for a node and their stored files."""
    svc = get_services()
    node = svc["node"].resolve_node_id_prefix(node_id)
    if not node:
        raise HTTPException(404, f"Node not found: {node_id}")

    file_paths = svc["triple"].get_by_sp(node["node_id"], ":hasFilePath")
    deleted_files = 0
    for fp in file_paths:
        path_str = fp["object_value"]
        p = Path(path_str)
        if p.exists() and is_managed_file(p):
            delete_file(p)
            deleted_files += 1

    # Remove all file metadata triples
    for pred in (":hasFilePath", ":hasFileMime", ":hasFileSize", ":hasFileSource"):
        svc["triple"].remove(subject_id=node["node_id"], predicate_id=pred)

    return {"deleted_files": deleted_files}
