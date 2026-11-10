from readgood import create_app
from readgood.auth import safe_next
from readgood.models import Account


def register(client, **overrides):
    data = {"username": "reader", "email": "reader@example.com", "password": "correct horse"}
    data.update(overrides)
    return client.post("/register", data=data)


def test_register_signs_in_and_hashes_password(app, client):
    assert register(client).status_code == 302
    with app.app_context():
        account = Account.query.filter_by(username="reader").one()
        assert account.password != "correct horse"
    assert client.get("/library").status_code == 200


def test_register_rejects_bad_input(app, client):
    bad = register(client, username="bad name!")
    assert bad.status_code == 400
    assert b'role="alert"' in bad.data
    assert b'value="bad name!"' in bad.data  # input is kept
    assert register(client, email="not-an-email").status_code == 400
    assert register(client, password="short").status_code == 400
    with app.app_context():
        assert Account.query.count() == 0


def test_register_rejects_duplicate_username_and_email(app, client):
    register(client)
    client.post("/logout")
    assert register(client, email="other@example.com").status_code == 400
    assert register(client, username="other").status_code == 400
    with app.app_context():
        assert Account.query.count() == 1


def test_login_and_logout(client):
    register(client)
    client.post("/logout")
    assert client.get("/library").status_code == 302

    bad = client.post("/login", data={"username": "reader", "password": "wrong"})
    assert bad.status_code == 401
    assert b"do not match" in bad.data
    assert b'value="reader"' in bad.data
    assert client.get("/library").status_code == 302

    good = client.post("/login", data={"username": "reader", "password": "correct horse"})
    assert good.status_code == 302
    assert client.get("/library").status_code == 200


def test_logout_requires_post(client):
    assert client.get("/logout").status_code == 405


def test_login_redirects_only_to_local_paths(client):
    register(client)
    client.post("/logout")
    response = client.post(
        "/login?next=https://evil.example/", data={"username": "reader", "password": "correct horse"}
    )
    assert response.headers["Location"].endswith("/home")


def test_safe_next():
    assert safe_next("/library?shelf=read") == "/library?shelf=read"
    for bad in ("https://evil.example", "//evil.example", "/\\evil.example", "", None):
        assert safe_next(bad) is None


def test_csrf_is_enforced_when_enabled(monkeypatch):
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "RATELIMIT_ENABLED": False,
        "CACHE_TYPE": "NullCache",
    })
    response = app.test_client().post("/logout", headers={"X-Requested-With": "fetch"})
    assert response.status_code == 400
