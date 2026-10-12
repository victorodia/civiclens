FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (e.g. for pytesseract, psycopg2)
RUN apt-get update && apt-get install -y tesseract-ocr libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Add extra production dependencies
RUN pip install --no-cache-dir -r requirements.txt gunicorn redis psycopg2-binary uvicorn[standard] qrcode

COPY . .

# Run with Gunicorn using Uvicorn workers.
# 2 workers: the VM has ~956MB RAM and 4 workers gets workers OOM-killed
# under load ( nationwide monitor map, builds); 2 async workers suffice.
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8001", "app.main:app"]
