"""Personal recommendations built from a reader's shelves.

The profile is simple and explainable: authors and categories from saved
books are weighted by rating and reading status, the strongest signals become
Google Books queries, and the results are interleaved so that no single
signal dominates. Each recommended book carries the reason it was picked.
"""
import re
from collections import Counter

from sqlalchemy.orm import joinedload

from ..models import UserBook
from . import books as book_service

GENERIC_CATEGORIES = {"fiction", "nonfiction", "general", "books"}


def _first_author(value):
    name = re.split(r",| and | & |;", value or "")[0].strip()
    return "" if not name or name.lower().startswith("unknown") else name


def build_profile(entries):
    """Return (author weights, category weights) for a list of UserBook rows."""
    authors, categories = Counter(), Counter()
    for entry in entries:
        if entry.rating is not None and entry.rating <= 2:
            continue  # disliked books should not steer recommendations
        weight = 1.0
        if entry.rating:
            weight += entry.rating - 3
        if entry.status == "read":
            weight += 0.5
        author = _first_author(entry.book.author)
        if author:
            authors[author] += weight
        for category in entry.book.category_list:
            categories[category] += weight
    return authors, categories


def _pick_categories(categories, count=2):
    """Prefer specific categories ('Fantasy') over generic ones ('Fiction')."""
    ranked = [c for c, _ in categories.most_common()]
    specific = [c for c in ranked if c.lower() not in GENERIC_CATEGORIES]
    return (specific + [c for c in ranked if c not in specific])[:count]


def recommend_for(user_id, limit=24):
    entries = (
        UserBook.query.options(joinedload(UserBook.book))
        .filter_by(user_id=user_id)
        .all()
    )
    if not entries:
        return {"books": [], "because": []}

    authors, categories = build_profile(entries)
    signals = []
    for category in _pick_categories(categories):
        signals.append((f'subject:"{category}"', f"Because you like {category}", category))
    for author, _ in authors.most_common(2):
        signals.append((f'inauthor:"{author}"', f"More from {author}", author))
    if not signals:
        return {"books": [], "because": []}

    owned = {entry.book.title.strip().lower() for entry in entries}
    result_lists = book_service.google_search_many([q for q, _, _ in signals], 20)

    picked, seen = [], set(owned)
    queues = [list(books) for books in result_lists]
    while len(picked) < limit and any(queues):
        for queue, (_, reason, _) in zip(queues, signals):
            while queue:
                book = queue.pop(0)
                key = book["title"].strip().lower()
                if key in seen:
                    continue
                seen.add(key)
                picked.append(dict(book, reason=reason))
                break
            if len(picked) >= limit:
                break

    because = [label for (_, _, label), books in zip(signals, result_lists) if books]
    return {"books": picked, "because": because}
