"""Gunicorn settings for production. Run with: gunicorn app:app -c gunicorn.conf.py"""
import os

bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
workers = int(os.getenv("WEB_CONCURRENCY", "2"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "4"))
timeout = 30
keepalive = 5
# Create the app (and run the schema check) once, before workers start.
preload_app = True
accesslog = "-"
errorlog = "-"
