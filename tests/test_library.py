from readgood.models import Book, UserBook

BOOK = {
    "source": "google",
    "source_id": "vol0001",
    "title": "The Hobbit",
    "author": "J.R.R. Tolkien",
    "cover_url": "https://example.com/hobbit.jpg",
    "categories": "Fantasy|Fiction",
    "year": "1937",
}


def test_library_requires_login(client):
    response = client.get("/library")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_add_requires_login_json(client):
    response = client.post("/library/add", data=BOOK, headers={"X-Requested-With": "fetch"})
    assert response.status_code == 401
    assert "login_url" in response.get_json()


def test_add_book_and_no_duplicates(app, user):
    first = user.post("/library/add", data=BOOK, headers={"X-Requested-With": "fetch"})
    assert first.get_json()["ok"] is True
    user.post("/library/add", data=BOOK)
    with app.app_context():
        assert Book.query.count() == 1
        entry = UserBook.query.one()
        assert entry.status == "want"
        assert entry.book.category_list == ["Fantasy", "Fiction"]
    assert b"The Hobbit" in user.get("/library").data


def test_unsafe_cover_url_is_replaced(app, user):
    user.post("/library/add", data=dict(BOOK, cover_url="javascript:alert(1)"))
    with app.app_context():
        assert Book.query.one().cover_url == "/static/img/default_cover.jpg"


def test_update_status_rating_and_notes(app, user):
    user.post("/library/add", data=BOOK)
    with app.app_context():
        entry_id = UserBook.query.one().id

    user.post(f"/library/{entry_id}/update", data={"status": "read", "rating": "5", "notes": "Loved it"})
    with app.app_context():
        entry = UserBook.query.one()
        assert (entry.status, entry.rating, entry.notes) == ("read", 5, "Loved it")
        assert entry.finished_at is not None

    user.post(f"/library/{entry_id}/update", data={"status": "bogus", "rating": "9"})
    with app.app_context():
        entry = UserBook.query.one()
        assert entry.status == "read"
        assert entry.rating is None


def test_cannot_touch_another_readers_entry(app, user):
    user.post("/library/add", data=BOOK)
    with app.app_context():
        entry_id = UserBook.query.one().id

    user.post("/logout")
    user.post("/register", data={
        "username": "other", "email": "other@example.com", "password": "correct horse",
    })
    assert user.post(f"/library/{entry_id}/update", data={"rating": "1"}).status_code == 404
    assert user.post(f"/library/{entry_id}/remove").status_code == 404
    with app.app_context():
        assert UserBook.query.one().rating is None


def test_remove_and_goal(app, user):
    user.post("/library/add", data=dict(BOOK, status="read"))
    user.post("/library/goal", data={"goal": "12"})
    page = user.get("/library").data
    assert b"of 12 books" in page

    with app.app_context():
        entry_id = UserBook.query.one().id
    user.post(f"/library/{entry_id}/remove")
    with app.app_context():
        assert UserBook.query.count() == 0
