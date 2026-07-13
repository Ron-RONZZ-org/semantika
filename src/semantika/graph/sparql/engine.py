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
# Known prefix → URI map (mirrors triple_turtle._KNOWN_PREFIXES)
# ---------------------------------------------------------------------------

_KNOWN_PREFIXES: dict[str, str] = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "owl": "http://www.w3.org/2002/07/owl#",
}

_DEFAULT_BASE_URI = "https://semantika.local/"

# ---------------------------------------------------------------------------
# IRI mapping — internal IDs ↔ RDF IRIs
# ---------------------------------------------------------------------------


def _to_uri(internal_id: str, base_uri: str = _DEFAULT_BASE_URI) -> ox.NamedNode:
    """Convert an internal Semantika ID to an RDF NamedNode (IRI).

    Resolution rules (mirrors :func:`triple_turtle._format_turtle_uri`):

    1. Full ``http://`` / ``https://`` URI → pass through as-is.
    2. ``prefix:local`` with known prefix (e.g. ``rdf:type``) →
       ``<known_prefix_uri>local``.
    3. ``prefix:local`` with *unknown* prefix → ``<base_uri>resource/prefix:local>``.
    4. Bare label (no colon) → ``<base_uri>node/label>``.
    """
    if internal_id.startswith("http://") or internal_id.startswith("https://"):
        return ox.NamedNode(internal_id)
    if ":" in internal_id:
        prefix, local = internal_id.split(":", 1)
        known = _KNOWN_PREFIXES.get(prefix)
        if known:
            return ox.NamedNode(known + local)
        return ox.NamedNode(f"{base_uri}resource/{internal_id}")
    if not internal_id:
        raise ValueError("Cannot map empty internal ID to IRI")
    return ox.NamedNode(f"{base_uri}node/{internal_id}")


def _from_uri(uri: str, base_uri: str = _DEFAULT_BASE_URI) -> str:
    """Reverse of :func:`_to_uri`: convert a RDF IRI back to an internal ID.

    Raises:
        ValueError: If the URI cannot be mapped back to an internal ID.
    """
    # Known prefix namespaces
    for prefix, ns in _KNOWN_PREFIXES.items():
        if uri.startswith(ns):
            local = uri[len(ns):]
            if local:
                return f"{prefix}:{local}"
    # Base node namespace
    node_ns = f"{base_uri}node/"
    if uri.startswith(node_ns):
        return uri[len(node_ns):]
    # Base resource namespace (for unknown-prefix IDs)
    res_ns = f"{base_uri}resource/"
    if uri.startswith(res_ns):
        return uri[len(res_ns):]
    # Pass-through full URIs
    if uri.startswith("http://") or uri.startswith("https://"):
        return uri
    raise ValueError(f"Cannot map URI back to internal ID: {uri}")


def _to_rdf_term(
    triple: dict[str, Any],
    base_uri: str = _DEFAULT_BASE_URI,
) -> ox.Term:
    """Convert the object column of a triple row to an Oxigraph RDF term.

    Handles ``object_type``:
    - ``'uri'`` → :class:`ox.NamedNode`
    - ``'literal'`` → :class:`ox.Literal` with optional language/datatype.
    """
    val = triple.get("object_value", "")
    otype = triple.get("object_type", "uri")
    if otype == "uri":
        return _to_uri(val, base_uri)
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
        self, store: ox.Store, base_uri: str = _DEFAULT_BASE_URI,
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
                subj = _to_uri(op.triple["subject_id"], base_uri)
                pred = _to_uri(op.triple["predicate_id"], base_uri)
                obj = _to_rdf_term(op.triple, base_uri)
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
        base_uri: str = _DEFAULT_BASE_URI,
    ) -> None:
        self._db = db
        self._base_uri = base_uri
        self._store = ox.Store(path=str(cache_dir))
        self._backlog = SyncBacklog()

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
        self._backlog.process_pending(self._store, self._base_uri)

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

        # Collect all internal IDs from URI bindings (no guessing).
        all_ids: set[str] = set()
        for row in bindings:
            for entry in row.values():
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") != "uri":
                    continue
                try:
                    all_ids.add(_from_uri(entry["value"], self._base_uri))
                except ValueError:
                    continue

        # Batch-query BOTH tables for every ID
        node_labels = self._fetch_node_labels(list(all_ids))
        pred_labels = self._fetch_pred_labels(list(all_ids))

        # Enrich with label AND type, determined by which table matched.
        for row in bindings:
            for entry in row.values():
                if not isinstance(entry, dict):
                    continue
                if entry.get("type") != "uri":
                    continue
                try:
                    internal = _from_uri(entry["value"], self._base_uri)
                except ValueError:
                    continue
                if internal in node_labels:
                    entry["_label"] = node_labels[internal]
                    entry["_type"] = "node"
                elif internal in pred_labels:
                    entry["_label"] = pred_labels[internal]
                    entry["_type"] = "predicate"
                # else: external URI not in our DB — leave unenriched

        return data

    def _fetch_node_labels(self, node_ids: list[str]) -> dict[str, str]:
        """Batch-fetch node labels from SQLite.

        Returns a map of ``node_id → best_label_string``.
        """
        if not node_ids:
            return {}
        placeholders = ", ".join(["?"] * len(node_ids))
        rows = self._db.execute(
            f"SELECT node_id, labels FROM nodes WHERE node_id IN ({placeholders})",
            tuple(node_ids),
        )
        result: dict[str, str] = {}
        for row in rows:
            labels_raw = row.get("labels", "{}")
            if isinstance(labels_raw, str):
                try:
                    labels = json.loads(labels_raw)
                except (json.JSONDecodeError, TypeError):
                    labels = {}
            else:
                labels = labels_raw or {}
            if isinstance(labels, dict):
                label = labels.get("en") or next(
                    (v for v in labels.values() if isinstance(v, str) and v),
                    row["node_id"],
                )
            else:
                label = row["node_id"]
            result[row["node_id"]] = label
        return result

    def _fetch_pred_labels(self, pred_ids: list[str]) -> dict[str, str]:
        """Batch-fetch predicate labels from SQLite.

        Returns a map of ``predicate_id → best_label_string``.
        """
        if not pred_ids:
            return {}
        placeholders = ", ".join(["?"] * len(pred_ids))
        rows = self._db.execute(
            f"SELECT predicate_id, labels FROM predicates "
            f"WHERE predicate_id IN ({placeholders})",
            tuple(pred_ids),
        )
        result: dict[str, str] = {}
        for row in rows:
            labels_raw = row.get("labels", "{}")
            if isinstance(labels_raw, str):
                try:
                    labels = json.loads(labels_raw)
                except (json.JSONDecodeError, TypeError):
                    labels = {}
            else:
                labels = labels_raw or {}
            if isinstance(labels, dict):
                label = labels.get("en") or next(
                    (v for v in labels.values() if isinstance(v, str) and v),
                    row["predicate_id"],
                )
            else:
                label = row["predicate_id"]
            result[row["predicate_id"]] = label
        return result

    # ── Sync hooks (called by service layer) ────────────────────────────

    def on_triple_added(self, triple: dict[str, Any]) -> None:
        """Sync hook: a triple was added to SQLite — add to RocksDB cache.

        On failure, the operation is queued in the backlog for retry;
        the error is logged but **never raised** to the caller to avoid
        breaking the write transaction.
        """
        try:
            subj = _to_uri(triple["subject_id"], self._base_uri)
            pred = _to_uri(triple["predicate_id"], self._base_uri)
            obj = _to_rdf_term(triple, self._base_uri)
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

        On failure, the operation is queued in the backlog for retry;
        the error is logged but **never raised** to the caller.
        """
        try:
            subj = _to_uri(triple["subject_id"], self._base_uri)
            pred = _to_uri(triple["predicate_id"], self._base_uri)
            obj = _to_rdf_term(triple, self._base_uri)
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
        return self._backlog.process_pending(self._store, self._base_uri)

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
                subj = _to_uri(row["subject_id"], self._base_uri)
                pred = _to_uri(row["predicate_id"], self._base_uri)
                obj = _to_rdf_term(row, self._base_uri)
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
