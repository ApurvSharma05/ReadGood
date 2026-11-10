"""A reader's shelves: saved books, reading status, ratings, notes and goal."""
from datetime import datetime, timezone
from urllib.parse import urlsplit

from flask import (
    Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for,
)
from sqlalchemy.orm import joinedload

from .auth import login_required, safe_next
from .extensions import db
from .models import STATUSES, Book, UserBook, utcnow
from .services.books import DEFAULT_COVER, SOURCES

bp = Blueprint("library", __name__)

SORTS = {"recent": "Recently added", "title": "Title", "rating": "My rating"}


def _wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


def _back(default):
    """Return to the page the form was submitted from (same site only)."""
    target = safe_next(request.form.get("next"))
    if not target and request.referrer:
        parts = urlsplit(request.referrer)
        if parts.netloc == request.host:
            target = safe_next(parts.path + (f"?{parts.query}" if parts.query else ""))
    return redirect(target or default)


def _clean_cover(url):
    url = (url or "").strip()[:500]
    if url.startswith("https://") or url == DEFAULT_COVER:
        return url
    return DEFAULT_COVER


def _set_status(entry, status):
    if status not in STATUSES or status == entry.status:
        return
    entry.status = status
    entry.finished_at = utcnow() if status == "read" else None


def _own_entry(entry_id):
    entry = db.session.get(UserBook, entry_id)
    if entry is None or entry.user_id != g.user.id:
        abort(404)
    return entry


@bp.get("/library")
@login_required
def index():
    shelf = request.args.get("shelf", "all")
    if shelf != "all" and shelf not in STATUSES:
        shelf = "all"
    sort = request.args.get("sort", "recent")
    if sort not in SORTS:
        sort = "recent"

    entries = (
        UserBook.query.options(joinedload(UserBook.book))
        .filter_by(user_id=g.user.id)
        .all()
    )

    year = datetime.now(timezone.utc).year
    counts = {status: 0 for status in STATUSES}
    for entry in entries:
        counts[entry.status if entry.status in STATUSES else "want"] += 1
    ratings = [e.rating for e in entries if e.rating]
    read_this_year = sum(
        1 for e in entries
        if e.status == "read" and e.finished_at and e.finished_at.year == year
    )
    goal = g.user.yearly_goal
    stats = {
        "total": len(entries),
        "counts": counts,
        "average_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        "read_this_year": read_this_year,
        "goal": goal,
        "goal_percent": min(100, round(100 * read_this_year / goal)) if goal else 0,
        "year": year,
    }

    visible = [e for e in entries if shelf == "all" or e.status == shelf]
    if sort == "title":
        visible.sort(key=lambda e: e.book.title.lower())
    elif sort == "rating":
        visible.sort(key=lambda e: (-(e.rating or 0), e.book.title.lower()))
    else:
        visible.sort(key=lambda e: (e.added_at or datetime.min, e.id), reverse=True)

    return render_template(
        "library.html", entries=visible, stats=stats, shelf=shelf, sort=sort, sorts=SORTS
    )


@bp.get("/user_books")
def legacy_user_books():
    return redirect(url_for("library.index"))


@bp.post("/library/add")
@login_required
def add():
    form = request.form
    title = form.get("title", "").strip()[:300]
    author = form.get("author", "").strip()[:300] or "Unknown author"
    source = form.get("source", "").strip()
    source_id = form.get("source_id", "").strip()[:64]
    status = form.get("status", "want")
    if status not in STATUSES:
        status = "want"

    if not title:
        message = "That book could not be saved."
        if _wants_json():
            return jsonify(ok=False, message=message), 400
        flash(message, "error")
        return _back(url_for("main.home"))

    book = None
    if source in SOURCES and source_id:
        book = Book.query.filter_by(source=source, source_id=source_id).first()
    else:
        source = source_id = None
        book = Book.query.filter_by(title=title, author=author, source=None).first()

    if book is None:
        book = Book(
            title=title,
            author=author,
            cover_url=_clean_cover(form.get("cover_url")),
            source=source,
            source_id=source_id,
            categories=form.get("categories", "").strip()[:400] or None,
            year=form.get("year", type=int),
        )
        db.session.add(book)
        db.session.flush()

    entry = UserBook.query.filter_by(user_id=g.user.id, book_id=book.id).first()
    if entry is None:
        entry = UserBook(user_id=g.user.id, book_id=book.id, status=status)
        if status == "read":
            entry.finished_at = utcnow()
        db.session.add(entry)
        message = f"Saved “{title}” to {STATUSES[status]}."
    elif entry.status != status and form.get("status"):
        _set_status(entry, status)
        message = f"Moved “{title}” to {STATUSES[status]}."
    else:
        message = f"“{title}” is already on your shelves."
    db.session.commit()

    if _wants_json():
        return jsonify(ok=True, message=message, status=entry.status, entry_id=entry.id)
    flash(message, "success")
    return _back(url_for("library.index"))


@bp.post("/library/<int:entry_id>/update")
@login_required
def update(entry_id):
    entry = _own_entry(entry_id)
    form = request.form

    if "status" in form:
        _set_status(entry, form["status"])
    if "rating" in form:
        rating = form.get("rating", type=int)
        entry.rating = rating if rating and 1 <= rating <= 5 else None
    if "notes" in form:
        entry.notes = form["notes"].strip()[:2000] or None
    db.session.commit()

    message = f"Updated “{entry.book.title}”."
    if _wants_json():
        return jsonify(ok=True, message=message, status=entry.status, rating=entry.rating)
    flash(message, "success")
    return _back(url_for("library.index"))


@bp.post("/library/<int:entry_id>/remove")
@login_required
def remove(entry_id):
    entry = _own_entry(entry_id)
    title = entry.book.title
    db.session.delete(entry)
    db.session.commit()
    flash(f"Removed “{title}” from your shelves.", "success")
    return _back(url_for("library.index"))


@bp.post("/library/goal")
@login_required
def set_goal():
    goal = request.form.get("goal", type=int)
    g.user.yearly_goal = goal if goal and 1 <= goal <= 500 else None
    db.session.commit()
    flash("Reading goal updated." if g.user.yearly_goal else "Reading goal cleared.", "success")
    return redirect(url_for("library.index"))


@bp.post("/remove_book/<int:book_id>")
@login_required
def legacy_remove(book_id):
    entry = UserBook.query.filter_by(user_id=g.user.id, book_id=book_id).first()
    if entry:
        db.session.delete(entry)
        db.session.commit()
    return redirect(url_for("library.index"))
