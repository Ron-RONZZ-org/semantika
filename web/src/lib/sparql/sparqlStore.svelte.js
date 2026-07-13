/**
 * SPARQL store — reactive state for the SPARQL query editor.
 *
 * Manages query text, results, loading state, and interaction with
 * the SPARQL API endpoint.
 *
 * Usage:
 *   import { sparqlStore } from "./sparql/sparqlStore.svelte.js";
 *   sparqlStore.query = "SELECT * WHERE { ?s ?p ?o } LIMIT 10";
 *   await sparqlStore.execute();
 */

const SPARQL_ENDPOINT = "/api/v1/query/sparql";

/** @type {string} */
let _query = $state("SELECT * WHERE {\n  ?s ?p ?o\n}\nLIMIT 10");

/** @type {object|null} */
let _result = $state(null);

/** @type {boolean} */
let _loading = $state(false);

/** @type {string|null} */
let _error = $state(null);

/** @type {Array<{prefix:string, uri:string}>} */
let _prefixes = $state([]);

/** @type {boolean} */
let _prefixesLoaded = $state(false);

export const sparqlStore = {
  get query() {
    return _query;
  },
  set query(v) {
    _query = v;
    _error = null;
  },

  get result() {
    return _result;
  },

  get loading() {
    return _loading;
  },

  get error() {
    return _error;
  },

  get prefixes() {
    return _prefixes;
  },

  get prefixesLoaded() {
    return _prefixesLoaded;
  },

  /**
   * Execute the current SPARQL query against the backend.
   */
  async execute() {
    if (!_query.trim()) {
      _error = "Query cannot be empty.";
      return;
    }

    _loading = true;
    _error = null;
    _result = null;

    try {
      const resp = await fetch(
        `${SPARQL_ENDPOINT}?query=${encodeURIComponent(_query)}`,
        { headers: { Accept: "application/sparql-results+json" } },
      );

      if (!resp.ok) {
        const body = await resp.json().catch(() => ({}));
        const detail = body.detail || body.error || `HTTP ${resp.status}`;
        const msg = typeof detail === "string" ? detail : detail.error || `HTTP ${resp.status}`;
        _error = msg;
        return;
      }

      _result = await resp.json();
    } catch (err) {
      _error = `Network error: ${err.message}`;
    } finally {
      _loading = false;
    }
  },

  /**
   * Load available prefixes from the backend for autocomplete.
   */
  async loadPrefixes() {
    if (_prefixesLoaded) return;
    try {
      const resp = await fetch("/api/v1/query/sparql/preview");
      if (resp.ok) {
        const data = await resp.json();
        // Expecting { prefixes: [ {prefix: "rdf", uri: "..."}, ... ] }
        _prefixes = data.prefixes || data || [];
        _prefixesLoaded = true;
      }
    } catch {
      // Non-critical — autocomplete degrades gracefully
    }
  },

  /**
   * Reset the store to initial state.
   */
  reset() {
    _query = "SELECT * WHERE {\n  ?s ?p ?o\n}\nLIMIT 10";
    _result = null;
    _error = null;
    _loading = false;
  },
};
