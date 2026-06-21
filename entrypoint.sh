#!/bin/sh
set -e

echo "🗄️  Migrationen..."
python manage.py migrate --noinput

echo "📁 Static Files sammeln..."
python manage.py collectstatic --noinput

echo "🚀 Starte Gunicorn..."
exec gunicorn \
    --bind 0.0.0.0:8000 \
    --workers 3 \
    --timeout 300 \
    --access-logfile - \
    --error-logfile - \
    config.wsgi:application
