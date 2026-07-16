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
