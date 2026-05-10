#!/bin/bash

echo "🚀 Starte Deployment..."

# Zum Projekt wechseln
cd /home/Blechmettl/segelmanager/Projekt_Segelmanager || exit

# Virtualenv aktivieren
source venv/bin/activate

echo "📥 Hole neuesten Code..."
git fetch origin
git reset --hard origin/main

echo "📦 Installiere neue Pakete..."
pip install -r requirements.txt

echo "🗄️ Migrationen..."
python manage.py migrate

echo "📁 Static Files..."
python manage.py collectstatic --noinput

echo "🔁 Reload Web App..."
touch /var/www/blechmettl_pythonanywhere_com_wsgi.py

echo "✅ Deployment fertig!"
