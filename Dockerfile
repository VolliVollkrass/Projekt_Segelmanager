FROM python:3.13-slim

# System-Abhängigkeiten für psycopg2, Pillow und pillow-heif
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    gcc \
    libheif-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements zuerst kopieren (Docker Layer-Caching nutzen)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Projektcode kopieren
COPY . .

# Entrypoint ausführbar machen
RUN chmod +x entrypoint.sh

# Nicht als root laufen
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
