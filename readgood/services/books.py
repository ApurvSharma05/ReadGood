"""Book data from the NYT Books, Google Books and Open Library APIs.

Every source is normalised into the same dictionary shape (see _book), and
every successful response is cached so pages do not hit the upstream APIs on
each request. Failed or empty responses are never cached.
"""
import hashlib
import html
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ..extensions import cache

log = logging.getLogger(__name__)

DEFAULT_COVER = "/static/img/default_cover.jpg"
TIMEOUT = (3.05, 8)

GOOGLE_VOLUMES = "https://www.googleapis.com/books/v1/volumes"
OPEN_LIBRARY = "https://openlibrary.org"
NYT_LISTS_URL = "https://api.nytimes.com/svc/books/v3/lists/current/{name}.json"

HOUR = 3600
TTL_NYT = 6 * HOUR
TTL_TRENDING = 3 * HOUR
TTL_BROWSE = 12 * HOUR
TTL_SEARCH = HOUR
TTL_BOOK = 24 * HOUR

SOURCES = ("google", "ol", "isbn")
GOOGLE_ID = re.compile(r"^[A-Za-z0-9_-]{4,40}$")
OL_ID = re.compile(r"^OL\d{1,12}W$")
ISBN = re.compile(r"^(\d{9}[\dXx]|\d{13})$")

# slug -> (label, Google Books subject, Bootstrap icon)
GENRES = {
    "fiction": ("Fiction", "Fiction", "bi-book"),
    "fantasy": ("Fantasy", "Fantasy", "bi-magic"),
    "romance": ("Romance", "Romance", "bi-heart"),
    "mystery": ("Mystery", "Mystery", "bi-search"),
    "thriller": ("Thriller", "Thrillers", "bi-lightning"),
    "science-fiction": ("Science Fiction", "Science Fiction", "bi-rocket-takeoff"),
    "horror": ("Horror", "Horror", "bi-moon-stars"),
    "historical-fiction": ("Historical Fiction", "Historical Fiction", "bi-hourglass-split"),
    "young-adult": ("Young Adult", "Young Adult Fiction", "bi-stars"),
    "biography": ("Biography", "Biography & Autobiography", "bi-person-lines-fill"),
    "history": ("History", "History", "bi-globe-americas"),
    "self-help": ("Self-Help", "Self-Help", "bi-lightbulb"),
    "science": ("Science", "Science", "bi-stars"),
    "poetry": ("Poetry", "Poetry", "bi-feather"),
}

POPULAR_AUTHORS = [
    "Stephen King",
    "George R.R. Martin",
    "William Shakespeare",
    "Haruki Murakami",
    "Jane Austen",
    "Agatha Christie",
    "Brandon Sanderson",
    "Toni Morrison",
]

NYT_LISTS = [
    ("hardcover-fiction", "Fiction bestsellers", "This week on the New York Times list", "Fiction"),
    ("hardcover-nonfiction", "Nonfiction bestsellers", "True stories and big ideas", "Nonfiction"),
    ("young-adult-hardcover", "Young adult favourites", "Popular with younger readers", "Young Adult"),
]


# --------------------------------------------------------------------------
# HTTP and caching helpers
# --------------------------------------------------------------------------

_session = None


def _http():
    global _session
    if _session is None:
        session = requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=(502, 503, 504),
            allowed_methods=("GET",),
        )
        session.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=16))
        session.headers["User-Agent"] = "ReadGood/2.0 (book discovery web app)"
        _session = session
    return _session


def _get_json(url, params=None):
    """GET a JSON document. Returns None on any failure.

    Only the bare URL is logged: API keys travel in the query string and must
    not end up in logs.
    """
    try:
        response = _http().get(url, params=params, timeout=TIMEOUT)
        if response.status_code != 200:
            log.warning("Upstream %s returned HTTP %s", url, response.status_code)
            return None
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Upstream %s failed: %s", url, type(exc).__name__)
        return None


def _cached(key, ttl, producer):
    hit = cache.get(key)
    if hit is not None:
        return hit
    value = producer()
    if value:
        cache.set(key, value, timeout=ttl)
    return value


def _cached_many(jobs):
    """Resolve several (key, ttl, producer) jobs, fetching misses in parallel."""
    results = {}
    pending = []
    for key, ttl, producer in jobs:
        hit = cache.get(key)
        if hit is not None:
            results[key] = hit
        elif key not in results:
            results[key] = None
            pending.append((key, ttl, producer))
    if pending:
        with ThreadPoolExecutor(max_workers=min(6, len(pending))) as pool:
            futures = [(key, ttl, pool.submit(producer)) for key, ttl, producer in pending]
        for key, ttl, future in futures:
            try:
                value = future.result()
            except Exception:  # a bad upstream payload must not break the page
                log.exception("Fetching %s failed", key)
                value = None
            if value:
                cache.set(key, value, timeout=ttl)
            results[key] = value
    return [results[key] for key, _, _ in jobs]


def _digest(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Normalisers
# --------------------------------------------------------------------------

def _book(**fields):
    book = {
        "source": "",
        "source_id": "",
        "title": "Untitled",
        "author": "Unknown author",
        "authors": [],
        "cover_url": DEFAULT_COVER,
        "description": "",
        "publisher": "",
        "published": "",
        "year": None,
        "page_count": None,
        "categories": [],
        "rating": None,
        "ratings_count": None,
        "isbn": "",
        "rank": None,
        "weeks_on_list": None,
        "buy_url": "",
        "external_url": "",
        "external_label": "",
        "reason": "",
    }
    book.update({k: v for k, v in fields.items() if v not in (None, "", [])})
    return book


def _https(url):
    if not url:
        return None
    url = url.split("&edge=curl")[0]
    if url.startswith("http://"):
        url = "https://" + url[len("http://"):]
    return url if url.startswith("https://") else None


def _clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<\s*br\s*/?>|</p\s*>|</li\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _clean_ol_description(text):
    """Open Library descriptions are Markdown-ish: drop footnotes and trailing rules."""
    text = _clean_html(text)
    text = re.split(r"\n\s*(?:-{3,}|_{3,}|\*{3,})\s*(?:\n|$)", text)[0]
    text = re.sub(r"\(\s*\[[^\]]*\]\[\d+\]\s*\)", "", text)        # ([source][1])
    text = re.sub(r"\[([^\]]+)\]\[\d+\]", r"\1", text)               # [text][1]
    text = re.sub(r"\[([^\]]+)\]\(https?://[^)]+\)", r"\1", text)    # [text](url)
    text = re.sub(r"(?m)^\s*\[\d+\]:\s*\S+.*$", "", text)            # [1]: http://...
    text = re.sub(r"[\s–—-]+$", "", text)                  # trailing dashes
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _year(value):
    match = re.search(r"\d{4}", str(value or ""))
    return int(match.group()) if match else None


def _split_categories(raw, limit=6):
    seen, out = set(), []
    for entry in raw or []:
        for part in str(entry).split(" / "):
            part = part.strip()
            # Skip machine tags such as "nyt:hardcover-fiction=2021-05-23".
            if not part or part.lower() == "general" or part.lower() in seen or re.search(r"[:=]", part):
                continue
            seen.add(part.lower())
            out.append((part[:1].upper() + part[1:])[:60])
    return out[:limit]


def _dedupe(books):
    seen, out = set(), []
    for book in books:
        key = (book["title"].lower(), book["author"].lower())
        if key not in seen:
            seen.add(key)
            out.append(book)
    return out


def from_google(item):
    info = item.get("volumeInfo") or {}
    if not item.get("id") or not info.get("title"):
        return None
    identifiers = {
        i.get("type"): i.get("identifier") for i in info.get("industryIdentifiers") or []
    }
    authors = [a for a in info.get("authors") or [] if a]
    images = info.get("imageLinks") or {}
    return _book(
        source="google",
        source_id=item["id"],
        title=info["title"],
        author=", ".join(authors[:3]),
        authors=authors,
        cover_url=_https(images.get("thumbnail") or images.get("smallThumbnail")),
        description=_clean_html(info.get("description")),
        publisher=info.get("publisher"),
        published=info.get("publishedDate"),
        year=_year(info.get("publishedDate")),
        page_count=info.get("pageCount") or None,
        categories=_split_categories(info.get("categories")),
        rating=info.get("averageRating"),
        ratings_count=info.get("ratingsCount"),
        isbn=identifiers.get("ISBN_13") or identifiers.get("ISBN_10"),
        external_url=_https(info.get("infoLink")),
        external_label="Google Books",
    )


def from_open_library(doc, cover_size="M"):
    key = (doc.get("key") or "").rsplit("/", 1)[-1]
    if not OL_ID.match(key) or not doc.get("title"):
        return None
    authors = [a for a in doc.get("author_name") or [] if a]
    cover_id = doc.get("cover_i")
    rating = doc.get("ratings_average")
    return _book(
        source="ol",
        source_id=key,
        title=doc["title"],
        author=", ".join(authors[:3]),
        authors=authors,
        cover_url=(
            f"https://covers.openlibrary.org/b/id/{cover_id}-{cover_size}.jpg"
            if cover_id
            else None
        ),
        year=doc.get("first_publish_year"),
        published=str(doc.get("first_publish_year") or ""),
        categories=_split_categories((doc.get("subject") or [])[:5]),
        rating=round(rating, 1) if rating else None,
        ratings_count=doc.get("ratings_count"),
        external_url=f"{OPEN_LIBRARY}/works/{key}",
        external_label="Open Library",
    )


SMALL_WORDS = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "nor", "of", "on", "or", "the", "to", "with"}


def _title_case(text):
    """NYT titles arrive in capitals; turn them into ordinary title case."""
    words = text.lower().split()
    out = []
    for i, word in enumerate(words):
        if 0 < i < len(words) - 1 and word in SMALL_WORDS and not out[-1].endswith(":"):
            out.append(word)
        else:
            out.append(word[:1].upper() + word[1:])
    return " ".join(out)


def from_nyt(entry, category):
    isbn = entry.get("primary_isbn13") or entry.get("primary_isbn10") or ""
    if not ISBN.match(isbn) or not entry.get("title"):
        return None
    author = entry.get("author") or ""
    return _book(
        source="isbn",
        source_id=isbn,
        isbn=isbn,
        title=_title_case(entry["title"]),
        author=author,
        authors=[author] if author else [],
        cover_url=_https(entry.get("book_image")),
        description=entry.get("description"),
        publisher=entry.get("publisher"),
        categories=[category],
        rank=entry.get("rank"),
        weeks_on_list=entry.get("weeks_on_list"),
        buy_url=_https(entry.get("amazon_product_url")),
    )


# --------------------------------------------------------------------------
# Fetchers (pure: safe to run in worker threads)
# --------------------------------------------------------------------------

def _google_get(url, params):
    """Call Google Books with the API key, falling back to keyless access."""
    key = os.getenv("GOOGLE_API_KEY")
    if key:
        data = _get_json(url, {**params, "key": key})
        if data is not None:
            return data
    return _get_json(url, params)


def _fetch_nyt(name, category):
    key = os.getenv("NYT_API_KEY")
    if not key:
        return []
    data = _get_json(NYT_LISTS_URL.format(name=name), {"api-key": key}) or {}
    entries = (data.get("results") or {}).get("books") or []
    return [b for b in (from_nyt(e, category) for e in entries) if b]


def _fetch_trending():
    data = _get_json(f"{OPEN_LIBRARY}/trending/daily.json", {"limit": 24}) or {}
    books = [from_open_library(doc) for doc in data.get("works") or []]
    return [b for b in books if b and b["cover_url"] != DEFAULT_COVER][:18]


def _fetch_google(query, limit, order_by):
    params = {
        "q": query,
        "maxResults": max(1, min(limit, 40)),
        "printType": "books",
        "langRestrict": "en",
        "orderBy": order_by,
    }
    data = _google_get(GOOGLE_VOLUMES, params) or {}
    items = [
        item for item in data.get("items") or []
        if (item.get("volumeInfo") or {}).get("language", "en") == "en"
    ]
    books = [from_google(item) for item in items]
    return _dedupe([b for b in books if b])


def _fetch_search(query, page, sort, limit):
    params = {
        "q": query,
        "page": page,
        "limit": limit,
        "fields": "key,title,author_name,cover_i,first_publish_year,subject,"
                  "ratings_average,ratings_count,language",
    }
    if sort in ("new", "old", "rating"):
        params["sort"] = sort
    data = _get_json(f"{OPEN_LIBRARY}/search.json", params)
    if not data:
        return None
    books = []
    for doc in data.get("docs") or []:
        languages = doc.get("language")
        if languages and "eng" not in languages:
            continue
        book = from_open_library(doc)
        if book and (book["authors"] or book["cover_url"] != DEFAULT_COVER):
            books.append(book)
    books = _dedupe(books)
    if not books:
        return None
    return {"books": books, "total": int(data.get("numFound") or len(books))}


def _fetch_google_volume(volume_id):
    data = _google_get(f"{GOOGLE_VOLUMES}/{volume_id}", {})
    return from_google(data) if data else None


def _fetch_open_library_work(work_id):
    found = _get_json(
        f"{OPEN_LIBRARY}/search.json",
        {
            "q": f"key:/works/{work_id}",
            "limit": 1,
            "fields": "key,title,author_name,cover_i,first_publish_year,subject,"
                      "ratings_average,ratings_count",
        },
    ) or {}
    docs = found.get("docs") or []
    work = _get_json(f"{OPEN_LIBRARY}/works/{work_id}.json") or {}
    if not docs and not work.get("title"):
        return None

    doc = docs[0] if docs else {"key": f"/works/{work_id}", "title": work["title"]}
    if not doc.get("cover_i") and work.get("covers"):
        doc["cover_i"] = next((c for c in work["covers"] if isinstance(c, int) and c > 0), None)
    book = from_open_library(doc, cover_size="L")
    if not book:
        return None

    description = work.get("description")
    if isinstance(description, dict):
        description = description.get("value")
    book["description"] = _clean_ol_description(description)
    if not book["categories"]:
        book["categories"] = _split_categories((work.get("subjects") or [])[:5])
    return book


# --------------------------------------------------------------------------
# Public API (needs an application context for the cache)
# --------------------------------------------------------------------------

def _google_job(query, limit=18, order_by="relevance"):
    return (
        "g:" + _digest(query, limit, order_by),
        TTL_BROWSE,
        partial(_fetch_google, query, limit, order_by),
    )


def google_search(query, limit=18, order_by="relevance"):
    return _cached(*_google_job(query, limit, order_by)) or []


def google_search_many(queries, limit=18):
    """Run several Google Books queries at once; returns one list per query."""
    results = _cached_many([_google_job(q, limit) for q in queries])
    return [r or [] for r in results]


def nyt_list(name, category):
    return _cached(f"nyt:{name}", TTL_NYT, partial(_fetch_nyt, name, category)) or []


def home_shelves():
    """Shelves for the Discover page: NYT lists plus Open Library trending."""
    jobs = [
        (f"nyt:{name}", TTL_NYT, partial(_fetch_nyt, name, category))
        for name, _, _, category in NYT_LISTS
    ]
    jobs.append(("ol:trending", TTL_TRENDING, _fetch_trending))
    results = _cached_many(jobs)

    shelves = []
    for (name, title, subtitle, _), books in zip(NYT_LISTS, results):
        if books:
            shelves.append({"id": name, "title": title, "subtitle": subtitle, "books": books})
    if results[-1]:
        shelves.append({
            "id": "trending",
            "title": "Trending today",
            "subtitle": "What readers are opening on Open Library right now",
            "books": results[-1],
        })

    if len(shelves) < 2:
        # No NYT key (or NYT is down): fall back to Google Books genre shelves.
        for slug in ("fiction", "fantasy", "mystery"):
            books = browse_genre(slug)
            if books:
                shelves.append({
                    "id": f"genre-{slug}",
                    "title": f"Popular in {GENRES[slug][0]}",
                    "subtitle": "From Google Books",
                    "books": books,
                })
    return shelves


def cached_covers(limit=12):
    """Cover images already in the cache. Never calls an upstream API."""
    covers = []
    for key in [f"nyt:{name}" for name, _, _, _ in NYT_LISTS] + ["ol:trending"]:
        for book in cache.get(key) or []:
            if book["cover_url"] != DEFAULT_COVER and book["cover_url"] not in covers:
                covers.append(book["cover_url"])
            if len(covers) >= limit:
                return covers
    return covers


def browse_genre(slug, newest=False):
    if slug not in GENRES:
        return []
    subject = GENRES[slug][1]
    return google_search(f'subject:"{subject}"', 30, "newest" if newest else "relevance")


def author_books(name):
    return google_search(f'inauthor:"{_quote_free(name)}"', 30)


def _quote_free(value):
    return re.sub(r'["\\]', " ", value or "").strip()


def search_books(query, page=1, sort="relevance", limit=24):
    key = "search:" + _digest(query.lower(), page, sort, limit)
    result = _cached(key, TTL_SEARCH, partial(_fetch_search, query, page, sort, limit))
    return result or {"books": [], "total": 0}


def suggest(query):
    result = search_books(query, page=1, sort="relevance", limit=6)
    return [
        {
            "title": b["title"],
            "author": b["author"],
            "cover_url": b["cover_url"],
            "source": b["source"],
            "source_id": b["source_id"],
        }
        for b in result["books"][:6]
    ]


def _nyt_lookup(isbn):
    for name, _, _, category in NYT_LISTS:
        for book in nyt_list(name, category):
            if book["source_id"] == isbn:
                return book
    return None


def _book_by_isbn(isbn):
    nyt = _nyt_lookup(isbn)
    found = _fetch_google(f"isbn:{isbn}", 1, "relevance")
    if found:
        book = dict(found[0], source="isbn", source_id=isbn, isbn=isbn)
        if nyt:
            # NYT is the listing the reader clicked, so its title wins: Google
            # often still has a placeholder title for brand-new releases.
            for field in ("title", "rank", "weeks_on_list", "buy_url"):
                book[field] = nyt[field]
            if nyt["cover_url"] != DEFAULT_COVER:
                book["cover_url"] = nyt["cover_url"]
            book["description"] = book["description"] or nyt["description"]
            book["categories"] = book["categories"] or nyt["categories"]
        return book
    if nyt:
        return nyt
    # Last resort: Open Library knows many ISBNs Google does not.
    result = _fetch_search(f"isbn:{isbn}", 1, "relevance", 1)
    return result["books"][0] if result else None


def get_book(source, source_id):
    """Full details for one book, or None if it cannot be found."""
    if source == "google" and GOOGLE_ID.match(source_id):
        producer = partial(_fetch_google_volume, source_id)
    elif source == "ol" and OL_ID.match(source_id):
        producer = partial(_fetch_open_library_work, source_id)
    elif source == "isbn" and ISBN.match(source_id):
        producer = partial(_book_by_isbn, source_id)
    else:
        return None
    return _cached(f"book:{source}:{source_id}", TTL_BOOK, producer)


def related(book):
    """'More by this author' and 'similar' shelves for a detail page."""
    queries, labels = [], []
    author = book["authors"][0] if book["authors"] else ""
    if author:
        queries.append(f'inauthor:"{_quote_free(author)}"')
        labels.append(("more-by", f"More by {author}"))
    category = book["categories"][0] if book["categories"] else ""
    if category:
        queries.append(f'subject:"{_quote_free(category)}"')
        labels.append(("similar", f"More in {category}"))
    if not queries:
        return []

    title = book["title"].lower()
    shelves, seen = [], {title}

    def is_new(other):
        # Skip other editions of this same book ("Dune (Deluxe Edition)").
        name = other["title"].lower()
        return name not in seen and title not in name and name not in title

    for (shelf_id, label), books in zip(labels, google_search_many(queries, 18)):
        fresh = [b for b in books if is_new(b)]
        seen.update(b["title"].lower() for b in fresh)
        if fresh:
            shelves.append({"id": shelf_id, "title": label, "subtitle": "", "books": fresh})
    return shelves
