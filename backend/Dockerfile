FROM python:3.10-slim

WORKDIR /app

# Install system dependencies (e.g. for pytesseract, psycopg2)
RUN apt-get update && apt-get install -y tesseract-ocr libpq-dev gcc && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# Add extra production dependencies
RUN pip install --no-cache-dir -r requirements.txt gunicorn redis psycopg2-binary uvicorn[standard] qrcode

COPY . .

# Run with Gunicorn using Uvicorn workers (4 workers)
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "4", "-b", "0.0.0.0:8001", "app.main:app"]
