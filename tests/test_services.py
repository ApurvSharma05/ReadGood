from readgood.models import Book, UserBook
from readgood.extensions import db
from readgood.services import books as book_service
from readgood.services import recommend

from .conftest import make_book

GOOGLE_ITEM = {
    "id": "abc123XYZ",
    "volumeInfo": {
        "title": "Dune",
        "authors": ["Frank Herbert"],
        "description": "<p>A <b>desert</b> planet.</p><p>Spice &amp; sandworms.</p>",
        "publishedDate": "1965-08-01",
        "pageCount": 612,
        "categories": ["Fiction / Science Fiction / General"],
        "industryIdentifiers": [{"type": "ISBN_13", "identifier": "9780441013593"}],
        "imageLinks": {"thumbnail": "http://books.google.com/x?id=1&edge=curl"},
    },
}


def test_from_google_normalises_fields():
    book = book_service.from_google(GOOGLE_ITEM)
    assert book["source"] == "google" and book["source_id"] == "abc123XYZ"
    assert book["author"] == "Frank Herbert"
    assert book["year"] == 1965
    assert book["isbn"] == "9780441013593"
    assert book["categories"] == ["Fiction", "Science Fiction"]
    assert book["cover_url"] == "https://books.google.com/x?id=1"
    assert book["description"] == "A desert planet.\nSpice & sandworms."


def test_from_google_handles_missing_data():
    assert book_service.from_google({"id": "x"}) is None
    book = book_service.from_google({"id": "abcd", "volumeInfo": {"title": "Bare"}})
    assert book["author"] == "Unknown author"
    assert book["cover_url"] == book_service.DEFAULT_COVER


def test_from_open_library_and_nyt():
    doc = {"key": "/works/OL45883W", "title": "Emma", "author_name": ["Jane Austen"], "cover_i": 12}
    book = book_service.from_open_library(doc)
    assert (book["source"], book["source_id"]) == ("ol", "OL45883W")
    assert book["cover_url"].endswith("/12-M.jpg")
    assert book_service.from_open_library({"key": "/works/bad", "title": "x"}) is None

    nyt = book_service.from_nyt(
        {"title": "THE WOMEN", "author": "Kristin Hannah", "primary_isbn13": "9781250178633", "rank": 1},
        "Fiction",
    )
    assert nyt["title"] == "The Women" and nyt["rank"] == 1
    assert (nyt["source"], nyt["source_id"]) == ("isbn", "9781250178633")
    assert book_service.from_nyt({"title": "NO ISBN"}, "Fiction") is None


def test_text_cleanup_helpers():
    raw = "A great book. ([source][1])\n\n----------\n[1]: https://example.com\nMore links"
    assert book_service._clean_ol_description(raw) == "A great book."
    assert book_service._clean_ol_description("Ends with a dash\n–") == "Ends with a dash"
    assert book_service._split_categories(["sci-fi", "nyt:hardcover-fiction=2021-05-23"]) == ["Sci-fi"]
    assert book_service._title_case("IN THE SHADOW OF EIGHT") == "In the Shadow of Eight"


def test_failures_are_cached_briefly(app):
    from readgood.extensions import cache

    app.config["CACHE_TYPE"] = "SimpleCache"
    cache.init_app(app)
    calls = []

    def flaky():
        calls.append(1)
        return None

    with app.app_context():
        assert book_service._cached("test:flaky", 60, flaky) is None
        assert book_service._cached("test:flaky", 60, flaky) is None
        results = book_service._cached_many([("test:flaky", 60, flaky)])
    assert results == [None]
    assert len(calls) == 1  # the rate-limited source was asked only once


def test_get_book_rejects_bad_ids(app):
    with app.app_context():
        assert book_service.get_book("google", "../../etc") is None
        assert book_service.get_book("ol", "OL1A") is None
        assert book_service.get_book("isbn", "12345") is None
        assert book_service.get_book("other", "abc123") is None


def test_failed_upstream_gives_empty_results(app):
    with app.app_context():
        assert book_service.home_shelves() == []
        assert book_service.search_books("dune") == {"books": [], "total": 0}
        assert book_service.browse_genre("fantasy") == []


def test_google_search_uses_response(app, monkeypatch):
    monkeypatch.setattr(
        book_service, "_get_json", lambda url, params=None: {"items": [GOOGLE_ITEM, GOOGLE_ITEM]}
    )
    with app.app_context():
        books = book_service.google_search('subject:"Science Fiction"')
    assert [b["title"] for b in books] == ["Dune"]  # duplicates collapsed


def test_recommendations_use_shelf_and_skip_owned(app, monkeypatch):
    def fake_many(queries, limit=18):
        return [
            [make_book(1, title="Owned Book"), make_book(2), make_book(3)] if "subject" in q
            else [make_book(2), make_book(4)]
            for q in queries
        ]

    monkeypatch.setattr(book_service, "google_search_many", fake_many)
    with app.app_context():
        liked = Book(title="Owned Book", author="Ann Writer, Co Author", categories="Fantasy|Fiction")
        disliked = Book(title="Bad Book", author="Poor Writer", categories="Horror")
        db.session.add_all([liked, disliked])
        db.session.flush()
        db.session.add_all([
            UserBook(user_id=1, book_id=liked.id, status="read", rating=5),
            UserBook(user_id=1, book_id=disliked.id, status="read", rating=1),
        ])
        db.session.commit()

        picks = recommend.recommend_for(1)

    titles = [b["title"] for b in picks["books"]]
    assert "Owned Book" not in titles
    assert len(titles) == len(set(titles))
    assert set(titles) == {"Book 2", "Book 3", "Book 4"}
    assert "Fantasy" in picks["because"] and "Ann Writer" in picks["because"]
    assert "Horror" not in picks["because"] and "Poor Writer" not in picks["because"]
    assert all(b["reason"] for b in picks["books"])


def test_no_recommendations_for_empty_shelf(app):
    with app.app_context():
        assert recommend.recommend_for(1) == {"books": [], "because": []}
