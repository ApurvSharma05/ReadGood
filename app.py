import os
import re
from flask import Flask, render_template, request, redirect, url_for, flash, session
import requests
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from util import fetch_books_by_genre, fetch_books_by_author, fetch_nyt_trending_books, fetch_nyt_bestsellers, search_books, clean_cover_url, fetch_nyt_YA
from dotenv import load_dotenv
from models import db, Book, Account, UserBookList

# Load environment variables
load_dotenv()

# Flask app and database setup
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///books.db'
app.config['SECRET_KEY'] = 'mysecretkey'
db.init_app(app)

# API keys
NYT_API_KEY = os.getenv('NYT_API_KEY')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')

# Routes
@app.route('/')
def landing():
    return render_template('landing.html')

# Login page
@app.route('/login', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form:
        username = request.form['username']
        password = request.form['password']
        account = Account.query.filter_by(username=username).first()
        if account and check_password_hash(account.password, password):
            session['loggedin'] = True
            session['id'] = account.id
            session['username'] = account.username
            msg = 'Logged in successfully!'
            return redirect(url_for('home'))
        else:
            msg = 'Incorrect username / password!'
    return render_template('login.html', msg=msg)

# Logout
@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    return redirect(url_for('login'))

# Register page
@app.route('/register', methods=['GET', 'POST'])
def register():
    msg = ''
    if request.method == 'POST' and 'username' in request.form and 'password' in request.form and 'email' in request.form:
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        account = Account.query.filter_by(username=username).first()
        if account:
            msg = 'Account already exists!'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            msg = 'Invalid email address!'
        elif not re.match(r'[A-Za-z0-9]+', username):
            msg = 'Username must contain only characters and numbers!'
        elif not username or not password or not email:
            msg = 'Please fill out the form!'
        else:
            hashed_password = generate_password_hash(password)
            new_account = Account(username=username, password=hashed_password, email=email)
            db.session.add(new_account)
            db.session.commit()
            msg = 'You have successfully registered!'
            flash(msg, 'success')
            return redirect(url_for('login'))
    elif request.method == 'POST':
        msg = 'Please fill out the form!'
    return render_template('register.html', msg=msg)

# Home page
@app.route('/home')
def home():
    if not session.get('loggedin'):
        return redirect(url_for('login'))
    trending_books = fetch_nyt_trending_books()
    bestseller_books = fetch_nyt_bestsellers()
    young_books = fetch_nyt_YA()

    return render_template(
        'home.html',
        trending_books=trending_books,
        bestseller_books=bestseller_books,
        young_books=young_books
    )

# User's book list
@app.route('/user_books')
def user_books():
    if not session.get('loggedin'):
        flash('Please log in to view your books.', 'error')
        return redirect(url_for('login'))
    
    user_id = session.get('id')
    user_books = UserBookList.query.filter_by(user_id=user_id).all()
    books = []
    for user_book in user_books:
        book = Book.query.get(user_book.book_id)
        if book:
            books.append({
                'id': book.id,
                'title': book.title,
                'author': book.author,
                'cover_url': book.cover_url,
                'more_info_link': book.more_info_link
            })
    return render_template('user_books.html', books=books)

# Search for books
@app.route('/search', methods=['GET', 'POST'])
def search():
    if not session.get('loggedin'):
        flash('Please log in to search for books.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        title_query = request.form.get('title', '').strip()
        books = []
        books += search_books(title_query, search_type='title')
        unique_books = { (book['title'], book['author']): book for book in books }
        books = list(unique_books.values())
        if not books:
            flash('No books found for the given input!', 'error')

        return render_template(
            'search_results.html', 
            books=books, 
            title_query=title_query, 
        )
# Books by Genres
@app.route('/genre/<code>')
def books_by_genre(code):
    if not session.get('loggedin'):
        flash('Please log in to view books by genre.', 'error')
        return redirect(url_for('login'))
    
    genres = {
        'FIC': 'Fiction',
        'FAN': 'Fantasy',
        'ROM': 'Romance',
        'MYS': 'Mystery',
        'THR': 'Thriller'
    }
    
    genre = genres.get(code.upper(), 'Unknown Genre')
    books = fetch_books_by_genre(genre)
    return render_template('genre.html', books=books, genre=genre)
# Books by Authors
@app.route('/author/<code>')
def books_by_author(code):
    if not session.get('loggedin'):
        flash('Please log in to view books by author.', 'error')
        return redirect(url_for('login'))
    
    authors = {
        'SK': 'Stephen King',
        'GM': 'George R.R. Martin',
        'WS': 'William Shakespeare',
        'HM': 'Haruki Murakami',
        'JA': 'Jane Austen'
    }
    
    author = authors.get(code.upper(), 'Unknown Author')
    author_books = fetch_books_by_author(author)
    return render_template('author.html', author_books=author_books, author_name=author)

# Fetch book details from Google Books API
@app.route('/book/<isbn>')
def book_details(isbn):
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{isbn}&key={GOOGLE_API_KEY}"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()

        book_data = data.get('items', [])[0] if data.get('items') else None

        if not book_data:
            flash('Book not found', 'error')
            return redirect(url_for('home'))

        volume_info = book_data.get('volumeInfo', {})
        title = volume_info.get('title', 'Unknown Title')
        authors = ', '.join(volume_info.get('authors', ['Unknown Author']))
        description = volume_info.get('description', 'Description not available')
        publisher = volume_info.get('publisher', 'Unknown Publisher')
        published_date = volume_info.get('publishedDate', 'Unknown Date')
        categories = ', '.join(volume_info.get('categories', []))
        cover_url = clean_cover_url(volume_info.get('imageLinks', {}).get('thumbnail', '/static/default_cover.jpg'))

        return render_template('book_details.html', 
                               title=title,
                               authors=authors,
                               description=description,
                               publisher=publisher,
                               published_date=published_date,
                               categories=categories,
                               cover_url=cover_url)

    except requests.exceptions.RequestException as e:
        flash(f'Error fetching book details: {e}', 'error')
        return redirect(url_for('home'))

# Fetch book details from NYT API
@app.route('/book/nyt/<title>')
def book_details_nyt(title):
    url_nonfiction = f'https://api.nytimes.com/svc/books/v3/lists/current/hardcover-nonfiction.json?api-key={NYT_API_KEY}'
    url_fiction = f'https://api.nytimes.com/svc/books/v3/lists/current/hardcover-fiction.json?api-key={NYT_API_KEY}'
    url_young = f'https://api.nytimes.com/svc/books/v3/lists/current/young-adult-hardcover.json?api-key={NYT_API_KEY}'
    
    try:
        response_nonfiction = requests.get(url_nonfiction)
        response_young = requests.get(url_young)
        response_fiction = requests.get(url_fiction)
        response_nonfiction.raise_for_status()
        response_fiction.raise_for_status()
        response_young.raise_for_status()
        
        data_nonfiction = response_nonfiction.json()
        data_fiction = response_fiction.json()
        data_young = response_young.json()
        
        books_nonfiction = data_nonfiction.get('results', {}).get('books', [])
        books_fiction = data_fiction.get('results', {}).get('books', [])
        books_young = data_young.get('results' , {}).get('books', [])
        
        books = books_nonfiction + books_fiction + books_young
        
        book = next((book for book in books if book['title'].lower() == title.lower()), None)
        
        if not book:
            flash('Book not found.', 'error')
            return redirect(url_for('home'))
        
        book_details = {
            'title': book.get('title', 'Unknown Title'),
            'authors': book.get('author', 'Unknown Author'),
            'description': book.get('description', 'No description available'),
            'publisher': book.get('publisher', 'Unknown'),
            'categories': 'Fiction' if book in books_fiction else 'Non-Fiction',
            'cover_url': book.get('book_image', '/static/default_cover.jpg'),
        }
        
        return render_template('book_nyt.html', book=book_details)
    
    except requests.exceptions.RequestException as e:
        flash('Failed to fetch book details.', 'error')
        return redirect(url_for('home'))
    
# Add book to user's list
@app.route('/add_book', methods=['POST'])
def add_book():
    if not session.get('loggedin'):
        flash('Please log in to add books.', 'error')
        return redirect(url_for('login'))
    
    title = request.form.get('title')
    author = request.form.get('author')
    info_link = request.form.get('infoLink')
    cover_url = clean_cover_url(request.form.get('cover_url'))
    
    if not title or not author:
        flash('Title and Author are required fields!', 'error')
        return redirect(url_for('home'))
    
    book = Book.query.filter_by(title=title, author=author, more_info_link=info_link).first()
    
    if not book:
        book = Book(title=title, author=author, cover_url=cover_url, more_info_link=info_link)
        db.session.add(book)
        db.session.commit()

    user_id = session.get('id')
    user_book = UserBookList.query.filter_by(user_id=user_id, book_id=book.id).first()
    if user_book:
        flash(f'Book "{title}" by {author} is already in your list!', 'error')
    else:
        user_book = UserBookList(user_id=user_id, book_id=book.id)
        db.session.add(user_book)
        db.session.commit()
        flash(f'Book "{title}" by {author} added to your list!', 'success')
    
    return redirect(url_for('user_books'))

# Remove book from user's list
@app.route('/remove_book/<int:book_id>', methods=['POST'])
def remove_book(book_id):
    if not session.get('loggedin'):
        flash('Please log in to remove books.', 'error')
        return redirect(url_for('login'))
    
    user_id = session.get('id')
    user_book = UserBookList.query.filter_by(user_id=user_id, book_id=book_id).first()
    if user_book:
        db.session.delete(user_book)
        db.session.commit()
        flash('Book removed from your list!', 'success')
    return redirect(url_for('user_books'))

if __name__ == '__main__':
    app.jinja_env.cache = {}
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)  # for local testing

