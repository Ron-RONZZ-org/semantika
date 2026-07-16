"""Scholarly-type node creation subcommands (paper, patent, conference).

These create semantically typed nodes with academic/IP metadata triples.
No file attachments — pure semantic nodes with ``rdf:type`` and metadata
predicates.

Accessible as::

    !node add scholarly paper|patent|conference
"""

from __future__ import annotations

import logging

from semantika.graph.db import get_services
from semantika.server.command.handlers.node_helpers import (
    create_typed_node,
    resolve_node_refs,
    split_literals,
)
from semantika.server.command.registry import command, group_command

logger = logging.getLogger(__name__)


# ── Group handler ──────────────────────────────────────────────────────────


@group_command("node.add.scholarly",
               description="Create scholarly-type nodes (paper, patent, conference)")
def cmd_node_add_scholarly_root(remaining: list[str], flags: dict[str, str]) -> dict:
    """Scholarly node creation group — use subcommands.

    Available:
      !node add scholarly paper       — Create an academic paper node
      !node add scholarly patent      — Create a patent node
      !node add scholarly conference  — Create a conference node
    """
    return {"type": "status", "title": "Scholarly Node Commands", "data": {
        "_summary": (
            "Available !node add scholarly commands:\n"
            "  !node add scholarly paper       — Create an academic paper with DOI, authors, journal, year, keywords\n"
            "  !node add scholarly patent      — Create a patent with patent number, inventor, year, assignee\n"
            "  !node add scholarly conference  — Create a conference with series, year, location, URL"
        )
    }}


# ── Paper ──────────────────────────────────────────────────────────────────


@command("node.add.scholarly.paper",
         description="Create an academic paper node with semantic metadata",
         interactive=True,
         flags=[
             {"name": "id", "type": "string",
              "help": "Explicit node ID (auto-derived from label if omitted)",
              "placeholder": "EINSTEIN_1905"},
             {"name": "labels", "type": "string",
              "help": "Labels as LANG::TEXT pairs or JSON",
              "placeholder": "en::On the Electrodynamics of Moving Bodies"},
             {"name": "doi", "type": "string",
              "help": "Digital Object Identifier",
              "placeholder": "10.1002/andp.19053221004"},
             {"name": "author", "type": "string",
              "help": "Author node IDs (comma-separated)",
              "placeholder": "ALBERT_EINSTEIN"},
             {"name": "journal", "type": "string",
              "help": "Journal or venue name",
              "placeholder": "Annalen der Physik"},
             {"name": "year", "type": "string",
              "help": "Year of publication",
              "placeholder": "1905"},
             {"name": "keywords", "type": "string",
              "help": "Keyword(s) (comma-separated)",
              "placeholder": "relativity, electrodynamics, special relativity"},
             {"name": "url", "type": "string",
              "help": "URL to the paper",
              "placeholder": "https://doi.org/10.1002/andp.19053221004"},
         ])
def cmd_node_add_paper(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create an academic paper node with metadata triples.

    Auto-creates:
    - ``rdf:type`` triple to ``PAPER``
    - ``sm:hasDOI`` triple with the DOI
    - ``sm:hasAuthor`` triple(s) for each author node ref
    - ``sm:publishedIn`` triple with the journal name
    - ``sm:publicationYear`` triple if ``--year`` is provided
    - ``sm:hasKeyword`` triple(s) for each comma-separated keyword
    - ``sm:hasURL`` triple if ``--url`` is provided
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    explicit_id = flags.get("id", "")
    doi = (flags.get("doi") or "").strip()
    journal = (flags.get("journal") or "").strip()
    year = (flags.get("year") or "").strip()
    url = (flags.get("url") or "").strip()

    author_nodes = resolve_node_refs(svc, flags.get("author", "") or "", "author")
    keywords = split_literals(flags.get("keywords", "") or "")

    extra_fields: list[tuple[str, str, str, str]] = []

    if doi:
        extra_fields.append(("sm:hasDOI", doi, "literal", ""))
    for author_id in author_nodes:
        extra_fields.append(("sm:hasAuthor", author_id, "node", ""))
    if journal:
        extra_fields.append(("sm:publishedIn", journal, "literal", ""))
    if year:
        extra_fields.append(("sm:publicationYear", year, "literal", ""))
    for kw in keywords:
        extra_fields.append(("sm:hasKeyword", kw, "literal", ""))
    if url:
        extra_fields.append(("sm:hasURL", url, "literal", ""))

    result = create_typed_node(svc, labels_raw, explicit_id, "PAPER", extra_fields)
    return {"type": "status", "data": result}


# ── Patent ─────────────────────────────────────────────────────────────────


@command("node.add.scholarly.patent",
         description="Create a patent node with semantic metadata",
         interactive=True,
         flags=[
             {"name": "id", "type": "string",
              "help": "Explicit node ID (auto-derived from label if omitted)",
              "placeholder": "US_PATENT_9876543"},
             {"name": "labels", "type": "string",
              "help": "Labels as LANG::TEXT pairs or JSON",
              "placeholder": "en::Method and system for... something"},
             {"name": "patent-number", "type": "string",
              "help": "Official patent number",
              "placeholder": "US9876543B2"},
             {"name": "inventor", "type": "string",
              "help": "Inventor node IDs (comma-separated)",
              "placeholder": "NIKOLA_TESLA"},
             {"name": "year", "type": "string",
              "help": "Year of grant or filing",
              "placeholder": "2023"},
             {"name": "assignee", "type": "string",
              "help": "Assignee node ID (organization or person)",
              "placeholder": "ACME_CORP"},
         ])
def cmd_node_add_patent(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a patent node with metadata triples.

    Auto-creates:
    - ``rdf:type`` triple to ``PATENT``
    - ``sm:hasPatentNumber`` triple with the patent number
    - ``sm:hasInventor`` triple(s) for each inventor node ref
    - ``sm:publicationYear`` triple if ``--year`` is provided
    - ``sm:assignedTo`` triple if ``--assignee`` is provided
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    explicit_id = flags.get("id", "")
    patent_number = (flags.get("patent-number") or "").strip()
    year = (flags.get("year") or "").strip()

    inventor_nodes = resolve_node_refs(svc, flags.get("inventor", "") or "", "inventor")
    assignee = (flags.get("assignee") or "").strip()
    assignee_node = resolve_node_refs(svc, assignee, "assignee") if assignee else []

    extra_fields: list[tuple[str, str, str, str]] = []

    if patent_number:
        extra_fields.append(("sm:hasPatentNumber", patent_number, "literal", ""))
    for inv_id in inventor_nodes:
        extra_fields.append(("sm:hasInventor", inv_id, "node", ""))
    if year:
        extra_fields.append(("sm:publicationYear", year, "literal", ""))
    for a_id in assignee_node:
        extra_fields.append(("sm:assignedTo", a_id, "node", ""))

    result = create_typed_node(svc, labels_raw, explicit_id, "PATENT", extra_fields)
    return {"type": "status", "data": result}


# ── Conference ──────────────────────────────────────────────────────────────


@command("node.add.scholarly.conference",
         description="Create a conference node with semantic metadata",
         interactive=True,
         flags=[
             {"name": "id", "type": "string",
              "help": "Explicit node ID (auto-derived from label if omitted)",
              "placeholder": "ICSE_2026"},
             {"name": "labels", "type": "string",
              "help": "Labels as LANG::TEXT pairs or JSON",
              "placeholder": "en::International Conference on Software Engineering 2026"},
             {"name": "series", "type": "string",
              "help": "Conference series name",
              "placeholder": "ICSE"},
             {"name": "year", "type": "string",
              "help": "Year of the conference",
              "placeholder": "2026"},
             {"name": "location", "type": "string",
              "help": "Host city or venue",
              "placeholder": "Pittsburgh, PA, USA"},
             {"name": "url", "type": "string",
              "help": "Conference website URL",
              "placeholder": "https://conf.researchr.org/home/icse-2026"},
         ])
def cmd_node_add_conference(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a conference node with metadata triples.

    Auto-creates:
    - ``rdf:type`` triple to ``CONFERENCE``
    - ``sm:conferenceSeries`` triple with the series name
    - ``sm:publicationYear`` triple if ``--year`` is provided
    - ``sm:location`` triple if ``--location`` is provided
    - ``sm:hasURL`` triple if ``--url`` is provided
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    explicit_id = flags.get("id", "")
    series = (flags.get("series") or "").strip()
    year = (flags.get("year") or "").strip()
    location = (flags.get("location") or "").strip()
    url = (flags.get("url") or "").strip()

    extra_fields: list[tuple[str, str, str, str]] = []

    if series:
        extra_fields.append(("sm:conferenceSeries", series, "literal", ""))
    if year:
        extra_fields.append(("sm:publicationYear", year, "literal", ""))
    if location:
        extra_fields.append(("sm:location", location, "literal", ""))
    if url:
        extra_fields.append(("sm:hasURL", url, "literal", ""))

    result = create_typed_node(svc, labels_raw, explicit_id, "CONFERENCE", extra_fields)
    return {"type": "status", "data": result}
