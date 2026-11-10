# ReadGood

A book discovery and recommendation web app. Browse bestsellers, search millions of
titles, keep track of what you read, and get recommendations based on your own shelves.

Built with Flask, Bootstrap 5, plain CSS and plain JavaScript. No front-end build step.

## Features

- **Discover**: New York Times bestseller lists, daily trending books, 14 genres,
  popular authors and a "Surprise me" button.
- **Search**: title, author or ISBN search with live suggestions, sorting and paging.
- **Book pages**: description, ratings, publisher details, "more by this author"
  and "similar books" shelves.
- **My library**: Want to read / Reading / Read shelves, star ratings, private notes
  and a yearly reading goal.
- **For you**: recommendations built from the authors and genres you save and rate,
  each with the reason it was picked.
- Light and dark themes, a bottom tab bar on phones, and a search palette that opens
  with `/` or `Ctrl/⌘ + K` and shows live suggestions.

Book data comes from the [NYT Books API](https://developer.nytimes.com/docs/books-product/1/overview),
[Google Books](https://developers.google.com/books) and [Open Library](https://openlibrary.org/developers/api).

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
copy .env.example .env          # macOS/Linux: cp .env.example .env
flask --app app run --debug
```

Open http://127.0.0.1:5000. Add your `NYT_API_KEY` and `GOOGLE_API_KEY` to `.env`;
without them the app still runs using Open Library and keyless Google Books.

Run the tests with `pytest`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `production` enables secure cookies, HSTS and proxy headers. Default `development`. |
| `SECRET_KEY` | Session signing key. **Required in production.** |
| `NYT_API_KEY` | New York Times Books API key (bestseller shelves). |
| `GOOGLE_API_KEY` | Google Books API key (genres, authors, recommendations). |
| `DATABASE_URL` | Postgres URL. Empty means SQLite at `instance/books.db`. |
| `CACHE_TYPE`, `RATELIMIT_STORAGE_URI` | Optional Redis backends when running several servers. |

## Deploy

The app is a standard WSGI app: `gunicorn app:app -c gunicorn.conf.py`.

- **Render**: push to GitHub, then New > Blueprint and select the repo. `render.yaml`
  creates the web service and a Postgres database and generates `SECRET_KEY`.
  Add the two API keys when asked.
- **Railway / Heroku-style hosts**: the `Procfile` is picked up automatically. Set
  `APP_ENV=production`, `SECRET_KEY`, the API keys, and attach Postgres (`DATABASE_URL`).
- **Docker**: `docker build -t readgood .` then
  `docker run -p 8000:8000 -e SECRET_KEY=... -e NYT_API_KEY=... -e GOOGLE_API_KEY=... readgood`.

Use Postgres in production: most hosts wipe the local disk on every deploy, which
would erase a SQLite file. Tables are created on first start, and new columns are
added automatically. `GET /healthz` is the health check.

## Project layout

```
app.py                  entry point (gunicorn app:app)
readgood/
  __init__.py           app factory, security headers, error pages
  config.py             settings from environment variables
  models.py             Account, Book, UserBook
  auth.py               sign up, sign in, sign out
  main.py               discover, search, genres, authors, book pages
  library.py            shelves, ratings, notes, reading goal
  services/books.py     NYT, Google Books and Open Library clients with caching
  services/recommend.py recommendation engine
  templates/  static/   Jinja templates, CSS and JavaScript
tests/                  pytest suite (no network access needed)
```

## License

Licensed under the MIT License.
