"""Seed data for Semantika built-in predicates and type nodes.

These define the application's core ontology: media/document/code type
hierarchy and the predicates that describe their relationships.
"""

from __future__ import annotations

# ── Built-in type nodes ─────────────────────────────────────────────────

BUILTIN_TYPE_NODES: list[dict] = [
    {
        "node_id": "sm:Photo",
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
        "node_id": "sm:Video",
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
        "node_id": "sm:Document",
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
        "node_id": "sm:SourceCode",
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

# ── Built-in predicates ─────────────────────────────────────────────────

# Each tuple: (predicate_id, source, labels, descriptions)
BUILTIN_PREDICATES: list[tuple[str, str, dict[str, str], dict[str, str]]] = [
    (
        "sm:depicts",
        "semantika",
        {
            "en": "depicts",
            "eo": "priskribas",
            "fr": "dépeint",
        },
        {
            "en": "Subject depicts or shows the object (e.g. a photo showing a person)",
            "eo": "Subjekto priskribas aŭ montras la objekton",
        },
    ),
    (
        "sm:programmingLanguage",
        "semantika",
        {
            "en": "programming language",
            "eo": "programlingvo",
            "fr": "langage de programmation",
        },
        {
            "en": "The programming language in which the subject (code) is written",
            "eo": "La programlingvo en kiu la subjekto (kodo) estas skribita",
        },
    ),
    (
        "sm:theme",
        "semantika",
        {
            "en": "theme",
            "eo": "temo",
            "fr": "thème",
        },
        {
            "en": "Subject has the object as a theme or topic",
            "eo": "Subjekto havas la objekton kiel temon",
        },
    ),
    (
        "sm:dimension",
        "semantika",
        {
            "en": "dimension",
            "eo": "dimensio",
            "fr": "dimension",
        },
        {
            "en": "Dimensions of the subject media (e.g. 1920x1080)",
            "eo": "Dimensioj de la subjekta amaskomunikilo",
        },
    ),
    (
        "sm:canonicalLink",
        "semantika",
        {
            "en": "canonical link",
            "eo": "kanonika ligilo",
            "fr": "lien canonique",
        },
        {
            "en": "A canonical URL pointing to the original external resource",
            "eo": "Kanonika URL indikanta la originan eksteran rimedon",
        },
    ),
]

# Predicate IDs that the builtin service must ensure exist before
# any specialised node-add command runs.
REQUIRED_PREDICATES: list[str] = [
    pid for pid, _, _, _ in BUILTIN_PREDICATES
] + [
    ":hasFilePath", ":hasFileMime", ":hasFileSize", ":hasFileSource",
]
