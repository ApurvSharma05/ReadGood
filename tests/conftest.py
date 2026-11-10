import pytest

from readgood import create_app
from readgood.extensions import db
from readgood.services import books as book_service


def make_book(n=1, **overrides):
    book = book_service._book(
        source="google",
        source_id=f"vol{n:04d}",
        title=f"Book {n}",
        author=f"Author {n}",
        authors=[f"Author {n}"],
        cover_url="https://example.com/cover.jpg",
        categories=["Fantasy"],
        year=2020,
    )
    book.update(overrides)
    return book


@pytest.fixture
def app(monkeypatch):
    # Tests must never reach the real APIs.
    monkeypatch.setattr(book_service, "_get_json", lambda url, params=None: None)
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "CACHE_TYPE": "NullCache",
    })
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user(client):
    """A registered and signed-in reader."""
    response = client.post("/register", data={
        "username": "reader", "email": "reader@example.com", "password": "correct horse",
    })
    assert response.status_code == 302
    return client
