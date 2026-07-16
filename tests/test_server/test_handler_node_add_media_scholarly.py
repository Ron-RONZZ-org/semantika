"""Unit tests for media and scholarly node-add subcommands via dispatch().

Tests cover:
  - !node add media book|film|song|game|podcast
  - !node add scholarly paper|patent|conference
"""

from __future__ import annotations

import pytest

from semantika.server.command import handlers  # noqa: F401
from semantika.server.command.handlers import node_media  # noqa: F401
from semantika.server.command.handlers import node_scholarly  # noqa: F401
from semantika.server.command.registry import dispatch


@pytest.fixture
def seeded(services: dict) -> dict:
    """Create seed nodes for test dependencies."""
    ns = services["node"]
    ns.create({"node_id": "ALICE", "labels": {"en": "Alice"}})
    ns.create({"node_id": "BOB", "labels": {"en": "Bob"}})
    ns.create({"node_id": "NOLAN", "labels": {"en": "Christopher Nolan"}})
    ns.create({"node_id": "EINSTEIN", "labels": {"en": "Albert Einstein"}})
    ns.create({"node_id": "CD_PROJEKT", "labels": {"en": "CD Projekt"}})
    return services


# ── Helper unit tests ────────────────────────────────────────────────────


def test_create_typed_node_basic(services: dict):
    """create_typed_node should create a node with rdf:type."""
    from semantika.server.command.handlers.node_helpers import create_typed_node
    result = create_typed_node(services, "en::Test Book", "", "BOOK")
    assert result["node"] is not None
    assert "Created node" in result["message"]
    triples = result.get("semantic_triples", [])
    assert any(t["predicate_id"] == "rdf:type" and t["object_value"] == "BOOK" for t in triples)


def test_create_typed_node_with_extra_fields(services: dict):
    """create_typed_node should create extra semantic triples."""
    from semantika.server.command.handlers.node_helpers import create_typed_node
    extra = [("sm:publicationYear", "1925", "literal", "")]
    result = create_typed_node(services, "en::Gatsby", "", "BOOK", extra)
    triples = result.get("semantic_triples", [])
    assert any(t["predicate_id"] == "sm:publicationYear" for t in triples)


# ── !node add media book ─────────────────────────────────────────────────


class TestNodeAddBook:
    def test_book_basic(self, seeded: dict):
        """Basic book creation with labels."""
        result = dispatch(
            ["node", "add", "media", "book"],
            {"labels": "en::The Great Gatsby"},
        )
        assert result["type"] == "status"
        assert result["data"]["node"] is not None

    def test_book_with_author(self, seeded: dict):
        """Book with --author should create sm:hasAuthor triple."""
        result = dispatch(
            ["node", "add", "media", "book"],
            {"labels": "en::Gatsby", "author": "ALICE"},
        )
        assert result["type"] == "status"
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasAuthor" for t in triples)

    def test_book_with_isbn(self, seeded: dict):
        """Book with --isbn should create sm:hasISBN triple."""
        result = dispatch(
            ["node", "add", "media", "book"],
            {"labels": "en::Gatsby", "isbn": "9780743273565"},
        )
        assert result["type"] == "status"
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasISBN" for t in triples)

    def test_book_with_year(self, seeded: dict):
        """Book with --year should create sm:publicationYear triple."""
        result = dispatch(
            ["node", "add", "media", "book"],
            {"labels": "en::Gatsby", "year": "1925"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:publicationYear" for t in triples)

    def test_book_with_id(self, seeded: dict):
        """Book with --id should use given node ID."""
        result = dispatch(
            ["node", "add", "media", "book"],
            {"labels": "en::Gatsby", "id": "GATSBY"},
        )
        assert result["data"]["node"]["node_id"] == "GATSBY"

    def test_book_all_fields(self, seeded: dict):
        """Book with all fields simultaneously."""
        result = dispatch(
            ["node", "add", "media", "book"],
            {"labels": "en::Gatsby", "author": "ALICE,BOB",
             "isbn": "9780743273565, 9780684801520",
             "year": "1925"},
        )
        assert result["type"] == "status"
        triples = result["data"].get("semantic_triples", [])
        assert sum(1 for t in triples if t["predicate_id"] == "sm:hasAuthor") == 2
        assert sum(1 for t in triples if t["predicate_id"] == "sm:hasISBN") == 2
        assert any(t["predicate_id"] == "sm:publicationYear" for t in triples)
        assert any(t["predicate_id"] == "rdf:type" and t["object_value"] == "BOOK" for t in triples)

    def test_book_invalid_author(self, services: dict):
        """Book with unresolvable --author should raise."""
        with pytest.raises(Exception, match="not found"):
            dispatch(
                ["node", "add", "media", "book"],
                {"labels": "en::Gatsby", "author": "NONEXISTENT"},
            )


# ── !node add media film ─────────────────────────────────────────────────


class TestNodeAddFilm:
    def test_film_basic(self, seeded: dict):
        """Basic film creation."""
        result = dispatch(
            ["node", "add", "media", "film"],
            {"labels": "en::Inception"},
        )
        assert result["type"] == "status"

    def test_film_with_director(self, seeded: dict):
        """Film with --director should create sm:hasDirector triple."""
        result = dispatch(
            ["node", "add", "media", "film"],
            {"labels": "en::Inception", "director": "NOLAN"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasDirector" for t in triples)

    def test_film_with_duration(self, seeded: dict):
        """Film with --duration should create sm:hasDuration triple (seconds)."""
        result = dispatch(
            ["node", "add", "media", "film"],
            {"labels": "en::Inception", "duration": "02:28:00"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasDuration" and t["object_value"] == "8880" for t in triples)

    def test_film_with_duration_mmss(self, seeded: dict):
        """Film with --duration in MM:SS format."""
        result = dispatch(
            ["node", "add", "media", "film"],
            {"labels": "en::Short", "duration": "90:00"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasDuration" and t["object_value"] == "5400" for t in triples)

    def test_film_all_fields(self, seeded: dict):
        """Film with all fields simultaneously."""
        result = dispatch(
            ["node", "add", "media", "film"],
            {"labels": "en::Inception",
             "director": "NOLAN", "actor": "ALICE,BOB",
             "isan": "0000-0000-1C8A", "duration": "02:28:00",
             "year": "2010"},
        )
        assert result["type"] == "status"
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasDirector" for t in triples)
        assert sum(1 for t in triples if t["predicate_id"] == "sm:hasActor") == 2
        assert any(t["predicate_id"] == "sm:hasISAN" for t in triples)
        assert any(t["predicate_id"] == "sm:hasDuration" for t in triples)


# ── !node add media song ─────────────────────────────────────────────────


class TestNodeAddSong:
    def test_song_basic(self, seeded: dict):
        """Basic song creation."""
        result = dispatch(
            ["node", "add", "media", "song"],
            {"labels": "en::Bohemian Rhapsody"},
        )
        assert result["type"] == "status"

    def test_song_with_author_and_singer(self, seeded: dict):
        """Song with --author and --singer."""
        result = dispatch(
            ["node", "add", "media", "song"],
            {"labels": "en::Bohemian Rhapsody", "author": "ALICE", "singer": "BOB"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasAuthor" for t in triples)
        assert any(t["predicate_id"] == "sm:hasSinger" for t in triples)

    def test_song_all_fields(self, seeded: dict):
        """Song with all fields simultaneously."""
        result = dispatch(
            ["node", "add", "media", "song"],
            {"labels": "en::Song", "author": "ALICE", "singer": "BOB",
             "iswc": "T-010.101.929-7"},
        )
        assert result["type"] == "status"
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasISWC" for t in triples)
        assert sum(1 for t in triples if t["predicate_id"] == "sm:hasAuthor") == 1
        assert sum(1 for t in triples if t["predicate_id"] == "sm:hasSinger") == 1


# ── !node add media game ─────────────────────────────────────────────────


class TestNodeAddGame:
    def test_game_basic(self, seeded: dict):
        """Basic game creation."""
        result = dispatch(
            ["node", "add", "media", "game"],
            {"labels": "en::The Witcher 3"},
        )
        assert result["type"] == "status"

    def test_game_with_developer(self, seeded: dict):
        """Game with --developer should create sm:developedBy triple."""
        result = dispatch(
            ["node", "add", "media", "game"],
            {"labels": "en::Witcher 3", "developer": "CD_PROJEKT"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:developedBy" for t in triples)

    def test_game_with_platform_and_genre(self, seeded: dict):
        """Game with --platform and --genre."""
        result = dispatch(
            ["node", "add", "media", "game"],
            {"labels": "en::Witcher 3", "platform": "PC, PS5", "genre": "RPG"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:platform" for t in triples)
        assert any(t["predicate_id"] == "sm:genre" for t in triples)

    def test_game_all_fields(self, seeded: dict):
        """Game with all fields simultaneously."""
        result = dispatch(
            ["node", "add", "media", "game"],
            {"labels": "en::Witcher 3", "platform": "PC, PS5", "genre": "RPG",
             "developer": "CD_PROJEKT", "publisher": "CD_PROJEKT",
             "year": "2015"},
        )
        assert result["type"] == "status"
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:developedBy" for t in triples)
        assert any(t["predicate_id"] == "sm:publishedBy" for t in triples)
        assert any(t["predicate_id"] == "sm:publicationYear" for t in triples)
        assert sum(1 for t in triples if t["predicate_id"] == "sm:platform") == 2


# ── !node add media podcast ──────────────────────────────────────────────


class TestNodeAddPodcast:
    def test_podcast_basic(self, seeded: dict):
        """Basic podcast creation."""
        result = dispatch(
            ["node", "add", "media", "podcast"],
            {"labels": "en::Hardcore History"},
        )
        assert result["type"] == "status"

    def test_podcast_with_host(self, seeded: dict):
        """Podcast with --host should create sm:hasHost triple."""
        result = dispatch(
            ["node", "add", "media", "podcast"],
            {"labels": "en::History", "host": "ALICE"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasHost" for t in triples)

    def test_podcast_all_fields(self, seeded: dict):
        """Podcast with all fields simultaneously."""
        result = dispatch(
            ["node", "add", "media", "podcast"],
            {"labels": "en::My Podcast", "host": "ALICE,BOB",
             "episode-count": "100", "feed-url": "https://example.com/feed",
             "language": "en"},
        )
        assert result["type"] == "status"
        triples = result["data"].get("semantic_triples", [])
        assert sum(1 for t in triples if t["predicate_id"] == "sm:hasHost") == 2
        assert any(t["predicate_id"] == "sm:episodeCount" for t in triples)
        assert any(t["predicate_id"] == "sm:feedURL" for t in triples)


# ── !node add scholarly paper ────────────────────────────────────────────


class TestNodeAddPaper:
    def test_paper_basic(self, seeded: dict):
        """Basic paper creation."""
        result = dispatch(
            ["node", "add", "scholarly", "paper"],
            {"labels": "en::On the Electrodynamics"},
        )
        assert result["type"] == "status"

    def test_paper_with_doi_and_author(self, seeded: dict):
        """Paper with --doi and --author."""
        result = dispatch(
            ["node", "add", "scholarly", "paper"],
            {"labels": "en::Paper", "doi": "10.1234/test", "author": "EINSTEIN"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasDOI" for t in triples)
        assert any(t["predicate_id"] == "sm:hasAuthor" for t in triples)

    def test_paper_with_journal_and_keywords(self, seeded: dict):
        """Paper with --journal and --keywords."""
        result = dispatch(
            ["node", "add", "scholarly", "paper"],
            {"labels": "en::Paper", "journal": "Nature", "keywords": "physics, einstein"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:publishedIn" for t in triples)
        assert any(t["predicate_id"] == "sm:hasKeyword" for t in triples)

    def test_paper_all_fields(self, seeded: dict):
        """Paper with all fields simultaneously."""
        result = dispatch(
            ["node", "add", "scholarly", "paper"],
            {"labels": "en::Paper", "doi": "10.1234/test",
             "author": "EINSTEIN", "journal": "Nature",
             "year": "1905", "keywords": "physics, einstein",
             "url": "https://doi.org/10.1234/test"},
        )
        assert result["type"] == "status"
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasDOI" for t in triples)
        assert any(t["predicate_id"] == "sm:publishedIn" for t in triples)
        assert sum(1 for t in triples if t["predicate_id"] == "sm:hasKeyword") == 2
        assert any(t["predicate_id"] == "sm:hasURL" for t in triples)


# ── !node add scholarly patent ───────────────────────────────────────────


class TestNodeAddPatent:
    def test_patent_basic(self, seeded: dict):
        """Basic patent creation."""
        result = dispatch(
            ["node", "add", "scholarly", "patent"],
            {"labels": "en::My Patent"},
        )
        assert result["type"] == "status"

    def test_patent_with_number_and_inventor(self, seeded: dict):
        """Patent with --patent-number and --inventor."""
        result = dispatch(
            ["node", "add", "scholarly", "patent"],
            {"labels": "en::Patent", "patent-number": "US9876543B2", "inventor": "EINSTEIN"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasPatentNumber" for t in triples)
        assert any(t["predicate_id"] == "sm:hasInventor" for t in triples)

    def test_patent_all_fields(self, seeded: dict):
        """Patent with all fields simultaneously."""
        result = dispatch(
            ["node", "add", "scholarly", "patent"],
            {"labels": "en::Patent", "patent-number": "US9876543B2",
             "inventor": "EINSTEIN", "year": "2023", "assignee": "CD_PROJEKT"},
        )
        assert result["type"] == "status"
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:hasPatentNumber" for t in triples)
        assert any(t["predicate_id"] == "sm:hasInventor" for t in triples)
        assert any(t["predicate_id"] == "sm:publicationYear" for t in triples)
        assert any(t["predicate_id"] == "sm:assignedTo" for t in triples)


# ── !node add scholarly conference ───────────────────────────────────────


class TestNodeAddConference:
    def test_conference_basic(self, seeded: dict):
        """Basic conference creation."""
        result = dispatch(
            ["node", "add", "scholarly", "conference"],
            {"labels": "en::ICSE 2026"},
        )
        assert result["type"] == "status"

    def test_conference_with_series_and_location(self, seeded: dict):
        """Conference with --series, --year, --location."""
        result = dispatch(
            ["node", "add", "scholarly", "conference"],
            {"labels": "en::ICSE 2026",
             "series": "ICSE",
             "year": "2026",
             "location": "Pittsburgh, PA"},
        )
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:conferenceSeries" for t in triples)
        assert any(t["predicate_id"] == "sm:publicationYear" for t in triples)
        assert any(t["predicate_id"] == "sm:location" for t in triples)

    def test_conference_all_fields(self, seeded: dict):
        """Conference with all fields simultaneously."""
        result = dispatch(
            ["node", "add", "scholarly", "conference"],
            {"labels": "en::ICSE 2026",
             "series": "ICSE", "year": "2026",
             "location": "Pittsburgh, PA",
             "url": "https://conf.researchr.org/home/icse-2026"},
        )
        assert result["type"] == "status"
        triples = result["data"].get("semantic_triples", [])
        assert any(t["predicate_id"] == "sm:conferenceSeries" for t in triples)
        assert any(t["predicate_id"] == "sm:location" for t in triples)
        assert any(t["predicate_id"] == "sm:hasURL" for t in triples)


# ── Command tree verification ──────────────────────────────────────────


class TestMediaScholarlyInTree:
    """Verify new subcommands appear in the command tree."""

    def test_tree_has_media(self):
        from semantika.server.command.registry import get_command_tree
        tree = get_command_tree()
        add_entry = next(c for c in next(
            n for n in tree if n["name"] == "node"
        )["children"] if c["name"] == "add")
        child_names = [c["name"] for c in add_entry.get("children", [])]
        assert "media" in child_names
        assert "scholarly" in child_names

    def test_media_has_children(self):
        from semantika.server.command.registry import get_command_tree
        tree = get_command_tree()
        add_entry = next(c for c in next(
            n for n in tree if n["name"] == "node"
        )["children"] if c["name"] == "add")
        media_entry = next(c for c in add_entry["children"] if c["name"] == "media")
        child_names = [c["name"] for c in media_entry.get("children", [])]
        for cmd in ("book", "film", "song", "game", "podcast"):
            assert cmd in child_names

    def test_scholarly_has_children(self):
        from semantika.server.command.registry import get_command_tree
        tree = get_command_tree()
        add_entry = next(c for c in next(
            n for n in tree if n["name"] == "node"
        )["children"] if c["name"] == "add")
        scholarly_entry = next(c for c in add_entry["children"] if c["name"] == "scholarly")
        child_names = [c["name"] for c in scholarly_entry.get("children", [])]
        for cmd in ("paper", "patent", "conference"):
            assert cmd in child_names
