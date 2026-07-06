# AGENTS-web.md — Web Frontend Agent Instructions

## Summary
Svelte 5 SPA frontend — command-bar UI with rich result rendering for the Semantika knowledge graph.

## Purpose and Expected Behavior
- **Command bar**: Always-visible input at the top; `!` prefix triggers command mode; `/*` prefix triggers prompt commands; natural text triggers LLM chat
- **Result area**: Shows command results (tables, forms, graph visualizations, chat responses)
- **Autocomplete**: As-you-type suggestions for commands, node IDs, predicate IDs
- **Graph visualization**: Interactive graph view (force-directed layout) for exploring relationships
- **Form popups**: Fillable forms for `add`/`modify` commands when required params are missing
- **Katex rendering**: Mathematical formulas rendered inline in results
- **Code block rendering**: Syntax-highlighted code snippets in results

## Constraints and Invariants
- Routes handled client-side via svelte-spa-router
- Command metadata fetched dynamically from `GET /api/v1/command/tree` on startup
- No hardcoded command tree — the frontend is driven by backend metadata

## Documentation Reference
- lighterbird's web frontend: `../lighterbird/web/` for proven patterns

## Domain-Specific Rules for Agents
- **Graph view component**: Use vis.js or D3-force for interactive graph visualization. Nodes are draggable, clickable. Edges show predicate labels.
- **Katex rendering**: Use `katex` npm package. Render in result panels when triples or nodes contain formula data.
- **Code blocks**: Use `highlight.js` or similar for syntax highlighting in triple literal display.
- **Command bar autocomplete**: Must suggest node IDs and predicate IDs as the user types, not just command names.
- **Form popups**: `NodeAddForm`, `TripleAddForm`, `PredicateAddForm` — each maps to a `!command` with missing params.
- Follow the same component patterns as lighterbird: `FormField.svelte`, `MultiEntryField.svelte` for shared form components.
