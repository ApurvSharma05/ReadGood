"""Entry point.

Production:  gunicorn app:app -c gunicorn.conf.py
Development: flask --app app run --debug
"""
import os

from readgood import create_app

app = create_app()

if __name__ == "__main__":
    # Local use only: binds to localhost, and debug is opt-in via FLASK_DEBUG=1.
    app.run(
        host="127.0.0.1",
        port=int(os.getenv("PORT", "5000")),
        debug=os.getenv("FLASK_DEBUG", "0") == "1",
    )
