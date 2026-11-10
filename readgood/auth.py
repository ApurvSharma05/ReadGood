"""Sign up, sign in and sign out."""
import re
from functools import wraps
from urllib.parse import urlsplit

from flask import (
    Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for,
)
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db, limiter
from .models import Account
from .services import books as book_service

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
MIN_PASSWORD = 8
# Checked when the username is unknown so both paths take similar time.
_DUMMY_HASH = generate_password_hash("not-a-real-password")


def load_current_user():
    user_id = session.get("user_id")
    g.user = db.session.get(Account, user_id) if user_id else None
    if user_id and g.user is None:
        session.clear()


def safe_next(target):
    """Only allow redirects to paths on this site."""
    if not target or not target.startswith("/") or target.startswith("//") or "\\" in target:
        return None
    parts = urlsplit(target)
    return target if not parts.netloc and not parts.scheme else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            next_url = request.full_path.rstrip("?") if request.method == "GET" else request.referrer
            if next_url and not next_url.startswith("/"):
                parts = urlsplit(next_url)
                next_url = parts.path + (f"?{parts.query}" if parts.query else "")
            login_url = url_for("auth.login", next=safe_next(next_url))
            if request.headers.get("X-Requested-With") == "fetch":
                return jsonify(ok=False, message="Please sign in first.", login_url=login_url), 401
            flash("Please sign in to continue.", "info")
            return redirect(login_url)
        return view(*args, **kwargs)

    return wrapped


def _sign_in(account):
    session.clear()
    session["user_id"] = account.id
    session.permanent = True


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if g.user:
        return redirect(url_for("main.home"))
    next_url = safe_next(request.values.get("next"))
    username, error = "", None

    if request.method == "POST":
        username = request.form.get("username", "").strip()[:50]
        password = request.form.get("password", "")
        account = Account.query.filter(
            func.lower(Account.username) == username.lower()
        ).first()
        valid = check_password_hash(account.password if account else _DUMMY_HASH, password)
        if account and valid:
            _sign_in(account)
            flash(f"Welcome back, {account.username}.", "success")
            return redirect(next_url or url_for("main.home"))
        error = "That username and password do not match. Please try again."

    return render_template(
        "auth/login.html", next_url=next_url, username=username, error=error,
        covers=book_service.cached_covers(9),
    ), (401 if error else 200)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if g.user:
        return redirect(url_for("main.home"))
    next_url = safe_next(request.values.get("next"))
    form = {"username": "", "email": ""}
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        form = {"username": username, "email": email}

        if not USERNAME_RE.match(username):
            error = "Usernames are 3 to 30 characters: letters, numbers and underscores."
        elif not EMAIL_RE.match(email) or len(email) > 120:
            error = "Please enter a valid email address."
        elif len(password) < MIN_PASSWORD:
            error = f"Passwords need at least {MIN_PASSWORD} characters."
        elif Account.query.filter(func.lower(Account.username) == username.lower()).first():
            error = "That username is taken."
        elif Account.query.filter(func.lower(Account.email) == email).first():
            error = "An account with that email already exists."

        if not error:
            account = Account(
                username=username, email=email, password=generate_password_hash(password)
            )
            db.session.add(account)
            db.session.commit()
            _sign_in(account)
            flash("Welcome to ReadGood. Save a few books to get recommendations.", "success")
            return redirect(next_url or url_for("main.home"))

    return render_template(
        "auth/register.html", form=form, next_url=next_url, error=error,
        covers=book_service.cached_covers(9),
    ), (400 if error else 200)


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.landing"))
