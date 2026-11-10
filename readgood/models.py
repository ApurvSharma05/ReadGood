"""Database models.

Table names match the original app so an existing books.db keeps working;
ensure_schema() adds the columns introduced since then.
"""
from datetime import datetime, timezone

from sqlalchemy import inspect, text

from .extensions import db

STATUSES = {
    "want": "Want to read",
    "reading": "Reading",
    "read": "Read",
}


def utcnow():
    """Naive UTC timestamp (SQLite does not keep timezone info)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Account(db.Model):
    __tablename__ = "account"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    yearly_goal = db.Column(db.Integer)

    entries = db.relationship(
        "UserBook", back_populates="account", cascade="all, delete-orphan"
    )


class Book(db.Model):
    __tablename__ = "book"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    author = db.Column(db.String(300), nullable=False)
    cover_url = db.Column(db.String(500))
    more_info_link = db.Column(db.String(300))  # links saved by the old app
    source = db.Column(db.String(20), index=True)  # google | ol | isbn
    source_id = db.Column(db.String(64), index=True)
    categories = db.Column(db.String(400))
    year = db.Column(db.Integer)

    entries = db.relationship("UserBook", back_populates="book")

    @property
    def category_list(self):
        return [c.strip() for c in (self.categories or "").split("|") if c.strip()]


class UserBook(db.Model):
    __tablename__ = "user_book_list"
    __table_args__ = (
        db.UniqueConstraint("user_id", "book_id", name="unique_user_book"),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False, index=True)
    book_id = db.Column(db.Integer, db.ForeignKey("book.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="want", server_default="want")
    rating = db.Column(db.Integer)
    notes = db.Column(db.Text)
    added_at = db.Column(db.DateTime, default=utcnow)
    finished_at = db.Column(db.DateTime)

    account = db.relationship("Account", back_populates="entries")
    book = db.relationship("Book", back_populates="entries")

    @property
    def status_label(self):
        return STATUSES.get(self.status, STATUSES["want"])


def ensure_schema():
    """Add columns that exist on the models but not yet in the database.

    A small stand-in for a migration tool: it only ever adds columns, so it is
    safe to run on every start, on both SQLite and Postgres.
    """
    engine = db.engine
    inspector = inspect(engine)
    statements = []
    for table in db.metadata.sorted_tables:
        if not inspector.has_table(table.name):
            continue
        existing = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing:
                continue
            ddl = (
                f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
                f"{column.type.compile(dialect=engine.dialect)}"
            )
            if column.server_default is not None:
                ddl += f" DEFAULT '{column.server_default.arg}'"
                if not column.nullable:
                    ddl += " NOT NULL"
            statements.append(ddl)
    if statements:
        with engine.begin() as conn:
            for ddl in statements:
                conn.execute(text(ddl))
