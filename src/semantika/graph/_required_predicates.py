"""Python fallback for required predicates.

When a required predicate is missing from the YAML seed files
(``builtins.yaml``, ``units.yaml``), the system falls back to these
hardcoded values and emits a warning.

This ensures that even if a non-coder editor accidentally deletes
a predicate from YAML, built-in commands continue to function.

The canonical source of truth is the YAML files.  This file exists
only as a safety net (the "belt" in the belt-and-suspenders design).
"""

from __future__ import annotations

from typing import TypedDict


class SeedPredicate(TypedDict, total=False):
    """Structure of a seed predicate entry in the fallback."""
    source: str
    labels: dict[str, str]
    descriptions: dict[str, str]


# ── All required predicates ────────────────────────────────────────────
# Keyed by predicate_id.  Every predicate that a built-in command
# references by name MUST be listed here.

REQUIRED_PREDICATES: dict[str, SeedPredicate] = {
    # ── W3C ────────────────────────────────────────────────────────────
    "rdf:type": {
        "source": "rdf",
        "labels": {"en": "type", "eo": "tipo"},
        "descriptions": {"en": "Is a type of", "eo": "Estas tipo de"},
    },
    "rdfs:subClassOf": {
        "source": "rdfs",
        "labels": {"en": "subclass of", "eo": "subklaso de"},
        "descriptions": {"en": "Is a subclass of", "eo": "Estas subklaso de"},
    },
    "rdfs:label": {
        "source": "rdfs",
        "labels": {"en": "label", "eo": "etikedo"},
        "descriptions": {"en": "Label for an entity", "eo": "Etikedo por ento"},
    },
    "owl:sameAs": {
        "source": "owl",
        "labels": {"en": "same as", "eo": "sama kiel"},
        "descriptions": {"en": "Same entity as", "eo": "Sama ento kiel"},
    },
    "owl:disjointWith": {
        "source": "owl",
        "labels": {"en": "disjoint from", "eo": "malapoga al"},
        "descriptions": {"en": "Disjoint from", "eo": "Malapoga al"},
    },
    "owl:inverseOf": {
        "source": "owl",
        "labels": {"en": "inverse of", "eo": "inverso de"},
        "descriptions": {"en": "Inverse property of", "eo": "Inversa eco de"},
    },
    "rdfs:seeAlso": {
        "source": "rdfs",
        "labels": {"en": "see also", "eo": "vidu ankau"},
        "descriptions": {"en": "Related resource", "eo": "Rilata rimedo"},
    },
    # ── Tier 1 — Core sm: ──────────────────────────────────────────────
    "sm:depicts": {
        "source": "semantika",
        "labels": {"en": "depicts", "eo": "priskribas", "fr": "dépeint"},
        "descriptions": {"en": "Subject depicts or shows the object (e.g. a photo showing a person)"},
    },
    "sm:programmingLanguage": {
        "source": "semantika",
        "labels": {"en": "programming language", "eo": "programlingvo", "fr": "langage de programmation"},
        "descriptions": {"en": "The programming language in which the subject (code) is written"},
    },
    "sm:theme": {
        "source": "semantika",
        "labels": {"en": "theme", "eo": "temo", "fr": "thème"},
        "descriptions": {"en": "Subject has the object as a theme or topic"},
    },
    "sm:dimension": {
        "source": "semantika",
        "labels": {"en": "dimension", "eo": "dimensio", "fr": "dimension"},
        "descriptions": {"en": "Dimensions of the subject media (e.g. 1920x1080)"},
    },
    "sm:canonicalLink": {
        "source": "semantika",
        "labels": {"en": "canonical link", "eo": "kanonika ligilo", "fr": "lien canonique"},
        "descriptions": {"en": "A canonical URL pointing to the original external resource"},
    },
    "sm:hasSource": {
        "source": "semantika",
        "labels": {"en": "source", "eo": "fonto", "fr": "source"},
        "descriptions": {"en": "Source URL or reference for imported knowledge"},
    },
    "sm:attributedTo": {
        "source": "semantika",
        "labels": {"en": "attributed to", "eo": "atribuita al", "fr": "attribué à"},
        "descriptions": {"en": "The subject fact or node is attributed to the object (person, source, tool)"},
    },
    "sm:partOf": {
        "source": "semantika",
        "labels": {"en": "part of", "eo": "parto de", "fr": "fait partie de"},
        "descriptions": {"en": "The subject is a part or member of the object (e.g. chapter partOf book)"},
    },
    # ── Media predicates ───────────────────────────────────────────────
    "sm:hasISBN": {
        "source": "semantika",
        "labels": {"en": "ISBN", "eo": "ISBN", "fr": "ISBN"},
        "descriptions": {"en": "International Standard Book Number", "eo": "Internacia Norma Libronumero"},
    },
    "sm:hasAuthor": {
        "source": "semantika",
        "labels": {"en": "author", "eo": "aŭtoro", "fr": "auteur"},
        "descriptions": {"en": "The author of a creative or scholarly work", "eo": "La aŭtoro de kreiva aŭ akademia verko"},
    },
    "sm:hasDirector": {
        "source": "semantika",
        "labels": {"en": "director", "eo": "reĝisoro", "fr": "réalisateur"},
        "descriptions": {"en": "The director of a film or video work", "eo": "La reĝisoro de filmo aŭ videa verko"},
    },
    "sm:hasProducer": {
        "source": "semantika",
        "labels": {"en": "producer", "eo": "produktoro", "fr": "producteur"},
        "descriptions": {"en": "The producer of a media work", "eo": "La produktoro de amaskomunikila verko"},
    },
    "sm:hasActor": {
        "source": "semantika",
        "labels": {"en": "actor", "eo": "aktoro", "fr": "acteur"},
        "descriptions": {"en": "An actor appearing in a film or video work", "eo": "Aktoro aperanta en filmo aŭ videa verko"},
    },
    "sm:hasSinger": {
        "source": "semantika",
        "labels": {"en": "singer", "eo": "kantisto", "fr": "chanteur"},
        "descriptions": {"en": "The singer or vocal performer of a song", "eo": "La kantisto aŭ voĉa prezentisto de kanto"},
    },
    "sm:hasDuration": {
        "source": "semantika",
        "labels": {"en": "duration", "eo": "daŭro", "fr": "durée"},
        "descriptions": {"en": "Duration in seconds of a media work", "eo": "Daŭro en sekundoj de amaskomunikila verko"},
    },
    "sm:hasISAN": {
        "source": "semantika",
        "labels": {"en": "ISAN", "eo": "ISAN", "fr": "ISAN"},
        "descriptions": {"en": "International Standard Audiovisual Number", "eo": "Internacia Norma Aŭdvidia Numero"},
    },
    "sm:hasISWC": {
        "source": "semantika",
        "labels": {"en": "ISWC", "eo": "ISWC", "fr": "ISWC"},
        "descriptions": {"en": "International Standard Musical Work Code", "eo": "Internacia Norma Muzika Verkkodo"},
    },
    "sm:publicationYear": {
        "source": "semantika",
        "labels": {"en": "publication year", "eo": "publikiga jaro", "fr": "année de publication"},
        "descriptions": {"en": "The year a work was first published", "eo": "La jaro kiam verko unue publikiĝis"},
    },
    "sm:platform": {
        "source": "semantika",
        "labels": {"en": "platform", "eo": "platformo", "fr": "plateforme"},
        "descriptions": {"en": "The platform or system a game runs on", "eo": "La platformo aŭ sistemo sur kiu ludo funkcias"},
    },
    "sm:genre": {
        "source": "semantika",
        "labels": {"en": "genre", "eo": "ĝenro", "fr": "genre"},
        "descriptions": {"en": "The genre of a creative work", "eo": "La ĝenro de kreiva verko"},
    },
    "sm:developedBy": {
        "source": "semantika",
        "labels": {"en": "developed by", "eo": "disvolvita de", "fr": "développé par"},
        "descriptions": {"en": "The developer of a software or game work", "eo": "La disvolvanto de programaro aŭ ludo"},
    },
    "sm:publishedBy": {
        "source": "semantika",
        "labels": {"en": "published by", "eo": "eldonita de", "fr": "publié par"},
        "descriptions": {"en": "The publisher of a work", "eo": "La eldonanto de verko"},
    },
    "sm:episodeCount": {
        "source": "semantika",
        "labels": {"en": "episode count", "eo": "epizoda nombro", "fr": "nombre d'épisodes"},
        "descriptions": {"en": "Number of episodes in a podcast series", "eo": "Nombro de epizodoj en podkasta serio"},
    },
    "sm:hasHost": {
        "source": "semantika",
        "labels": {"en": "host", "eo": "gastiganto", "fr": "animateur"},
        "descriptions": {"en": "The host of a podcast or event", "eo": "La gastiganto de podkasto aŭ evento"},
    },
    "sm:feedURL": {
        "source": "semantika",
        "labels": {"en": "feed URL", "eo": "fluo URL", "fr": "URL du flux"},
        "descriptions": {"en": "The RSS or Atom feed URL for a podcast", "eo": "La RSS aŭ Atom fluo URL por podkasto"},
    },
    # ── Scholarly predicates ───────────────────────────────────────────
    "sm:hasDOI": {
        "source": "semantika",
        "labels": {"en": "DOI", "eo": "DOI", "fr": "DOI"},
        "descriptions": {"en": "Digital Object Identifier", "eo": "Cifereca Objekta Identigilo"},
    },
    "sm:publishedIn": {
        "source": "semantika",
        "labels": {"en": "published in", "eo": "eldonita en", "fr": "publié dans"},
        "descriptions": {"en": "The journal or venue where a work was published", "eo": "La revuo aŭ loko kie verko estis publikigita"},
    },
    "sm:hasKeyword": {
        "source": "semantika",
        "labels": {"en": "keyword", "eo": "ŝlosilvorto", "fr": "mot-clé"},
        "descriptions": {"en": "A keyword or tag describing the subject", "eo": "Ŝlosilvorto aŭ etikedo priskribanta la temon"},
    },
    "sm:hasURL": {
        "source": "semantika",
        "labels": {"en": "URL", "eo": "URL", "fr": "URL"},
        "descriptions": {"en": "A URL pointing to an external resource", "eo": "URL indikanta eksteran rimedon"},
    },
    "sm:hasPatentNumber": {
        "source": "semantika",
        "labels": {"en": "patent number", "eo": "patenta numero", "fr": "numéro de brevet"},
        "descriptions": {"en": "The official patent number", "eo": "La oficiala patentnumero"},
    },
    "sm:hasInventor": {
        "source": "semantika",
        "labels": {"en": "inventor", "eo": "inventisto", "fr": "inventeur"},
        "descriptions": {"en": "The inventor of a patented invention", "eo": "La inventinto de patentita invento"},
    },
    "sm:assignedTo": {
        "source": "semantika",
        "labels": {"en": "assigned to", "eo": "asignita al", "fr": "attribué à"},
        "descriptions": {"en": "The entity to which a patent is assigned", "eo": "La ento al kiu patento estas asignita"},
    },
    "sm:conferenceSeries": {
        "source": "semantika",
        "labels": {"en": "conference series", "eo": "konferenca serio", "fr": "série de conférences"},
        "descriptions": {"en": "The series name of a conference (e.g. ICSE, CHI)", "eo": "La seria nomo de konferenco"},
    },
    "sm:location": {
        "source": "semantika",
        "labels": {"en": "location", "eo": "loko", "fr": "lieu"},
        "descriptions": {"en": "A geographic location associated with the subject", "eo": "Geografia loko asociita kun la subjekto"},
    },
    "sm:language": {
        "source": "semantika",
        "labels": {"en": "language", "eo": "lingvo", "fr": "langue"},
        "descriptions": {"en": "The language of a creative or scholarly work", "eo": "La lingvo de kreiva aŭ akademia verko"},
    },
    # ── Tier 2 — Extended sm: ──────────────────────────────────────────
    "sm:isAbout": {
        "source": "semantika",
        "labels": {"en": "is about", "eo": "temas pri", "fr": "concerne"},
        "descriptions": {"en": "Broader subject relationship"},
    },
    "sm:relatesTo": {
        "source": "semantika",
        "labels": {"en": "relates to", "eo": "rilatas al", "fr": "se rapporte à"},
        "descriptions": {"en": "Generic bidirectional relationship between two entities"},
    },
    "sm:contradicts": {
        "source": "semantika",
        "labels": {"en": "contradicts", "eo": "kontraŭdiras", "fr": "contredit"},
        "descriptions": {"en": "Contradictory or conflicting knowledge assertion"},
    },
    "sm:requires": {
        "source": "semantika",
        "labels": {"en": "requires", "eo": "bezonas", "fr": "nécessite"},
        "descriptions": {"en": "Subject requires the object (dependency)"},
    },
    "sm:hasExample": {
        "source": "semantika",
        "labels": {"en": "has example", "eo": "havas ekzemplon", "fr": "a pour exemple"},
        "descriptions": {"en": "Subject has the object as an example"},
    },
    "sm:definedIn": {
        "source": "semantika",
        "labels": {"en": "defined in", "eo": "difinita en", "fr": "défini dans"},
        "descriptions": {"en": "Source document or file where a concept is defined"},
    },
    "sm:succeededBy": {
        "source": "semantika",
        "labels": {"en": "succeeded by", "eo": "sekvata de", "fr": "suivi par"},
        "descriptions": {"en": "Temporal succession — subject was succeeded by the object"},
    },
    "sm:precededBy": {
        "source": "semantika",
        "labels": {"en": "preceded by", "eo": "antaŭata de", "fr": "précédé par"},
        "descriptions": {"en": "Temporal precedence — subject was preceded by the object"},
    },
    "sm:similarTo": {
        "source": "semantika",
        "labels": {"en": "similar to", "eo": "simila al", "fr": "similaire à"},
        "descriptions": {"en": "Subject is similar to the object (non-identity similarity)"},
    },
    "sm:hasPart": {
        "source": "semantika",
        "labels": {"en": "has part", "eo": "havas parton", "fr": "a pour partie"},
        "descriptions": {"en": "Subject has the object as a part (inverse of sm:partOf)"},
    },
    # ── File attachment predicates ──────────────────────────────────────
    ":hasFilePath": {
        "source": "manual",
        "labels": {"en": "file path", "eo": "dosiero-loko"},
        "descriptions": {"en": "Path to attached file", "eo": "Dosiero-loko por alkroĉita dosiero"},
    },
    ":hasFileMime": {
        "source": "manual",
        "labels": {"en": "MIME type", "eo": "MIME-tipo"},
        "descriptions": {"en": "MIME type of attached file", "eo": "MIME-tipo de alkroĉita dosiero"},
    },
    ":hasFileSize": {
        "source": "manual",
        "labels": {"en": "file size", "eo": "grandeco"},
        "descriptions": {"en": "File size in bytes", "eo": "Grandeco en bajtoj"},
    },
    ":hasFileSource": {
        "source": "manual",
        "labels": {"en": "file source", "eo": "fontindiko"},
        "descriptions": {"en": "Original source path or URL of attached file", "eo": "Origina fonta vojo aŭ URL de alkroĉita dosiero"},
    },
    # ── Unit predicates ────────────────────────────────────────────────
    ":symbol": {
        "source": "manual",
        "labels": {"en": "symbol", "eo": "simbolo"},
        "descriptions": {"en": "Unit symbol (e.g. m, kg, s)", "eo": "Unuosimbolo (ekz. m, kg, s)"},
    },
    ":ucumCode": {
        "source": "manual",
        "labels": {"en": "UCUM code", "eo": "UCUM-kodo"},
        "descriptions": {"en": "Unified Code for Units of Measure code", "eo": "Unuigita Kodo por Mezurunuoj"},
    },
    ":multiplier": {
        "source": "manual",
        "labels": {"en": "multiplier", "eo": "multiplikanto"},
        "descriptions": {"en": "Unit multiplier value", "eo": "Unuomultiplika valoro"},
    },
    ":offset": {
        "source": "manual",
        "labels": {"en": "offset", "eo": "deŝovo"},
        "descriptions": {"en": "Unit offset (e.g. for Celsius conversion)", "eo": "Unuodeŝovo (ekz. por celsia konvertiĝo)"},
    },
    ":hasBase": {
        "source": "manual",
        "labels": {"en": "has base", "eo": "havas bazon"},
        "descriptions": {"en": "Base unit of a compound power unit", "eo": "Baza unuo de kunmetita potenca unuo"},
    },
    ":hasExponent": {
        "source": "manual",
        "labels": {"en": "has exponent", "eo": "havas eksponenton"},
        "descriptions": {"en": "Exponent of a power unit", "eo": "Eksponento de potenca unuo"},
    },
    ":hasTerm1": {
        "source": "manual",
        "labels": {"en": "has term 1", "eo": "havas terminon 1"},
        "descriptions": {"en": "First term of a product unit", "eo": "Unua termino de produkta unuo"},
    },
    ":hasTerm2": {
        "source": "manual",
        "labels": {"en": "has term 2", "eo": "havas terminon 2"},
        "descriptions": {"en": "Second term of a product unit", "eo": "Dua termino de produkta unuo"},
    },
}

# ── Set of all required predicate IDs (for fast lookup) ─────────────────

REQUIRED_PREDICATE_IDS: frozenset[str] = frozenset(REQUIRED_PREDICATES.keys())
