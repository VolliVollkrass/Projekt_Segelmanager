# Segelmanager "Meer erleben" — Claude Kontext

## Tech Stack

| Was | Detail |
|---|---|
| Backend | Django 5.2, Python 3.13 |
| Frontend | Tailwind v4 (kein Config-File!), DaisyUI v5 |
| Datenbank | PostgreSQL 15, Docker |
| Auth | AbstractUser, E-Mail-Login (kein allauth, kein username) |
| E-Mail | django-anymail 15.0 → Brevo REST API |
| PDF | ReportLab (Crewliste) |
| Static Files | WhiteNoise (CompressedStaticFilesStorage) |
| Bilder | django-imagekit + Pillow |

## Infrastruktur

- **Hosting**: Hetzner VPS, Docker Compose, Traefik v2 Reverse Proxy
- **Traefik certresolver**: heißt `le` (nicht `letsencrypt`!)
- **Docker-Service**: heißt `segelmanager` (nicht `web`)
- **Domain**: undmeererleben.de / segelmanager.undmeererleben.de
- **Media-Serving**: `re_path + serve` in `config/urls.py` — `static()` gibt `[]` zurück wenn `DEBUG=False`

## Deploy-Workflow

```bash
# Lokal: CSS bauen und committen (muss im Repo sein!)
npm run build:css
git add static/css/src/output.css
git commit -m "..."
git push

# Server
cd ~/docker/segelmanager
git pull
docker compose build segelmanager
docker compose up -d
docker compose exec segelmanager python manage.py migrate
```

## Projektstruktur

```
accounts/    User-Model, Login, Registrierung, E-Mail-Verifikation, Passwort-Reset
toern/       Törns, Teilnahmen, Skipper-Dashboard, Crewliste, Packliste, Kabinenzuteilung
boote/       Boot- und Kabinen-Modelle
logistik/    Einkauf, Mahlzeiten, Mitbringer
home/        Startseite / Törn-Übersicht
utils/       Hilfsfunktionen (Profil-Fortschritt, Permissions, Packlisten-Daten)
templates/   Globale Templates (base.html, nav, bottom_nav, footer)
config/      settings.py, urls.py
```

## Rollen & Berechtigungen

| Rolle | Zugang |
|---|---|
| Anonym | Startseite, Törn-Details |
| Crew | Crew-Dashboard, Profil |
| Skipper / Co-Skipper | + Skipper-Dashboard (Übersicht / Zuteilung / Crew / Packliste) |
| Anbieter (`is_anbieter=True`) | + Anbieter-Dashboard, Törn erstellen/bearbeiten |
| Staff (`is_staff=True`) | + Django Admin |

Decorators: `@login_required`, `@anbieter_required` (utils/permissions.py), `@require_POST`

## Frontend-Konventionen

- **Mobile-first**: Bottom-Nav für Mobile, Top-Nav für Desktop (`lg:hidden` / `hidden lg:flex`)
- **Tailwind v4**: kein `tailwind.config.js`, Auto-Scan aller Templates; CSS-Build: `npm run build:css`
- **DaisyUI v5**: `btn`, `card`, `badge`, `alert`, `modal`, `tabs`, `avatar`, `progress`
- **Kein DiceBear**: Avatare ohne Profilbild = CSS-Initialen-Div
- **Flash-Messages**: DaisyUI `alert` in `base.html`
- **Safe Area iPhone**: `viewport-fit=cover` + `env(safe-area-inset-bottom)` am Bottom-Nav, `pb-28 lg:pb-0` am `<main>`
- **Theme**: Eigenes DaisyUI-Theme "segelmanager" — Primary: dunkles Blau, Secondary: Teal (#0D9488)
- **output.css muss committed werden** — kein Build-Step im Container

## Bekannte Fallstricke

- **WhiteNoise + Tailwind v4**: `CompressedManifestStaticFilesStorage` bricht → `CompressedStaticFilesStorage` verwenden
- **PostgreSQL 15+**: `GRANT ALL ON SCHEMA public TO segelmanager_user` nach DB-Erstellung manuell setzen
- **schema_viewer**: Nur wenn `DEBUG=True` aktiv
- **Kabinenpartner-Logik**: Gegenseitig — accepted löscht alle anderen Anfragen beider User
- **E-Mail**: HETZNER BLOCKIERT SMTP-PORTS (587/465/2525) → Brevo REST API via anymail verwenden, nie SMTP

## Wichtige Dateien

| Datei | Inhalt |
|---|---|
| `config/settings.py` | Alle Django-Settings, env-basiert (django-environ) |
| `config/urls.py` | URL-Config inkl. `re_path + serve` für Media |
| `docker-compose.yml` | Traefik-Labels, Volumes, Netzwerk |
| `Dockerfile` | Python 3.13-slim, non-root appuser (uid=1000) |
| `entrypoint.sh` | migrate → collectstatic → gunicorn |
| `.env.example` | Template für Server-.env (Secrets nie in git!) |
| `templates/base.html` | Basis-Template: Nav, Main, Footer, Flash-Messages, Verifikations-Banner |
| `toern/crew_utils.py` | `CREWLISTE_FELDER` (12 Pflichtfelder), `fehlende_crew_felder(user)` |
| `toern/emails.py` | Alle E-Mail-Versand-Funktionen |
| `static/css/src/output.css` | Gebautes CSS — muss committed sein! |
