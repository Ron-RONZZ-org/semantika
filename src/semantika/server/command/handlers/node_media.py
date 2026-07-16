"""Media-type node creation subcommands (book, film, song, game, podcast).

These create semantically typed nodes with domain-specific metadata triples.
Unlike attachment subcommands, these have no file attachments — they create
pure semantic nodes with ``rdf:type`` and metadata predicates.

Accessible as::

    !node add media book|film|song|game|podcast
"""

from __future__ import annotations

import logging

from semantika.graph.db import get_services
from semantika.server.command.handlers.node_helpers import (
    create_typed_node,
    parse_duration,
    resolve_node_refs,
    split_literals,
)
from semantika.server.command.registry import command, group_command

logger = logging.getLogger(__name__)


# ── Group handler ──────────────────────────────────────────────────────────


@group_command("node.add.media", description="Create media-type nodes (book, film, song, game, podcast)")
def cmd_node_add_media_root(remaining: list[str], flags: dict[str, str]) -> dict:
    """Media node creation group — use subcommands.

    Available:
      !node add media book    — Create a book node
      !node add media film    — Create a film node
      !node add media song    — Create a song node
      !node add media game    — Create a computer game node
      !node add media podcast — Create a podcast node
    """
    return {"type": "status", "title": "Media Node Commands", "data": {
        "_summary": (
            "Available !node add media commands:\n"
            "  !node add media book    — Create a book node with ISBN, author, theme, year\n"
            "  !node add media film    — Create a film node with ISAN, director, producer, actor, duration, year\n"
            "  !node add media song    — Create a song node with ISWC, author, singer\n"
            "  !node add media game    — Create a computer game node with platform, genre, developer, publisher, year\n"
            "  !node add media podcast — Create a podcast node with host, episode-count, feed URL, language"
        )
    }}


# ── Book ───────────────────────────────────────────────────────────────────


@command("node.add.media.book",
         description="Create a book node with semantic metadata",
         interactive=True,
         flags=[
             {"name": "id", "type": "string",
              "help": "Explicit node ID (auto-derived from label if omitted)",
              "placeholder": "THE_GREAT_GATSBY"},
             {"name": "labels", "type": "string",
              "help": "Labels as LANG::TEXT pairs or JSON",
              "placeholder": "en::The Great Gatsby, fr::Gatsby le Magnifique"},
             {"name": "isbn", "type": "string",
              "help": "ISBN(s) (comma-separated for multiple editions)",
              "placeholder": "9780743273565, 9780684801520"},
             {"name": "author", "type": "string",
              "help": "Author node IDs (comma-separated)",
              "placeholder": "F_SCOTT_FITZGERALD"},
             {"name": "theme", "type": "string",
              "help": "Theme node IDs (comma-separated)",
              "placeholder": "AMERICAN_DREAM,WEALTH"},
             {"name": "year", "type": "string",
              "help": "Year of first publication",
              "placeholder": "1925"},
         ])
def cmd_node_add_book(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a book node with metadata triples.

    Auto-creates:
    - ``rdf:type`` triple to ``BOOK``
    - ``sm:hasISBN`` triple(s) for each comma-separated ISBN
    - ``sm:hasAuthor`` triple(s) for each author node ref
    - ``sm:theme`` triple(s) for each theme node ref
    - ``sm:publicationYear`` triple if ``--year`` is provided
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    explicit_id = flags.get("id", "")
    year = flags.get("year", "").strip()

    author_nodes = resolve_node_refs(svc, flags.get("author", "") or "", "author")
    theme_nodes = resolve_node_refs(svc, flags.get("theme", "") or "", "theme")
    isbns = split_literals(flags.get("isbn", "") or "")

    extra_fields: list[tuple[str, str, str, str]] = []

    for isbn in isbns:
        extra_fields.append(("sm:hasISBN", isbn, "literal", ""))
    for author_id in author_nodes:
        extra_fields.append(("sm:hasAuthor", author_id, "uri", ""))
    for theme_id in theme_nodes:
        extra_fields.append(("sm:theme", theme_id, "uri", ""))
    if year:
        extra_fields.append(("sm:publicationYear", year, "literal", ""))

    result = create_typed_node(svc, labels_raw, explicit_id, "BOOK", extra_fields)
    return {"type": "status", "data": result}


# ── Film ───────────────────────────────────────────────────────────────────


@command("node.add.media.film",
         description="Create a film node with semantic metadata",
         interactive=True,
         flags=[
             {"name": "id", "type": "string",
              "help": "Explicit node ID (auto-derived from label if omitted)",
              "placeholder": "INCEPTION"},
             {"name": "labels", "type": "string",
              "help": "Labels as LANG::TEXT pairs or JSON",
              "placeholder": "en::Inception"},
             {"name": "isan", "type": "string",
              "help": "ISAN(s) (comma-separated for different cuts)",
              "placeholder": "0000-0000-1C8A-0000-7-0000-0000-6"},
             {"name": "director", "type": "string",
              "help": "Director node IDs (comma-separated)",
              "placeholder": "CHRISTOPHER_NOLAN"},
             {"name": "producer", "type": "string",
              "help": "Producer node IDs (comma-separated)",
              "placeholder": "EMMA_THOMAS"},
             {"name": "actor", "type": "string",
              "help": "Actor node IDs (comma-separated)",
              "placeholder": "LEONARDO_DICAPRIO,ELLIOT_PAGE"},
             {"name": "duration", "type": "string",
              "help": "Duration(s) in HH:MM:SS (comma-separated for different cuts)",
              "placeholder": "02:28:00, 02:28:06"},
             {"name": "year", "type": "string",
              "help": "Year of release",
              "placeholder": "2010"},
         ])
def cmd_node_add_film(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a film node with metadata triples.

    Auto-creates:
    - ``rdf:type`` triple to ``FILM``
    - ``sm:hasISAN`` triple(s) for each comma-separated ISAN
    - ``sm:hasDirector`` triple(s) for each director node ref
    - ``sm:hasProducer`` triple(s) for each producer node ref
    - ``sm:hasActor`` triple(s) for each actor node ref
    - ``sm:hasDuration`` triple for each parsed duration (in seconds)
    - ``sm:publicationYear`` triple if ``--year`` is provided
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    explicit_id = flags.get("id", "")
    year = flags.get("year", "").strip()

    director_nodes = resolve_node_refs(svc, flags.get("director", "") or "", "director")
    producer_nodes = resolve_node_refs(svc, flags.get("producer", "") or "", "producer")
    actor_nodes = resolve_node_refs(svc, flags.get("actor", "") or "", "actor")
    isans = split_literals(flags.get("isan", "") or "")
    durations_raw = split_literals(flags.get("duration", "") or "")

    extra_fields: list[tuple[str, str, str, str]] = []

    for isan in isans:
        extra_fields.append(("sm:hasISAN", isan, "literal", ""))
    for director_id in director_nodes:
        extra_fields.append(("sm:hasDirector", director_id, "uri", ""))
    for producer_id in producer_nodes:
        extra_fields.append(("sm:hasProducer", producer_id, "uri", ""))
    for actor_id in actor_nodes:
        extra_fields.append(("sm:hasActor", actor_id, "uri", ""))
    for dur in durations_raw:
        seconds = parse_duration(dur)
        if seconds:
            extra_fields.append(("sm:hasDuration", seconds, "literal", "xsd:integer"))
    if year:
        extra_fields.append(("sm:publicationYear", year, "literal", ""))

    result = create_typed_node(svc, labels_raw, explicit_id, "FILM", extra_fields)
    return {"type": "status", "data": result}


# ── Song ───────────────────────────────────────────────────────────────────


@command("node.add.media.song",
         description="Create a song node with semantic metadata",
         interactive=True,
         flags=[
             {"name": "id", "type": "string",
              "help": "Explicit node ID (auto-derived from label if omitted)",
              "placeholder": "BOHEMIAN_RHAPSODY"},
             {"name": "labels", "type": "string",
              "help": "Labels as LANG::TEXT pairs or JSON",
              "placeholder": "en::Bohemian Rhapsody"},
             {"name": "iswc", "type": "string",
              "help": "ISWC(s) (comma-separated)",
              "placeholder": "T-010.101.929-7"},
             {"name": "author", "type": "string",
              "help": "Author/composer node IDs (comma-separated)",
              "placeholder": "FREDDIE_MERCURY"},
             {"name": "singer", "type": "string",
              "help": "Singer/performer node IDs (comma-separated)",
              "placeholder": "FREDDIE_MERCURY"},
         ])
def cmd_node_add_song(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a song node with metadata triples.

    Auto-creates:
    - ``rdf:type`` triple to ``SONG``
    - ``sm:hasISWC`` triple(s) for each comma-separated ISWC
    - ``sm:hasAuthor`` triple(s) for each author/composer node ref
    - ``sm:hasSinger`` triple(s) for each singer/performer node ref
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    explicit_id = flags.get("id", "")

    author_nodes = resolve_node_refs(svc, flags.get("author", "") or "", "author")
    singer_nodes = resolve_node_refs(svc, flags.get("singer", "") or "", "singer")
    iswcs = split_literals(flags.get("iswc", "") or "")

    extra_fields: list[tuple[str, str, str, str]] = []

    for iswc in iswcs:
        extra_fields.append(("sm:hasISWC", iswc, "literal", ""))
    for author_id in author_nodes:
        extra_fields.append(("sm:hasAuthor", author_id, "uri", ""))
    for singer_id in singer_nodes:
        extra_fields.append(("sm:hasSinger", singer_id, "uri", ""))

    result = create_typed_node(svc, labels_raw, explicit_id, "SONG", extra_fields)
    return {"type": "status", "data": result}


# ── Game ───────────────────────────────────────────────────────────────────


@command("node.add.media.game",
         description="Create a computer game node with semantic metadata",
         interactive=True,
         flags=[
             {"name": "id", "type": "string",
              "help": "Explicit node ID (auto-derived from label if omitted)",
              "placeholder": "THE_WITCHER_3"},
             {"name": "labels", "type": "string",
              "help": "Labels as LANG::TEXT pairs or JSON",
              "placeholder": "en::The Witcher 3: Wild Hunt"},
             {"name": "platform", "type": "string",
              "help": "Platform(s) (comma-separated)",
              "placeholder": "PC, PS5, Xbox Series X"},
             {"name": "genre", "type": "string",
              "help": "Genre(s) (comma-separated)",
              "placeholder": "RPG, Open World"},
             {"name": "developer", "type": "string",
              "help": "Developer node IDs (comma-separated)",
              "placeholder": "CD_PROJEKT_RED"},
             {"name": "publisher", "type": "string",
              "help": "Publisher node IDs (comma-separated)",
              "placeholder": "CD_PROJEKT"},
             {"name": "year", "type": "string",
              "help": "Year of release",
              "placeholder": "2015"},
         ])
def cmd_node_add_game(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a computer game node with metadata triples.

    Auto-creates:
    - ``rdf:type`` triple to ``GAME``
    - ``sm:platform`` triple(s) for each comma-separated platform
    - ``sm:genre`` triple(s) for each comma-separated genre
    - ``sm:developedBy`` triple(s) for each developer node ref
    - ``sm:publishedBy`` triple(s) for each publisher node ref
    - ``sm:publicationYear`` triple if ``--year`` is provided
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    explicit_id = flags.get("id", "")
    year = flags.get("year", "").strip()

    developer_nodes = resolve_node_refs(svc, flags.get("developer", "") or "", "developer")
    publisher_nodes = resolve_node_refs(svc, flags.get("publisher", "") or "", "publisher")
    platforms = split_literals(flags.get("platform", "") or "")
    genres = split_literals(flags.get("genre", "") or "")

    extra_fields: list[tuple[str, str, str, str]] = []

    for platform in platforms:
        extra_fields.append(("sm:platform", platform, "literal", ""))
    for genre in genres:
        extra_fields.append(("sm:genre", genre, "literal", ""))
    for dev_id in developer_nodes:
        extra_fields.append(("sm:developedBy", dev_id, "uri", ""))
    for pub_id in publisher_nodes:
        extra_fields.append(("sm:publishedBy", pub_id, "uri", ""))
    if year:
        extra_fields.append(("sm:publicationYear", year, "literal", ""))

    result = create_typed_node(svc, labels_raw, explicit_id, "GAME", extra_fields)
    return {"type": "status", "data": result}


# ── Podcast ────────────────────────────────────────────────────────────────


@command("node.add.media.podcast",
         description="Create a podcast node with semantic metadata",
         interactive=True,
         flags=[
             {"name": "id", "type": "string",
              "help": "Explicit node ID (auto-derived from label if omitted)",
              "placeholder": "HARDCORE_HISTORY"},
             {"name": "labels", "type": "string",
              "help": "Labels as LANG::TEXT pairs or JSON",
              "placeholder": "en::Hardcore History"},
             {"name": "host", "type": "string",
              "help": "Host node IDs (comma-separated)",
              "placeholder": "DAN_CARLIN"},
             {"name": "episode-count", "type": "string",
              "help": "Total number of episodes",
              "placeholder": "75"},
             {"name": "feed-url", "type": "string",
              "help": "RSS/Atom feed URL",
              "placeholder": "https://feeds.feedburner.com/dancarlin/history"},
             {"name": "language", "type": "string",
              "help": "Language code",
              "placeholder": "en"},
         ])
def cmd_node_add_podcast(remaining: list[str], flags: dict[str, str]) -> dict:
    """Create a podcast node with metadata triples.

    Auto-creates:
    - ``rdf:type`` triple to ``PODCAST``
    - ``sm:hasHost`` triple(s) for each host node ref
    - ``sm:episodeCount`` triple if ``--episode-count`` is provided
    - ``sm:feedURL`` triple if ``--feed-url`` is provided
    - ``sm:language`` triple if ``--language`` is provided
    """
    svc = get_services()
    labels_raw = flags.get("labels") or (remaining[0] if remaining else "")
    explicit_id = flags.get("id", "")

    host_nodes = resolve_node_refs(svc, flags.get("host", "") or "", "host")
    episode_count = (flags.get("episode-count") or "").strip()
    feed_url = (flags.get("feed-url") or "").strip()
    language = (flags.get("language") or "").strip()

    extra_fields: list[tuple[str, str, str, str]] = []

    for host_id in host_nodes:
        extra_fields.append(("sm:hasHost", host_id, "uri", ""))
    if episode_count:
        extra_fields.append(("sm:episodeCount", episode_count, "literal", "xsd:integer"))
    if feed_url:
        extra_fields.append(("sm:feedURL", feed_url, "literal", ""))
    if language:
        extra_fields.append(("sm:language", language, "literal", ""))

    result = create_typed_node(svc, labels_raw, explicit_id, "PODCAST", extra_fields)
    return {"type": "status", "data": result}
