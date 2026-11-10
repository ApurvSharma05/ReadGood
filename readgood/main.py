"""Discovery pages: home, search, genres, authors, book details."""
import random

from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, url_for
from sqlalchemy import text
from sqlalchemy.orm import joinedload

from .auth import login_required
from .extensions import db, limiter
from .models import Book, UserBook
from .services import books as book_service
from .services import recommend

bp = Blueprint("main", __name__)

SEARCH_SORTS = {"relevance": "Best match", "rating": "Top rated", "new": "Newest", "old": "Oldest"}
PAGE_SIZE = 24
MAX_PAGE = 40


@bp.get("/")
def landing():
    if g.user:
        return redirect(url_for("main.home"))
    shelves = book_service.home_shelves()
    featured = shelves[0]["books"][0] if shelves and shelves[0]["books"] else None
    wall, seen = [], set()
    for shelf in shelves:
        for book in shelf["books"]:
            if book["cover_url"] != book_service.DEFAULT_COVER and book["cover_url"] not in seen:
                seen.add(book["cover_url"])
                wall.append(book)
    return render_template(
        "landing.html", featured=featured, wall=wall[1:15], shelves=shelves[1:2] or shelves[:1]
    )


@bp.get("/home")
def home():
    shelves = book_service.home_shelves()
    spotlight = None
    if shelves and shelves[0]["books"] and shelves[0]["books"][0].get("rank"):
        spotlight = shelves[0]["books"][0]
    picks = recommend.recommend_for(g.user.id, limit=18) if g.user else None
    return render_template("home.html", shelves=shelves, picks=picks, spotlight=spotlight)


@bp.get("/recommendations")
@login_required
def recommendations():
    picks = recommend.recommend_for(g.user.id, limit=36)
    return render_template("recommendations.html", picks=picks)


@bp.get("/search")
def search():
    query = " ".join(request.args.get("q", "").split())[:100]
    sort = request.args.get("sort", "relevance")
    if sort not in SEARCH_SORTS:
        sort = "relevance"
    page = min(max(request.args.get("page", 1, type=int) or 1, 1), MAX_PAGE)

    result = {"books": [], "total": 0}
    if query:
        result = book_service.search_books(query, page=page, sort=sort, limit=PAGE_SIZE)
    last_page = min(MAX_PAGE, max(1, -(-result["total"] // PAGE_SIZE)))
    return render_template(
        "search.html",
        query=query,
        sort=sort,
        sorts=SEARCH_SORTS,
        page=page,
        last_page=last_page,
        books=result["books"],
        total=result["total"],
    )


@bp.get("/api/suggest")
@limiter.limit("40 per minute")
def suggest():
    query = " ".join(request.args.get("q", "").split())[:60]
    if len(query) < 3:
        return jsonify(results=[])
    results = [
        {
            "title": s["title"],
            "author": s["author"],
            "cover_url": s["cover_url"],
            "url": url_for("main.book_detail", source=s["source"], source_id=s["source_id"]),
        }
        for s in book_service.suggest(query)
    ]
    return jsonify(results=results)


@bp.get("/genres")
def genres():
    return render_template("genres.html")


@bp.get("/genre/<slug>")
def genre(slug):
    slug = slug.lower()
    if slug not in book_service.GENRES:
        abort(404)
    newest = request.args.get("sort") == "newest"
    label = book_service.GENRES[slug][0]
    return render_template(
        "browse.html",
        heading=label,
        eyebrow="Genre",
        intro=f"Popular and notable {label.lower()} books.",
        books=book_service.browse_genre(slug, newest=newest),
        sorts=[
            ("Popular", url_for("main.genre", slug=slug), not newest),
            ("Newest", url_for("main.genre", slug=slug, sort="newest"), newest),
        ],
    )


@bp.get("/author/<path:name>")
def author(name):
    name = " ".join(name.split())[:100]
    if not name:
        abort(404)
    return render_template(
        "browse.html",
        heading=name,
        eyebrow="Author",
        intro=f"Books by {name}, most relevant first.",
        books=book_service.author_books(name),
        back_url=url_for("main.home"),
        back_label="Discover",
    )


@bp.get("/surprise")
@limiter.limit("20 per minute")
def surprise():
    slug = random.choice(list(book_service.GENRES))
    books = book_service.browse_genre(slug)
    if not books:
        return redirect(url_for("main.home"))
    book = random.choice(books)
    return redirect(url_for("main.book_detail", source=book["source"], source_id=book["source_id"]))


@bp.get("/book/<source>/<path:source_id>")
def book_detail(source, source_id):
    if source == "nyt":
        # Links saved by the old app looked like /book/nyt/<title>.
        return redirect(url_for("main.search", q=source_id))

    book = book_service.get_book(source, source_id)
    if not book:
        abort(404)
    if (book["source"], book["source_id"]) != (source, source_id):
        return redirect(
            url_for("main.book_detail", source=book["source"], source_id=book["source_id"])
        )

    entry = None
    if g.user:
        entry = (
            UserBook.query.options(joinedload(UserBook.book))
            .join(Book)
            .filter(
                UserBook.user_id == g.user.id,
                Book.source == source,
                Book.source_id == source_id,
            )
            .first()
        )
    return render_template(
        "book.html", book=book, entry=entry, shelves=book_service.related(book)
    )


@bp.get("/book/<legacy_id>")
def legacy_book(legacy_id):
    """Old-style /book/<isbn> links."""
    if book_service.ISBN.match(legacy_id):
        return redirect(url_for("main.book_detail", source="isbn", source_id=legacy_id))
    return redirect(url_for("main.search", q=legacy_id))


@bp.get("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="favicon.ico"), code=301)


@bp.get("/healthz")
def healthz():
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return jsonify(status="error"), 503
    return jsonify(status="ok")
