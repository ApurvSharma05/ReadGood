# 📖 ReadGood

**ReadGood** is a book discovery and management web app built with **Flask, HTML, CSS, and JavaScript**.  
It lets users explore books, view details, track personal reading lists, and authenticate via login/register.  

---

## 🚀 Features
- 🔍 **Search & Explore** books by title, author, genre, or API (NYT, Google Books, etc.)  
- 📚 **Personal Reading List** with user-specific saved books  
- 📝 **Book Details Pages** for more information  
- 👤 **User Authentication** (login/register)  
- 🌍 Responsive UI with modular CSS (navbar, hero, etc.)  
- 📊 Integration-ready with external book APIs  

---

## 🛠️ Tech Stack
- **Frontend:** HTML, CSS (modular stylesheets), SVG assets  
- **Backend:** Flask (Python)  
- **Templates:** Jinja2 (Flask templating engine)  
- **Database:** SQLAlchemy (from `models.py`)  
- **Environment:** `.env` for secret keys/config  

---

## 📂 Project Structure
```
ReadGood/
├── instance/              # Flask instance folder (DB, configs)
├── static/                # Static assets (CSS, images, icons)
│   ├── default_cover.jpg
│   ├── favicon.ico
│   ├── hero.css
│   ├── index.css
│   ├── navbar.css
│   ├── logo.svg
│   └── logout.svg
├── templates/             # HTML templates
│   ├── author.html
│   ├── base.html
│   ├── book_details.html
│   ├── book_nyt.html
│   ├── genre.html
│   ├── home.html
│   ├── landing.html
│   ├── login.html
│   ├── register.html
│   ├── search_results.html
│   └── user_books.html
├── app.py                 # Main Flask app
├── models.py              # Database models
├── util.py                # Helper functions
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables
└── .gitignore             # Git ignore rules
```

---

## ⚙️ Installation & Setup

1. **Clone the repo**
   ```bash
   git clone https://github.com/your-username/ReadGood.git
   cd ReadGood
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate   # Linux/Mac
   venv\Scripts\activate      # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables**  
   Create a `.env` file in the root directory:
   ```
   FLASK_APP=app.py
   FLASK_ENV=development
   SECRET_KEY=your_secret_key
   ```

5. **Run the app**
   ```bash
   flask run
   ```

---

## 💡 Usage
- Visit: `http://127.0.0.1:5000/`  
- Browse landing & home pages  
- Search for books and explore genres/authors  
- Create an account → Login → Manage personal reading list  

---

## 🤝 Contributing
Want to improve **ReadGood**?  
- Fork the repo  
- Create a branch (`git checkout -b feature-xyz`)  
- Commit (`git commit -m "Added xyz feature"`)  
- Push (`git push origin feature-xyz`)  
- Create a Pull Request  

---

## 📜 License
Licensed under the **MIT License**.  
