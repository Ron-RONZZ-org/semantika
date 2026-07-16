"""Seed data for Semantika built-in predicates and type nodes.

These define the application's core ontology: media/document/code type
hierarchy and the predicates that describe their relationships.

The predicate catalog is grouped into tiers:
  - **W3C** — standard RDF/RDFS/OWL predicates (never duplicated in ``sm:``)
  - **Tier 1** — core ``sm:`` predicates (soft-protected, always seeded)
  - **Tier 2** — extended ``sm:`` predicates (seeded, deletable)
  - **File** — file-attachment metadata predicates (internal, no stable IRI)
"""

from __future__ import annotations

# ── Built-in type nodes ─────────────────────────────────────────────────

BUILTIN_TYPE_NODES: list[dict] = [
    {
        "node_id": "PHOTO",
        "labels": {
            "en": "Photo",
            "eo": "Foto",
            "fr": "Photo",
        },
        "definitions": {
            "en": "A photographic image or picture",
            "eo": "Fotografia bildo",
        },
    },
    {
        "node_id": "VIDEO",
        "labels": {
            "en": "Video",
            "eo": "Filmeto",
            "fr": "Vidéo",
        },
        "definitions": {
            "en": "A video recording or moving image",
            "eo": "Videa registraĵo aŭ moviĝanta bildo",
        },
    },
    {
        "node_id": "DOCUMENT",
        "labels": {
            "en": "Document",
            "eo": "Dosiero",
            "fr": "Document",
        },
        "definitions": {
            "en": "An arbitrary file or document",
            "eo": "Ajna dosiero aŭ dokumento",
        },
    },
    {
        "node_id": "SOURCE_CODE",
        "labels": {
            "en": "Source code",
            "eo": "Komputika kodo",
            "fr": "Code source",
        },
        "definitions": {
            "en": "A source code snippet or software program",
            "eo": "Fontkoda fragmento aŭ programaro",
        },
    },
]

# ── Seed predicate entry type ───────────────────────────────────────────
# Each entry: (predicate_id, source, labels, descriptions)

SeedPredicate = tuple[str, str, dict[str, str], dict[str, str]]

# ── W3C standard predicates (never duplicated in sm:) ──────────────────

W3C_PREDICATES: list[SeedPredicate] = [
    (
        "rdf:type",
        "rdf",
        {"en": "type", "eo": "tipo"},
        {"en": "Is a type of", "eo": "Estas tipo de"},
    ),
    (
        "rdfs:subClassOf",
        "rdfs",
        {"en": "subclass of", "eo": "subklaso de"},
        {"en": "Is a subclass of", "eo": "Estas subklaso de"},
    ),
    (
        "rdfs:label",
        "rdfs",
        {"en": "label", "eo": "etikedo"},
        {"en": "Label for an entity", "eo": "Etikedo por ento"},
    ),
    (
        "owl:sameAs",
        "owl",
        {"en": "same as", "eo": "sama kiel"},
        {"en": "Same entity as", "eo": "Sama ento kiel"},
    ),
    (
        "owl:disjointWith",
        "owl",
        {"en": "disjoint from", "eo": "malapoga al"},
        {"en": "Disjoint from", "eo": "Malapoga al"},
    ),
    (
        "owl:inverseOf",
        "owl",
        {"en": "inverse of", "eo": "inverso de"},
        {"en": "Inverse property of", "eo": "Inversa eco de"},
    ),
    (
        "rdfs:seeAlso",
        "rdfs",
        {"en": "see also", "eo": "vidu ankau"},
        {"en": "Related resource", "eo": "Rilata rimedo"},
    ),
]

# ── Tier 1 — Core sm: predicates (soft-protected, always seeded) ───────

TIER1_SM_PREDICATES: list[SeedPredicate] = [
    (
        "sm:depicts",
        "semantika",
        {"en": "depicts", "eo": "priskribas", "fr": "dépeint"},
        {"en": "Subject depicts or shows the object (e.g. a photo showing a person)"},
    ),
    (
        "sm:programmingLanguage",
        "semantika",
        {"en": "programming language", "eo": "programlingvo", "fr": "langage de programmation"},
        {"en": "The programming language in which the subject (code) is written"},
    ),
    (
        "sm:theme",
        "semantika",
        {"en": "theme", "eo": "temo", "fr": "thème"},
        {"en": "Subject has the object as a theme or topic"},
    ),
    (
        "sm:dimension",
        "semantika",
        {"en": "dimension", "eo": "dimensio", "fr": "dimension"},
        {"en": "Dimensions of the subject media (e.g. 1920x1080)"},
    ),
    (
        "sm:canonicalLink",
        "semantika",
        {"en": "canonical link", "eo": "kanonika ligilo", "fr": "lien canonique"},
        {"en": "A canonical URL pointing to the original external resource"},
    ),
    (
        "sm:hasSource",
        "semantika",
        {"en": "source", "eo": "fonto", "fr": "source"},
        {"en": "Source URL or reference for imported knowledge"},
    ),
    (
        "sm:attributedTo",
        "semantika",
        {"en": "attributed to", "eo": "atribuita al", "fr": "attribué à"},
        {"en": "The subject fact or node is attributed to the object (person, source, tool)"},
    ),
    (
        "sm:partOf",
        "semantika",
        {"en": "part of", "eo": "parto de", "fr": "fait partie de"},
        {"en": "The subject is a part or member of the object (e.g. chapter partOf book)"},
    ),
]

# ── Tier 2 — Extended sm: predicates (seeded, deletable) ────────────────

TIER2_SM_PREDICATES: list[SeedPredicate] = [
    (
        "sm:isAbout",
        "semantika",
        {"en": "is about", "eo": "temas pri", "fr": "concerne"},
        {"en": "Broader subject relationship"},
    ),
    (
        "sm:relatesTo",
        "semantika",
        {"en": "relates to", "eo": "rilatas al", "fr": "se rapporte à"},
        {"en": "Generic bidirectional relationship between two entities"},
    ),
    (
        "sm:contradicts",
        "semantika",
        {"en": "contradicts", "eo": "kontraŭdiras", "fr": "contredit"},
        {"en": "Contradictory or conflicting knowledge assertion"},
    ),
    (
        "sm:requires",
        "semantika",
        {"en": "requires", "eo": "bezonas", "fr": "nécessite"},
        {"en": "Subject requires the object (dependency)"},
    ),
    (
        "sm:hasExample",
        "semantika",
        {"en": "has example", "eo": "havas ekzemplon", "fr": "a pour exemple"},
        {"en": "Subject has the object as an example"},
    ),
    (
        "sm:definedIn",
        "semantika",
        {"en": "defined in", "eo": "difinita en", "fr": "défini dans"},
        {"en": "Source document or file where a concept is defined"},
    ),
    (
        "sm:succeededBy",
        "semantika",
        {"en": "succeeded by", "eo": "sekvata de", "fr": "suivi par"},
        {"en": "Temporal succession — subject was succeeded by the object"},
    ),
    (
        "sm:precededBy",
        "semantika",
        {"en": "preceded by", "eo": "antaŭata de", "fr": "précédé par"},
        {"en": "Temporal precedence — subject was preceded by the object"},
    ),
    (
        "sm:similarTo",
        "semantika",
        {"en": "similar to", "eo": "simila al", "fr": "similaire à"},
        {"en": "Subject is similar to the object (non-identity similarity)"},
    ),
    (
        "sm:hasPart",
        "semantika",
        {"en": "has part", "eo": "havas parton", "fr": "a pour partie"},
        {"en": "Subject has the object as a part (inverse of sm:partOf)"},
    ),
]

# ── File attachment predicates (internal, no stable IRI) ──────────────

FILE_PREDICATES: list[SeedPredicate] = [
    (":hasFilePath", "manual", {"en": "file path", "eo": "dosiero-loko"},
     {"en": "Path to attached file"}),
    (":hasFileMime", "manual", {"en": "MIME type", "eo": "MIME-tipo"},
     {"en": "MIME type of attached file"}),
    (":hasFileSize", "manual", {"en": "file size", "eo": "grandeco"},
     {"en": "File size in bytes"}),
    (":hasFileSource", "manual", {"en": "file source", "eo": "fontindiko"},
     {"en": "Original source path or URL of attached file"}),
]

# ── Combined seed list (in order: W3C → Tier 1 → Tier 2 → File) ──────

SEED_PREDICATES: list[SeedPredicate] = (
    W3C_PREDICATES + TIER1_SM_PREDICATES + TIER2_SM_PREDICATES + FILE_PREDICATES
)

# ── Backward-compatible aliases (for existing imports) ─────────────────

BUILTIN_PREDICATES: list[SeedPredicate] = TIER1_SM_PREDICATES + TIER2_SM_PREDICATES

REQUIRED_PREDICATES: list[str] = [
    pid for pid, _, _, _ in BUILTIN_PREDICATES
] + [
    ":hasFilePath", ":hasFileMime", ":hasFileSize", ":hasFileSource",
]
