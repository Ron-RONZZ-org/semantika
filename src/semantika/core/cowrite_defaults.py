"""Shipped defaults for Semantika's co-writing style files.

These are the default content for ``cowrite_style.md`` (general) and
per-domain files (``cowrite_style_node.md``, ``cowrite_style_predicate.md``,
``cowrite_style_triple.md``).  Users can edit these files to customise
LLM behaviour during co-writing.

Style files live at ``~/.config/semantika/cowrite_style*.md`` and are
auto-seeded on first access by :func:`load_cowrite_style`.
"""

from __future__ import annotations

# ── Mapping form_type → domain slug ────────────────────────────────────────
# Each command path maps to a cowrite style domain file.
# E.g. "node-add-concept" → cowrite_style_node.md

_FORM_TYPE_TO_DOMAIN: dict[str, str] = {
    "node-add-concept": "node",
    "node-add-attachment": "node",
    "node-add-media": "node",
    "node-add-scholarly": "node",
    "node-add-code": "node",
    "node-add-quote": "node",
    "node-modify": "node",
    "predicate-add": "predicate",
    "predicate-group-add": "predicate",
    "triple-add": "triple",
    "unit-add": "unit",
    "proof-add": "proof",
    "review-start": "review",
}

DEFAULT_COWRITE_STYLE = """# Co-writing Style Guide

This file lets you tell the LLM how you want knowledge-graph entries to
sound. Remove or edit the sections below to match your personal style.

## Tone
- Clear, factual, and neutral
- Use precise terminology
- Be concise — entries should be easy to scan

## Language
- Use English for labels and definitions
- Add short definitions for clarity when the label is ambiguous
- Avoid promotional language, subjective opinions, or fluff
"""

DEFAULT_COWRITE_STYLE_NODE = """# Node Style Guide

## Labels
- Use singular form for concept nodes
- Capitalize proper nouns only
- For multi-language labels: use JSON format for the first label field

## Definitions
- One or two sentences capturing the essential meaning
- Include a brief etymology or source if relevant
- For code nodes: describe the purpose and key characteristics

## Examples
- "Python": A dynamically-typed, interpreted programming language.
- "Relativity": Physical theory by Einstein describing gravity as spacetime curvature.
"""

DEFAULT_COWRITE_STYLE_PREDICATE = """# Predicate Style Guide

## ID format
- Use camelCase for multi-word IDs (hasAuthor, isPartOf, depicts)
- Keep IDs short but descriptive
- Follow existing predicate naming conventions in the graph

## Labels
- Use preferred label format: English short description
- Example: "depicts" for ``sm:depicts``
- Include domain/range hints in the description when helpful
"""

DEFAULT_COWRITE_STYLE_TRIPLE = """# Triple Style Guide

## Patterns
- Subject-Predicate-Object: clear and unambiguous
- Use existing predicates from the built-in catalog when possible
- Create new predicates only when no existing one fits

## Descriptions
- Briefly explain the relationship if it's non-obvious
- Include context about the source or evidence
- Example: "Einstein — developed → Theory of Relativity (1905)"
"""

DEFAULT_COWRITE_STYLE_UNIT = """# Unit Style Guide

## Format
- Use SI base units as the foundation
- Include conversion factors for non-SI units
- Group related units together

## Labels
- Full name as the primary label
- Abbreviation in parentheses
"""

DEFAULT_COWRITE_STYLE_REVIEW = """# Review Style Guide

## Focus
- Evaluate accuracy, consistency, and completeness of triples
- Flag missing labels or definitions
- Suggest improvements that align with existing graph conventions
"""

DEFAULT_COWRITE_STYLE_PROOF = """# Proof Style Guide

## Evidence
- Cite specific sources or reasoning steps
- Distinguish between direct evidence and inference
- Note confidence level when appropriate
"""

__all__ = [
    "_FORM_TYPE_TO_DOMAIN",
    "DEFAULT_COWRITE_STYLE",
    "DEFAULT_COWRITE_STYLE_NODE",
    "DEFAULT_COWRITE_STYLE_PREDICATE",
    "DEFAULT_COWRITE_STYLE_TRIPLE",
    "DEFAULT_COWRITE_STYLE_UNIT",
    "DEFAULT_COWRITE_STYLE_REVIEW",
    "DEFAULT_COWRITE_STYLE_PROOF",
]
