"""SparqlEngine — SPARQL query engine backed by Oxigraph RocksDB cache + SQLite enrichment.

Architecture
============

- **SQLite** remains the source of truth for all data (nodes, predicates, triples,
  labels, descriptions, FTS5 indexes, proofs, reviews, etc.).
- **Oxigraph RocksDB** is a *cache* that stores only bare ID-triples (no labels,
  no descriptions) for fast SPARQL evaluation.
- On SPARQL query, the engine evaluates against RocksDB, then **enriches** the
  results via batch SQL lookups from SQLite to attach human-readable labels.

Incremental sync
================

Every write through ``TripleService.add()`` / ``.remove()`` / ``.update_metadata()``
fires a sync callback into this engine.  The sync operation adds/removes the
corresponding RDF triple from the RocksDB store.

If a sync operation fails (e.g. RocksDB is temporarily unavailable), it is placed
in a **SyncBacklog** queue and retried with exponential backoff.  After exhausting
retries, the operation is logged as ERROR and dropped — the RocksDB cache is
allowed to be *eventually consistent*.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyoxigraph as ox

from semantika.core import SemantikaDB

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Known prefix → URI map (single source of truth in graph/constants.py)
# ---------------------------------------------------------------------------

from semantika.graph.constants import KNOWN_PREFIXES as _KNOWN_PREFIXES  # noqa: E402

# ---------------------------------------------------------------------------
# IRI mapping — internal IDs ↔ RDF IRIs
# ---------------------------------------------------------------------------


def _get_template(kind: str) -> str:
    """Lazy import to avoid circular dependency at module level."""
    from semantika.core.config import get_iri_template

    return get_iri_template(kind)


def _to_uri(internal_id: str, kind: str = "") -> ox.NamedNode:
    """Convert an internal Semantika ID to an RDF NamedNode (IRI).

    Resolution rules (mirrors :func:`triple_turtle._format_turtle_uri`):

    1. Full ``http://`` / ``https://`` URI → pass through as-is.
    2. ``prefix:local`` with known prefix (e.g. ``rdf:type``) →
       ``<known_prefix_uri>local``.
    3. ``prefix:local`` with *unknown* prefix →
       ``predicate_iri`` template with ``$id`` replaced.
    4. Bare label (no colon) →
       ``node_iri`` template with ``$id`` replaced.
    """
    if internal_id.startswith("http://") or internal_id.startswith("https://"):
        return ox.NamedNode(internal_id)
    if ":" in internal_id:
        prefix, local = internal_id.split(":", 1)
        known = _KNOWN_PREFIXES.get(prefix)
        if known:
            return ox.NamedNode(known + local)
        tpl = _get_template("predicate")
        return ox.NamedNode(tpl.replace("$id", internal_id))
    if not internal_id:
        raise ValueError("Cannot map empty internal ID to IRI")
    tpl = _get_template(kind or "node")
    return ox.NamedNode(tpl.replace("$id", internal_id))


def _from_uri(uri: str) -> str:
    """Reverse of :func:`_to_uri`: convert a RDF IRI back to an internal ID.

    Resolution order:
    1. Template namespaces (node + predicate) — checked first so that
       template-expanded predicate IDs (e.g. ``rs:hasAuthor``) are
       correctly decoded even when the predicate IRI template shares
       a prefix with a known namespace (e.g. ``sm:``).
    2. Known prefix namespaces — e.g. ``rdf:type`` → ``http://www.w3.org/…``.
    3. Pass-through for bare ``http://`` / ``https://`` URIs.

    Raises:
        ValueError: If the URI cannot be mapped back to an internal ID.
    """
    from semantika.core.config import get_iri_template

    # Node template namespace (e.g. "https://sm.ronzz.org/nodes/$id")
    node_ns = get_iri_template("node").replace("$id", "")
    if uri.startswith(node_ns):
        return uri[len(node_ns):]

    # Predicate template namespace (e.g. "https://sm.ronzz.org/predicates/$id")
    pred_ns = get_iri_template("predicate").replace("$id", "")
    if uri.startswith(pred_ns):
        return uri[len(pred_ns):]

    # Known prefix namespaces
    for prefix, ns in _KNOWN_PREFIXES.items():
        if uri.startswith(ns):
            local = uri[len(ns):]
            if local:
                return f"{prefix}:{local}"

    # Pass-through full URIs
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    raise ValueError(f"Cannot map URI back to internal ID: {uri}")


def _to_rdf_term(
    triple: dict[str, Any],
) -> ox.Term:
    """Convert the object column of a triple row to an Oxigraph RDF term.

    Handles ``object_type``:
    - ``'node'`` → :class:`ox.NamedNode`
    - ``'literal'`` → :class:`ox.Literal` with optional language/datatype.
    """
    val = triple.get("object_value", "")
    otype = triple.get("object_type", "node")
    if otype == "node":
        return _to_uri(val)
    lang = triple.get("object_lang")
    dtype = triple.get("object_datatype")
    if lang:
        return ox.Literal(val, language=lang)
    if dtype:
        return ox.Literal(val, datatype=ox.NamedNode(dtype))
    return ox.Literal(val)


# ---------------------------------------------------------------------------
# SyncBacklog — retries failed sync ops with exponential backoff
# ---------------------------------------------------------------------------


@dataclass
class SyncOp:
    """A single sync operation queued for retry."""

    op_type: str  # "add" or "remove"
    triple: dict[str, Any]
    retries: int = 0


class SyncBacklog:
    """Queue of failed sync operations retried with exponential backoff.

    Each failed :class:`SyncOp` is enqueued and retried on subsequent
    :meth:`process_pending` calls.  After ``max_retries`` attempts, the
    operation is dropped and logged as ERROR.
    """

    def __init__(self, max_retries: int = 5, base_delay: float = 1.0) -> None:
        self._queue: deque[SyncOp] = deque()
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._tick = 0

    def enqueue(self, op_type: str, triple: dict[str, Any]) -> None:
        """Add a failed sync operation to the backlog."""
        self._queue.append(SyncOp(op_type=op_type, triple=triple))

    def process_pending(
        self, store: ox.Store,
    ) -> int:
        """Retry pending operations.

        Args:
            store: Oxigraph store to apply operations against.
            base_uri: Base URI for IRI mapping.

        Returns:
            Number of operations processed (successfully or permanently dropped).
        """
        self._tick += 1
        processed = 0
        for _ in range(len(self._queue)):
            op = self._queue[0]
            # Exponential backoff: skip if not enough ticks elapsed
            delay = self._base_delay * (2 ** (op.retries - 1)) if op.retries > 0 else 0
            if op.retries > 0 and delay > self._tick:
                break
            try:
                subj = _to_uri(op.triple["subject_id"])
                pred = _to_uri(op.triple["predicate_id"])
                obj = _to_rdf_term(op.triple)
                quad = ox.Quad(subj, pred, obj)
                if op.op_type == "add":
                    store.add(quad)
                elif op.op_type == "remove":
                    store.remove(quad)
                self._queue.popleft()
                logger.info("SyncBacklog: recovered %s for triple", op.op_type)
            except Exception as exc:
                op.retries += 1
                if op.retries >= self._max_retries:
                    self._queue.popleft()
                    logger.error(
                        "SyncBacklog: %s permanently dropped after %d retries: "
                        "triple=(%s, %s, %s) error=%s",
                        op.op_type, op.retries,
                        op.triple.get("subject_id"),
                        op.triple.get("predicate_id"),
                        op.triple.get("object_value"),
                        exc,
                    )
                else:
                    logger.warning(
                        "SyncBacklog: %s queued (retry %d/%d): "
                        "triple=(%s, %s, %s) error=%s",
                        op.op_type, op.retries, self._max_retries,
                        op.triple.get("subject_id"),
                        op.triple.get("predicate_id"),
                        op.triple.get("object_value"),
                        exc,
                    )
            processed += 1
        return processed

    def __len__(self) -> int:
        return len(self._queue)

    def clear(self) -> None:
        """Clear all pending operations."""
        self._queue.clear()


# ---------------------------------------------------------------------------
# Enrichment helpers
# ---------------------------------------------------------------------------


def _is_known_prefix_iri(uri: str) -> bool:
    """Return True if *uri* uses a known RDF prefix namespace.

    Known prefixes (rdf, rdfs, xsd, owl) have fixed standard namespaces
    that never match user-configured IRI templates.
    """
    return any(uri.startswith(ns) for ns in _KNOWN_PREFIXES.values())


def _extract_label(labels_raw: str | dict | None, fallback_id: str) -> str:
    """Extract the best human-readable label from a JSON labels field."""
    if isinstance(labels_raw, str):
        try:
            labels = json.loads(labels_raw)
        except (json.JSONDecodeError, TypeError):
            labels = {}
    else:
        labels = labels_raw or {}
    if isinstance(labels, dict):
        return labels.get("en") or next(
            (v for v in labels.values() if isinstance(v, str) and v),
            fallback_id,
        )
    return fallback_id


# ---------------------------------------------------------------------------
# SparqlEngine
# ---------------------------------------------------------------------------


class SparqlEngine:
    """SPARQL query engine backed by Oxigraph RocksDB cache + SQLite enrichment.

    Usage::

        engine = SparqlEngine(get_db(), cache_dir=Path("/tmp/sparql-cache"))
        result = engine.execute("SELECT * WHERE { ?s ?p ?o } LIMIT 10")
    """

    MAX_RESULTS = 10_000
    MAX_QUERY_LENGTH = 50_000

    def __init__(
        self,
        db: SemantikaDB,
        cache_dir: Path,
    ) -> None:
        self._db = db
        self._store = ox.Store(path=str(cache_dir))
        self._backlog = SyncBacklog()
        # IRI resolution cache (internal_id → iri string).
        # Populated on-demand by _resolve_iri(); cleared on reindex.
        self._iri_cache: dict[str, str] = {}

    # ── IRI resolution (Option B — cache-aware) ────────────────────────

    def _resolve_iri(self, internal_id: str, kind: str = "") -> str:
        """Return the canonical IRI for *internal_id*, checking cache first.

        Queries the ``iri`` column in SQLite; if empty (template-default), falls
        back to the template.  Results are cached to avoid redundant DB lookups
        during bulk sync (``sync_all``).
        """
        if internal_id in self._iri_cache:
            return self._iri_cache[internal_id]

        # Check for a stored custom IRI (non-empty iri column)
        iri: str | None = None
        for table, id_col in (("nodes", "node_id"), ("predicates", "predicate_id")):
            row = self._db.execute_one(
                f"SELECT iri FROM {table} WHERE {id_col} = ? AND iri != ''",
                (internal_id,),
            )
            if row and row["iri"]:
                iri = row["iri"]
                break

        if iri is None:
            # Template fallback
            iri = _to_uri(internal_id, kind=kind).value

        self._iri_cache[internal_id] = iri
        return iri

    def _iri_from_triple(self, triple: dict[str, Any], role: str) -> str:
        """Resolve the IRI for a triple's subject or predicate.

        *role* is ``"subject"`` or ``"predicate"`` — maps to entity kind
        ``"node"`` or ``"predicate"`` for template resolution.
        Tries the passed ``{role}_iri`` field first (set by service layer for
        custom IRIs), then falls back to cache-aware resolution.
        """
        key = f"{role}_iri"
        if key in triple and triple[key]:
            return triple[key]
        kind = "node" if role == "subject" else "predicate"
        return self._resolve_iri(triple[f"{role}_id"], kind=kind)

    def clear_iri_cache(self) -> None:
        """Clear the IRI resolution cache (call after config template change)."""
        self._iri_cache.clear()

    # ── Public query interface ──────────────────────────────────────────

    def execute(self, query: str) -> dict[str, Any]:
        """Execute a SPARQL query and return enriched results.

        Args:
            query: SPARQL 1.1 query string (SELECT, ASK, CONSTRUCT, DESCRIBE).

        Returns:
            A dict following the SPARQL 1.1 Query Results JSON Format
            (``application/sparql-results+json``) with additional
            ``_label`` fields on bindings, or Turtle for CONSTRUCT/DESCRIBE.

        Raises:
            ValueError: If the query is too long, or the SPARQL syntax is
                invalid.
        """
        # Process any pending backlog items first
        self._backlog.process_pending(self._store)

        if len(query) > self.MAX_QUERY_LENGTH:
            raise ValueError(
                f"SPARQL query exceeds maximum length of {self.MAX_QUERY_LENGTH} characters"
            )

        try:
            result = self._store.query(query)
        except Exception as exc:
            raise ValueError(f"SPARQL query failed: {exc}") from exc

        return self._serialize(result)

    def _serialize(self, result: ox.QueryResult) -> dict[str, Any]:
        """Serialize an Oxigraph query result to the SPARQL JSON format."""
        if isinstance(result, ox.QuerySolutions):
            return self._serialize_solutions(result)
        if isinstance(result, ox.QueryBoolean):
            return json.loads(result.serialize(format=ox.QueryResultsFormat.JSON))
        if isinstance(result, ox.QueryTriples):
            ttl = result.serialize(format=ox.RdfFormat.TURTLE)
            return {"data": ttl.decode("utf-8") if isinstance(ttl, bytes) else ttl,
                    "format": "turtle"}
        raise RuntimeError(f"Unexpected SPARQL result type: {type(result)}")

    def _serialize_solutions(self, solutions: ox.QuerySolutions) -> dict[str, Any]:
        """Serialize SELECT results with enrichment.

        Uses Oxigraph's built-in JSON serialization for correct SPARQL JSON
        format, then batch-enriches URI bindings with labels from SQLite.
        """
        # Use Oxigraph's built-in JSON serialization (correct format)
        raw_json = solutions.serialize(format=ox.QueryResultsFormat.JSON)
        data: dict[str, Any] = json.loads(raw_json)

        # Cap results
        bindings = data.get("results", {}).get("bindings", [])
        if len(bindings) > self.MAX_RESULTS:
            truncated = bindings[:self.MAX_RESULTS]
            data["results"]["bindings"] = truncated
            data["truncated"] = True

        # Dual-path enrichment:
        #   1. IRIs matching the current template prefix → string-op → query by ID
        #   2. Other IRIs (custom --canonical, known-prefix rdf:type) → query by iri column
        from semantika.core.config import get_iri_template

        node_prefix = get_iri_template("node").replace("$id", "")
        pred_prefix = get_iri_template("predicate").replace("$id", "")

        # Bucket 1 — template-matched IRIs → extract internal ID via string-op
        template_ids: dict[str, str] = {}  # internal_id → iri
        # Bucket 2 — custom IRIs → query by iri column
        custom_iris: list[str] = []

        for row in bindings:
            for entry in row.values():
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") != "uri":
                    continue
                iri = entry["value"]
                if _is_known_prefix_iri(iri):
                    custom_iris.append(iri)
                elif iri.startswith(node_prefix):
                    template_ids[iri[len(node_prefix):]] = iri
                elif iri.startswith(pred_prefix):
                    template_ids[iri[len(pred_prefix):]] = iri
                else:
                    custom_iris.append(iri)

        # Resolve bucket 1: query by internal ID
        template_node_info = self._fetch_node_by_ids(list(template_ids.keys()))
        template_pred_info = self._fetch_pred_by_ids(list(template_ids.keys()))
        # Resolve bucket 2: query by iri column
        custom_node_info = self._fetch_node_by_iri(custom_iris)
        custom_pred_info = self._fetch_pred_by_iri(custom_iris)

        # Enrich
        for row in bindings:
            for entry in row.values():
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") != "uri":
                    continue
                iri = entry["value"]
                internal_id: str | None = None

                if iri in custom_node_info:
                    entry["_label"] = custom_node_info[iri][0]
                    entry["_type"] = "node"
                    entry["_id"] = custom_node_info[iri][1]
                elif iri in custom_pred_info:
                    entry["_label"] = custom_pred_info[iri][0]
                    entry["_type"] = "predicate"
                    entry["_id"] = custom_pred_info[iri][1]
                elif iri.startswith(node_prefix):
                    internal_id = iri[len(node_prefix):]
                    info = template_node_info.get(internal_id)
                    if info:
                        entry["_label"] = info[0]
                        entry["_type"] = "node"
                        entry["_id"] = info[1]
                elif iri.startswith(pred_prefix):
                    internal_id = iri[len(pred_prefix):]
                    info = template_pred_info.get(internal_id)
                    if info:
                        entry["_label"] = info[0]
                        entry["_type"] = "predicate"
                        entry["_id"] = info[1]
                # else: external URI not in our DB — leave unenriched

        return data

    # ── Batch lookup helpers ─────────────────────────────────────────────

    def _fetch_node_by_iri(self, iris: list[str]) -> dict[str, tuple[str, str]]:
        """Batch-fetch nodes by IRI column (custom IRIs).

        Returns a map of ``iri → (best_label, node_id)``.
        """
        if not iris:
            return {}
        placeholders = ", ".join(["?"] * len(iris))
        rows = self._db.execute(
            f"SELECT iri, node_id, labels FROM nodes WHERE iri IN ({placeholders})",
            tuple(iris),
        )
        result: dict[str, tuple[str, str]] = {}
        for row in rows:
            label = _extract_label(row.get("labels"), row["node_id"])
            result[row["iri"]] = (label, row["node_id"])
        return result

    def _fetch_pred_by_iri(self, iris: list[str]) -> dict[str, tuple[str, str]]:
        """Batch-fetch predicates by IRI column (custom IRIs).

        Returns a map of ``iri → (best_label, predicate_id)``.
        """
        if not iris:
            return {}
        placeholders = ", ".join(["?"] * len(iris))
        rows = self._db.execute(
            f"SELECT iri, predicate_id, labels FROM predicates "
            f"WHERE iri IN ({placeholders})",
            tuple(iris),
        )
        result: dict[str, tuple[str, str]] = {}
        for row in rows:
            label = _extract_label(row.get("labels"), row["predicate_id"])
            result[row["iri"]] = (label, row["predicate_id"])
        return result

    def _fetch_node_by_ids(self, ids: list[str]) -> dict[str, tuple[str, str]]:
        """Batch-fetch nodes by primary key (template-default IRIs).

        Returns a map of ``node_id → (best_label, node_id)``.
        """
        if not ids:
            return {}
        placeholders = ", ".join(["?"] * len(ids))
        rows = self._db.execute(
            f"SELECT node_id, labels FROM nodes WHERE node_id IN ({placeholders})",
            tuple(ids),
        )
        return {row["node_id"]: (_extract_label(row.get("labels"), row["node_id"]), row["node_id"]) for row in rows}

    def _fetch_pred_by_ids(self, ids: list[str]) -> dict[str, tuple[str, str]]:
        """Batch-fetch predicates by primary key (template-default IRIs).

        Returns a map of ``predicate_id → (best_label, predicate_id)``.
        """
        if not ids:
            return {}
        placeholders = ", ".join(["?"] * len(ids))
        rows = self._db.execute(
            f"SELECT predicate_id, labels FROM predicates WHERE predicate_id IN ({placeholders})",
            tuple(ids),
        )
        return {row["predicate_id"]: (_extract_label(row.get("labels"), row["predicate_id"]), row["predicate_id"]) for row in rows}

    # ── Sync hooks (called by service layer) ────────────────────────────

    def on_triple_added(self, triple: dict[str, Any]) -> None:
        """Sync hook: a triple was added to SQLite — add to RocksDB cache.

        Uses ``_iri_from_triple`` so custom IRIs (set via ``--canonical``) are
        respected.  On failure, the operation is queued in the backlog for
        retry; the error is logged but **never raised** to the caller.
        """
        try:
            subj_str = self._iri_from_triple(triple, "subject")
            pred_str = self._iri_from_triple(triple, "predicate")
            subj = ox.NamedNode(subj_str)
            pred = ox.NamedNode(pred_str)
            obj = _to_rdf_term(triple)
            self._store.add(ox.Quad(subj, pred, obj))
        except Exception as exc:
            self._backlog.enqueue("add", triple)
            logger.error(
                "SPARQL sync: failed to add triple (%s, %s, %s): %s "
                "(queued for retry)",
                triple.get("subject_id"), triple.get("predicate_id"),
                triple.get("object_value"), exc,
            )

    def on_triple_removed(self, triple: dict[str, Any]) -> None:
        """Sync hook: a triple was removed from SQLite — remove from cache.

        Uses ``_iri_from_triple`` so custom IRIs are respected.
        On failure, the operation is queued in the backlog for retry;
        the error is logged but **never raised** to the caller.
        """
        try:
            subj_str = self._iri_from_triple(triple, "subject")
            pred_str = self._iri_from_triple(triple, "predicate")
            subj = ox.NamedNode(subj_str)
            pred = ox.NamedNode(pred_str)
            obj = _to_rdf_term(triple)
            self._store.remove(ox.Quad(subj, pred, obj))
        except Exception as exc:
            self._backlog.enqueue("remove", triple)
            logger.error(
                "SPARQL sync: failed to remove triple (%s, %s, %s): %s "
                "(queued for retry)",
                triple.get("subject_id"), triple.get("predicate_id"),
                triple.get("object_value"), exc,
            )

    def on_triple_updated(
        self, old_triple: dict[str, Any], new_triple: dict[str, Any],
    ) -> None:
        """Sync hook: a triple's metadata was updated — remove old, add new."""
        self.on_triple_removed(old_triple)
        self.on_triple_added(new_triple)

    def process_backlog(self) -> int:
        """Retry any pending failed sync operations.

        Returns the number of operations processed.
        """
        return self._backlog.process_pending(self._store)

    @property
    def backlog_size(self) -> int:
        """Number of pending retry operations in the backlog."""
        return len(self._backlog)

    # ── Lifecycle ───────────────────────────────────────────────────────

    def sync_all(self) -> int:
        """Bulk-sync all existing triples from SQLite into the RocksDB cache.

        Reads all triples from SQLite and streams them into the Oxigraph store.
        Called by :func:`init_sparql_engine` so that the cache is populated
        even if the engine is lazily initialised after data already exists.

        Returns:
            Number of triples synced.
        """
        # Guard against missing table (e.g. during test setup)
        try:
            rows = self._db.execute(
                "SELECT * FROM triples ORDER BY subject_id"
            )
        except Exception:
            return 0

        count = 0
        for row in rows:
            try:
                subj_str = self._resolve_iri(row["subject_id"], kind="node")
                pred_str = self._resolve_iri(row["predicate_id"], kind="predicate")
                subj = ox.NamedNode(subj_str)
                pred = ox.NamedNode(pred_str)
                obj = _to_rdf_term(row)
                self._store.add(ox.Quad(subj, pred, obj))
                count += 1
            except Exception as exc:
                logger.warning(
                    "SPARQL sync_all: skipping triple (%s, %s, %s): %s",
                    row.get("subject_id"), row.get("predicate_id"),
                    row.get("object_value"), exc,
                )
        if count:
            logger.info("SPARQL cache synced %d existing triples", count)
        return count

    def close(self) -> None:
        """Flush the Oxigraph store to disk (no explicit close in pyoxigraph)."""
        try:
            self._store.flush()
        except Exception as exc:
            logger.warning("Error flushing SPARQL cache store: %s", exc)

    def clear_cache(self) -> None:
        """Clear all triples from the RocksDB cache."""
        self._store.clear()
        self._backlog.clear()
        logger.info("SPARQL cache cleared")
