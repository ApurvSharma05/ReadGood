from readgood.services import books as book_service

from .conftest import make_book


def test_public_pages_render_without_upstream(client):
    for path in ("/", "/home", "/genres", "/genre/fantasy", "/author/Jane Austen",
                 "/search", "/search?q=dune", "/login", "/register"):
        assert client.get(path).status_code == 200, path


def test_healthz(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}


def test_security_headers(client):
    headers = client.get("/home").headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "default-src 'self'" in headers["Content-Security-Policy"]


def test_unknown_pages_are_404(client):
    assert client.get("/genre/not-a-genre").status_code == 404
    assert client.get("/book/google/missing0000").status_code == 404
    assert client.get("/nope").status_code == 404


def test_legacy_links_redirect(client):
    assert "/book/isbn/9780441013593" in client.get("/book/9780441013593").headers["Location"]
    assert "/search" in client.get("/book/Unknown ISBN").headers["Location"]
    assert "/search" in client.get("/book/nyt/THE WOMEN").headers["Location"]
    assert "/library" in client.get("/user_books").headers["Location"]


def test_home_and_detail_show_books(client, monkeypatch):
    shelf = {"id": "x", "title": "Test shelf", "subtitle": "", "books": [make_book(1), make_book(2)]}
    monkeypatch.setattr(book_service, "home_shelves", lambda: [shelf])
    monkeypatch.setattr(book_service, "get_book", lambda source, source_id: make_book(1))
    monkeypatch.setattr(book_service, "related", lambda book: [shelf])

    home = client.get("/home").data
    assert b"Test shelf" in home and b"Book 2" in home

    detail = client.get("/book/google/vol0001").data
    assert b"Book 1" in detail and b"Want to read" in detail


def test_search_results_and_escaping(client, monkeypatch):
    nasty = make_book(7, title="<script>alert(1)</script>")
    monkeypatch.setattr(
        book_service, "search_books", lambda query, page=1, sort="relevance", limit=24:
        {"books": [nasty], "total": 60},
    )
    page = client.get("/search?q=anything").data
    assert b"<script>alert(1)</script>" not in page
    assert b"&lt;script&gt;" in page
    assert b"page 1 of 3" in page
    assert b'rel="next"' in page


def test_suggest_endpoint(client, monkeypatch):
    monkeypatch.setattr(book_service, "suggest", lambda query: [make_book(1)])
    assert client.get("/api/suggest?q=a").get_json() == {"results": []}
    results = client.get("/api/suggest?q=book").get_json()["results"]
    assert results[0]["url"] == "/book/google/vol0001"
