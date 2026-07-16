"""Seed data for Semantika built-in predicates and type nodes.

These define the application's core ontology: media/document/code type
hierarchy and the predicates that describe their relationships.
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
    # ── Media type nodes ─────────────────────────────────────────────
    {
        "node_id": "BOOK",
        "labels": {"en": "Book", "eo": "Libro", "fr": "Livre"},
        "definitions": {"en": "A published written work", "eo": "Publikigita skribita verko"},
    },
    {
        "node_id": "FILM",
        "labels": {"en": "Film", "eo": "Filmo", "fr": "Film"},
        "definitions": {"en": "A motion picture or movie", "eo": "Kino aŭ movbildo"},
    },
    {
        "node_id": "SONG",
        "labels": {"en": "Song", "eo": "Kanto", "fr": "Chanson"},
        "definitions": {"en": "A musical composition with or without lyrics", "eo": "Muzika komponaĵo kun aŭ sen tekstoj"},
    },
    {
        "node_id": "GAME",
        "labels": {"en": "Game", "eo": "Ludo", "fr": "Jeu"},
        "definitions": {"en": "An interactive digital or tabletop game", "eo": "Interaga cifereca aŭ tabloludo"},
    },
    {
        "node_id": "PODCAST",
        "labels": {"en": "Podcast", "eo": "Podkasto", "fr": "Podcast"},
        "definitions": {"en": "An episodic series of digital audio files", "eo": "Epizoda serio de ciferecaj audio-dosieroj"},
    },
    # ── Scholarly type nodes ─────────────────────────────────────────
    {
        "node_id": "PAPER",
        "labels": {"en": "Paper", "eo": "Artikolo", "fr": "Article"},
        "definitions": {"en": "An academic or scholarly article", "eo": "Akademia aŭ scienca artikolo"},
    },
    {
        "node_id": "PATENT",
        "labels": {"en": "Patent", "eo": "Patento", "fr": "Brevet"},
        "definitions": {"en": "A granted patent or patent application", "eo": "Aljuĝita patento aŭ patentpeto"},
    },
    {
        "node_id": "CONFERENCE",
        "labels": {"en": "Conference", "eo": "Konferenco", "fr": "Conférence"},
        "definitions": {"en": "An academic or industry conference", "eo": "Akademia aŭ industria konferenco"},
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
    # ── Media predicates ─────────────────────────────────────────────
    (
        "sm:hasISBN",
        "semantika",
        {"en": "ISBN", "eo": "ISBN", "fr": "ISBN"},
        {"en": "International Standard Book Number", "eo": "Internacia Norma Libronumero"},
    ),
    (
        "sm:hasAuthor",
        "semantika",
        {"en": "author", "eo": "aŭtoro", "fr": "auteur"},
        {"en": "The author of a creative or scholarly work", "eo": "La aŭtoro de kreiva aŭ akademia verko"},
    ),
    (
        "sm:hasDirector",
        "semantika",
        {"en": "director", "eo": "reĝisoro", "fr": "réalisateur"},
        {"en": "The director of a film or video work", "eo": "La reĝisoro de filmo aŭ videa verko"},
    ),
    (
        "sm:hasProducer",
        "semantika",
        {"en": "producer", "eo": "produktoro", "fr": "producteur"},
        {"en": "The producer of a media work", "eo": "La produktoro de amaskomunikila verko"},
    ),
    (
        "sm:hasActor",
        "semantika",
        {"en": "actor", "eo": "aktoro", "fr": "acteur"},
        {"en": "An actor appearing in a film or video work", "eo": "Aktoro aperanta en filmo aŭ videa verko"},
    ),
    (
        "sm:hasSinger",
        "semantika",
        {"en": "singer", "eo": "kantisto", "fr": "chanteur"},
        {"en": "The singer or vocal performer of a song", "eo": "La kantisto aŭ voĉa prezentisto de kanto"},
    ),
    (
        "sm:hasDuration",
        "semantika",
        {"en": "duration", "eo": "daŭro", "fr": "durée"},
        {"en": "Duration in seconds of a media work", "eo": "Daŭro en sekundoj de amaskomunikila verko"},
    ),
    (
        "sm:hasISAN",
        "semantika",
        {"en": "ISAN", "eo": "ISAN", "fr": "ISAN"},
        {"en": "International Standard Audiovisual Number", "eo": "Internacia Norma Aŭdvidia Numero"},
    ),
    (
        "sm:hasISWC",
        "semantika",
        {"en": "ISWC", "eo": "ISWC", "fr": "ISWC"},
        {"en": "International Standard Musical Work Code", "eo": "Internacia Norma Muzika Verkkodo"},
    ),
    (
        "sm:publicationYear",
        "semantika",
        {"en": "publication year", "eo": "publikiga jaro", "fr": "année de publication"},
        {"en": "The year a work was first published", "eo": "La jaro kiam verko unue publikiĝis"},
    ),
    (
        "sm:platform",
        "semantika",
        {"en": "platform", "eo": "platformo", "fr": "plateforme"},
        {"en": "The platform or system a game runs on", "eo": "La platformo aŭ sistemo sur kiu ludo funkcias"},
    ),
    (
        "sm:genre",
        "semantika",
        {"en": "genre", "eo": "ĝenro", "fr": "genre"},
        {"en": "The genre of a creative work", "eo": "La ĝenro de kreiva verko"},
    ),
    (
        "sm:developedBy",
        "semantika",
        {"en": "developed by", "eo": "disvolvita de", "fr": "développé par"},
        {"en": "The developer of a software or game work", "eo": "La disvolvanto de programaro aŭ ludo"},
    ),
    (
        "sm:publishedBy",
        "semantika",
        {"en": "published by", "eo": "eldonita de", "fr": "publié par"},
        {"en": "The publisher of a work", "eo": "La eldonanto de verko"},
    ),
    (
        "sm:episodeCount",
        "semantika",
        {"en": "episode count", "eo": "epizoda nombro", "fr": "nombre d'épisodes"},
        {"en": "Number of episodes in a podcast series", "eo": "Nombro de epizodoj en podkasta serio"},
    ),
    (
        "sm:hasHost",
        "semantika",
        {"en": "host", "eo": "gastiganto", "fr": "animateur"},
        {"en": "The host of a podcast or event", "eo": "La gastiganto de podkasto aŭ evento"},
    ),
    (
        "sm:feedURL",
        "semantika",
        {"en": "feed URL", "eo": "fluo URL", "fr": "URL du flux"},
        {"en": "The RSS or Atom feed URL for a podcast", "eo": "La RSS aŭ Atom fluo URL por podkasto"},
    ),
    # ── Scholarly predicates ──────────────────────────────────────────
    (
        "sm:hasDOI",
        "semantika",
        {"en": "DOI", "eo": "DOI", "fr": "DOI"},
        {"en": "Digital Object Identifier", "eo": "Cifereca Objekta Identigilo"},
    ),
    (
        "sm:publishedIn",
        "semantika",
        {"en": "published in", "eo": "eldonita en", "fr": "publié dans"},
        {"en": "The journal or venue where a work was published", "eo": "La revuo aŭ loko kie verko estis publikigita"},
    ),
    (
        "sm:hasKeyword",
        "semantika",
        {"en": "keyword", "eo": "ŝlosilvorto", "fr": "mot-clé"},
        {"en": "A keyword or tag describing the subject", "eo": "Ŝlosilvorto aŭ etikedo priskribanta la temon"},
    ),
    (
        "sm:hasURL",
        "semantika",
        {"en": "URL", "eo": "URL", "fr": "URL"},
        {"en": "A URL pointing to an external resource", "eo": "URL indikanta eksteran rimedon"},
    ),
    (
        "sm:hasPatentNumber",
        "semantika",
        {"en": "patent number", "eo": "patenta numero", "fr": "numéro de brevet"},
        {"en": "The official patent number", "eo": "La oficiala patentnumero"},
    ),
    (
        "sm:hasInventor",
        "semantika",
        {"en": "inventor", "eo": "inventisto", "fr": "inventeur"},
        {"en": "The inventor of a patented invention", "eo": "La inventinto de patentita invento"},
    ),
    (
        "sm:assignedTo",
        "semantika",
        {"en": "assigned to", "eo": "asignita al", "fr": "attribué à"},
        {"en": "The entity to which a patent is assigned", "eo": "La ento al kiu patento estas asignita"},
    ),
    (
        "sm:conferenceSeries",
        "semantika",
        {"en": "conference series", "eo": "konferenca serio", "fr": "série de conférences"},
        {"en": "The series name of a conference (e.g. ICSE, CHI)", "eo": "La seria nomo de konferenco"},
    ),
    (
        "sm:location",
        "semantika",
        {"en": "location", "eo": "loko", "fr": "lieu"},
        {"en": "A geographic location associated with the subject", "eo": "Geografia loko asociita kun la subjekto"},
    ),
]

# Predicate IDs that the builtin service must ensure exist before
# any specialised node-add command runs.
REQUIRED_PREDICATES: list[str] = [
    pid for pid, _, _, _ in BUILTIN_PREDICATES
] + [
    ":hasFilePath", ":hasFileMime", ":hasFileSize", ":hasFileSource",
]
