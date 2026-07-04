/** API client — thin fetch wrappers. */
const BASE = "/api/v1";

export async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export async function del(path) {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  return res.json();
}

export const api = {
  // Graph
  listNodes: (limit = 100) => get(`/graph/nodes?limit=${limit}`),
  getNode: (id) => get(`/graph/nodes/${encodeURIComponent(id)}`),
  createNode: (data) => post("/graph/nodes", data),
  deleteNode: (id) => del(`/graph/nodes/${encodeURIComponent(id)}`),
  searchNodes: (q) => get(`/graph/nodes/search?q=${encodeURIComponent(q)}`),

  listPredicates: (limit = 100) => get(`/graph/predicates?limit=${limit}`),
  searchPredicates: (q) => get(`/graph/predicates/search?q=${encodeURIComponent(q)}`),
  createPredicate: (data) => post("/graph/predicates", data),

  listTriples: (limit = 100) => get(`/graph/triples?limit=${limit}`),
  addTriple: (data) => post("/graph/triples", data),
  triplesBySubject: (id) => get(`/graph/triples/by-subject/${encodeURIComponent(id)}`),

  // Query
  searchAll: (q) => get(`/query/search?q=${encodeURIComponent(q)}`),
  stats: () => get("/query/stats"),
  exportTurtle: () => get("/query/export"),

  // Commands
  commandTree: () => get("/command/tree"),
  execute: (command) => post("/command/execute", { command }),
  help: () => get("/command/help"),

  // LLM
  chat: (message, history = []) => post("/llm/chat", { message, history }),

  // Review
  startReview: () => post("/review/sessions"),
  reviewSessions: () => get("/review/sessions"),
  reviewNext: (uuid) => get(`/review/sessions/${uuid}/next`),
  recordAnswer: (resultUuid, isCorrect) => post("/review/answer", { result_uuid: resultUuid, is_correct: isCorrect }),

  // Units
  listUnits: () => get("/units"),
  getUnit: (id) => get(`/units/${encodeURIComponent(id)}`),
  resolveUnit: (expr) => post("/units/resolve", { expr }),
  createUnit: (data) => post("/units", data),

  // Proofs
  createProof: (data) => post("/proof/proofs", data),
  proofsByTriple: (s, p, o) => get(`/proof/proofs/by-triple?subject_id=${encodeURIComponent(s)}&predicate_id=${encodeURIComponent(p)}&object_value=${encodeURIComponent(o)}`),
};
