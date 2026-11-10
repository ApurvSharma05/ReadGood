"""ReadGood: a book discovery and recommendation web app."""
import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import Flask, flash, g, jsonify, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFError
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import configure
from .extensions import cache, csrf, db, limiter
from .models import STATUSES, Book, UserBook, ensure_schema
from .services import books as book_service

CONTENT_SECURITY_POLICY = "; ".join([
    "default-src 'self'",
    "script-src 'self' https://cdn.jsdelivr.net",
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com",
    "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com",
    "img-src 'self' data: https:",
    "connect-src 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "base-uri 'self'",
])


def create_app(test_config=None):
    load_dotenv()
    app = Flask(__name__, instance_relative_config=True)
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass  # read-only filesystem (e.g. Vercel); nothing is written there in production
    configure(app, test_config)

    if not app.debug:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if app.config["TRUST_PROXY"]:
        # Behind the host's load balancer: trust one hop for scheme and client IP.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    csrf.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)

    from .auth import bp as auth_bp, load_current_user
    from .library import bp as library_bp
    from .main import bp as main_bp

    app.before_request(load_current_user)
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(library_bp)

    with app.app_context():
        db.create_all()
        ensure_schema()

    _register_template_helpers(app)
    _register_error_handlers(app)

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        if app.config["PRODUCTION"]:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

    return app


def _register_template_helpers(app):
    def saved_entries():
        """Map of (source, source_id) -> shelf status for the signed-in reader."""
        if "saved_entries" not in g:
            g.saved_entries = {}
            if g.user:
                rows = (
                    db.session.query(Book.source, Book.source_id, UserBook.status)
                    .join(UserBook, UserBook.book_id == Book.id)
                    .filter(UserBook.user_id == g.user.id, Book.source.isnot(None))
                    .all()
                )
                g.saved_entries = {(src, sid): status for src, sid, status in rows}
        return g.saved_entries

    def saved_status(book):
        return saved_entries().get((book.get("source"), book.get("source_id")))

    def asset(filename):
        """Static URL with a version stamp so browsers fetch new files after a deploy."""
        try:
            version = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
        except OSError:
            version = 0
        return url_for("static", filename=filename, v=version)

    @app.context_processor
    def inject_globals():
        return {
            "asset": asset,
            "current_user": g.get("user"),
            "current_year": datetime.now(timezone.utc).year,
            "genres": book_service.GENRES,
            "popular_authors": book_service.POPULAR_AUTHORS,
            "statuses": STATUSES,
            "saved_status": saved_status,
            "default_cover": book_service.DEFAULT_COVER,
        }


def _wants_json():
    return request.headers.get("X-Requested-With") == "fetch"


def _register_error_handlers(app):
    def page(code, title, message):
        if _wants_json():
            return jsonify(ok=False, message=message), code
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(404)
    def not_found(_):
        return page(404, "Page not found", "That page is not on our shelves.")

    @app.errorhandler(429)
    def too_many(_):
        return page(429, "Slow down a little", "Too many requests. Please wait a minute and try again.")

    @app.errorhandler(500)
    def server_error(_):
        return page(500, "Something went wrong", "An unexpected error occurred. Please try again.")

    @app.errorhandler(CSRFError)
    def csrf_error(_):
        message = "Your session expired. Please try that again."
        if _wants_json():
            return jsonify(ok=False, message=message), 400
        flash(message, "error")
        return redirect(request.referrer or url_for("main.home"))
