from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Book(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    cover_url = db.Column(db.String(500))
    more_info_link = db.Column(db.String(200), nullable=True)

class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    user_books = db.relationship('UserBookList', backref='account', lazy=True)

class UserBookList(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('account.id'), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('book.id'), nullable=False)
    book = db.relationship('Book', backref=db.backref('book_users', lazy=True))
    user = db.relationship('Account', backref=db.backref('account_books', lazy=True))
    __table_args__ = (db.UniqueConstraint('user_id', 'book_id', name='unique_user_book'),)
