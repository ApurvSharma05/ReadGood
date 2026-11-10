FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py gunicorn.conf.py ./
COPY readgood ./readgood

# Run as an unprivileged user; instance/ holds the SQLite file when no
# DATABASE_URL is set (mount a volume there to keep it between deploys).
RUN useradd --create-home appuser && mkdir -p /app/instance && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["gunicorn", "app:app", "-c", "gunicorn.conf.py"]
