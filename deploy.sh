#!/bin/bash
set -e

echo "🚀 Starte Deployment Segelmanager..."

# Zum Projektverzeichnis wechseln
cd ~/docker/segelmanager

echo "📥 Hole neuesten Code..."
git pull origin main

echo "🔨 Baue Docker-Image..."
docker compose build

echo "🔁 Container neu starten..."
docker compose up -d

echo "🧹 Alte Images aufräumen..."
docker image prune -f

echo "✅ Deployment fertig! Läuft unter https://segelmanager.undmeererleben.de"
