from flask import Flask, render_template, request, redirect, url_for, flash, session
import requests
from flask_sqlalchemy import SQLAlchemy
import re
from werkzeug.security import generate_password_hash, check_password_hash

GOOGLE_API_KEY="AIzaSyBu58B_1R5bMqUje7lbpFi-qR8WslABVHk"
NYT_API_KEY="sM41gAH1cpXDT9vWpwGQFqefZKG4sreP"

def clean_cover_url(url):
    if url:
        return url.split('&edge=curl')[0]
    return '/static/default_cover.jpg'

# Fetch NYT trending books
def fetch_nyt_trending_books():
    url = f'https://api.nytimes.com/svc/books/v3/lists/current/hardcover-fiction.json?api-key={NYT_API_KEY}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        books = data.get('results', {}).get('books', [])
        
        standardized_books = []
        for book in books:
            authors = book.get('author', 'Unknown Author')
            
            standardized_book = {
                'title': book.get('title', 'Unknown Title'),
                'author': authors,
                'cover_url': clean_cover_url(book.get('book_image', '/static/default_cover.jpg')),
                'description': book.get('description', 'No description available'),
                'publisher': book.get('publisher', 'Unknown'),
                'publishedDate': book.get('published_date', 'Unknown'),
                'pageCount': 'Unknown',  # NYT API may not provide this
                'categories': book.get('book_details', [{}])[0].get('categories', []),
                'averageRating': book.get('book_details', [{}])[0].get('average_rating', 'No rating'),
                'retailPrice': book.get('price', 'Not for sale'),
            }
            info_link = url_for('book_details_nyt', title=standardized_book["title"])
            standardized_book['infoLink'] = info_link
            standardized_books.append(standardized_book)
        
        return standardized_books[:15]  # Return top 12 trending books
    except requests.exceptions.RequestException as e:
        print(f"Error fetching NYT trending books: {e}")
        return []

# Fetch NYT bestsellers
def fetch_nyt_bestsellers():
    url = f'https://api.nytimes.com/svc/books/v3/lists/current/hardcover-nonfiction.json?api-key={NYT_API_KEY}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        books = data.get('results', {}).get('books', [])
        
        standardized_books = []
        for book in books:
            authors = book.get('author', 'Unknown Author')
            
            standardized_book = {
                'title': book.get('title', 'Unknown Title'),
                'author': authors,
                'cover_url': clean_cover_url(book.get('book_image', '/static/default_cover.jpg')),
                'description': book.get('description', 'No description available'),
                'publisher': book.get('publisher', 'Unknown'),
                'publishedDate': book.get('published_date', 'Unknown'),
                'pageCount': 'Unknown',  # NYT API may not provide this
                'categories': book.get('book_details', [{}])[0].get('categories', []),
                'averageRating': book.get('book_details', [{}])[0].get('average_rating', 'No rating'),
                'retailPrice': book.get('price', 'Not for sale'),
            }
            info_link = url_for('book_details_nyt', title=standardized_book["title"])
            standardized_book['infoLink'] = info_link
            standardized_books.append(standardized_book)
        
        return standardized_books[:15]  # Return top 12 bestsellers
    except requests.exceptions.RequestException as e:
        print(f"Error fetching NYT bestsellers: {e}")
        return []
    
def search_books(query, search_type='title'):
    if search_type == 'title':
        url = f'https://openlibrary.org/search.json?title={query}'
    else:
        return []

    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        seen_books = set()
        books = []

        for book in data.get('docs', []):
            # Filter out non-English books
            if book.get('language') and 'eng' not in book['language']:
                continue

            title = book.get('title', 'Unknown Title')
            authors = ', '.join(book.get('author_name', ['Unknown Author']))
            cover_id = book.get('cover_i')
            isbn = book.get('isbn', ['Unknown ISBN'])[0]  # Assuming first ISBN is the correct one

            # Skip books with no cover image or unknown author
            if not cover_id or authors == 'Unknown Author':
                continue

            # Create a unique identifier for each book
            unique_id = f"{title}-{authors}"
            if unique_id not in seen_books:
                seen_books.add(unique_id)
                cover_url = f'https://covers.openlibrary.org/b/id/{cover_id}-M.jpg' if cover_id else '/static/default_cover.jpg'

                # Generate the correct infoLink using the ISBN (if available)
                info_link = url_for('book_details', isbn=isbn)  # Use ISBN in the URL

                books.append({
                    'title': title,
                    'author': authors,
                    'cover_url': cover_url,
                    'infoLink': info_link,  # Link to the Flask route using ISBN
                    'isbn': isbn  # Pass ISBN along with other book info
                })

        return books
    except requests.exceptions.RequestException as e:
        print(f'Error fetching search results: {e}')
        return []


def fetch_books_by_genre(genre, max_results=15):
    url = f'https://www.googleapis.com/books/v1/volumes?q=subject:{genre}&maxResults={max_results}&key={GOOGLE_API_KEY}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        books = []
        
        for item in data.get('items', []):
            volume_info = item.get('volumeInfo', {})
            sale_info = item.get('saleInfo', {})
            
            authors = volume_info.get('authors', ['Unknown Author'])
            author_str = ', '.join(authors)  # Convert list to string
            
            book = {
                'id': item.get('id', 'Unknown ID'),
                'title': volume_info.get('title', 'Unknown Title'),
                'author': author_str,
                'cover_url': clean_cover_url(volume_info.get('imageLinks', {}).get('thumbnail', '/static/default_cover.jpg')),
                'description': volume_info.get('description', 'No description available'),
                'publisher': volume_info.get('publisher', 'Unknown'),
                'publishedDate': volume_info.get('publishedDate', 'Unknown'),
                'pageCount': volume_info.get('pageCount', 'Unknown'),
                'categories': volume_info.get('categories', []),
                'averageRating': volume_info.get('averageRating', 'No rating'),
                'isbn': next((identifier.get('identifier', 'Unknown ISBN') 
                              for identifier in volume_info.get('industryIdentifiers', []) 
                              if identifier.get('type') == 'ISBN_13'), 'Unknown ISBN'),
                'retailPrice': sale_info.get('retailPrice', {}).get('amount', 'Not for sale'),
            }
            info_link = url_for('book_details', isbn=book['isbn'])  # Use ISBN in the URL
            book['infoLink'] = info_link
            
            books.append(book)
        
        return books
    except requests.exceptions.RequestException as e:
        print(f"Error fetching books by genre '{genre}': {e}")
        return []


def fetch_books_by_author(author, max_results=15):
    url = f'https://www.googleapis.com/books/v1/volumes?q=inauthor:{author}&maxResults={max_results}&key={GOOGLE_API_KEY}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        books = []
        
        for item in data.get('items', []):
            volume_info = item.get('volumeInfo', {})
            sale_info = item.get('saleInfo', {})
            
            authors = volume_info.get('authors', ['Unknown Author'])
            author_str = ', '.join(authors)  # Convert list to string
            
            book = {
                'id': item.get('id', 'Unknown ID'),  # Add the book ID
                'title': volume_info.get('title', 'Unknown Title'),
                'author': author_str,
                'cover_url': clean_cover_url(volume_info.get('imageLinks', {}).get('thumbnail', '/static/default_cover.jpg')),
                'description': volume_info.get('description', 'No description available'),
                'publisher': volume_info.get('publisher', 'Unknown'),
                'publishedDate': volume_info.get('publishedDate', 'Unknown'),
                'pageCount': volume_info.get('pageCount', 'Unknown'),
                'categories': volume_info.get('categories', []),
                'averageRating': volume_info.get('averageRating', 'No rating'),
                'isbn' : volume_info.get('industryIdentifiers', [{}])[0].get('identifier', 'Unknown ISBN'),
                'retailPrice': sale_info.get('retailPrice', {}).get('amount', 'Not for sale'),
            }
            info_link = url_for('book_details', isbn=book['isbn'])  
            book['infoLink'] = info_link
            books.append(book)
        
        return books
    except requests.exceptions.RequestException as e:
        print(f"Error fetching books by author '{author}': {e}")
        return []

# Fetch NYT bestsellers
def fetch_nyt_YA():
    url = f'https://api.nytimes.com/svc/books/v3/lists/current/young-adult-hardcover.json?api-key={NYT_API_KEY}'
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        books = data.get('results', {}).get('books', [])
        
        standardized_books = []
        for book in books:
            authors = book.get('author', 'Unknown Author')
            
            standardized_book = {
                'title': book.get('title', 'Unknown Title'),
                'author': authors,
                'cover_url': clean_cover_url(book.get('book_image', '/static/default_cover.jpg')),
                'description': book.get('description', 'No description available'),
                'publisher': book.get('publisher', 'Unknown'),
                'publishedDate': book.get('published_date', 'Unknown'),  # This might not be available
                'pageCount': 'Unknown',  # NYT API may not provide this
                'categories': [],  # NYT API may not provide this
                'averageRating': 'No rating',  # NYT API may not provide this
                'retailPrice': book.get('price', 'Not for sale'),
            }
            info_link = url_for('book_details_nyt', title=standardized_book["title"])
            standardized_book['infoLink'] = info_link
            standardized_books.append(standardized_book)
        
        return standardized_books[:9]  # Return top 12 bestsellers
    except requests.exceptions.RequestException as e:
        print(f"Error fetching NYT bestsellers: {e}")
        return []
    