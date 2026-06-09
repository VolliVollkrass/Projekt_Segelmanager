# Projektkontext: Segelmanager "Meer erleben"

## Was ist das Projekt?
Eine Django-Webapp zur Verwaltung von Segeltörns. Anbieter erstellen Törns, Crew-Mitglieder melden sich an, Skipper verwalten Kabinenzuteilung und Packlisten.

---

## Tech Stack

| Was | Version |
|---|---|
| Backend | Django 5.2 |
| Frontend | Tailwind CSS 4.2.1 + DaisyUI 5.5.19 |
| Datenbank | PostgreSQL 16 (Hetzner VPS) |
| Hosting | Hetzner VPS CX22, Ubuntu 26.04, IP: 46.224.226.138 |
| Reverse Proxy | Traefik v2.11 mit Let's Encrypt SSL |
| Container | Docker + docker-compose |
| Auth | E-Mail-basiert (AbstractUser), django-axes für Login-Schutz |
| PDF | ReportLab (Crewliste) |
| Bilder | django-imagekit + Pillow |
| Static Files | WhiteNoise (CompressedStaticFilesStorage) |

---

## Infrastruktur (Hetzner VPS)

### Server-Details
- **IP**: 46.224.226.138
- **User**: volker (sudo)
- **Domain**: undmeererleben.de
- **App-URL**: https://segelmanager.undmeererleben.de

### Verzeichnisstruktur auf dem Server
```
~/docker/
├── traefik/          # Traefik Reverse Proxy + Let's Encrypt
│   ├── docker-compose.yml
│   └── letsencrypt/acme.json
├── postgres/         # Geteilte PostgreSQL-Instanz
│   └── docker-compose.yml
├── segelmanager/     # Git-Klon des Projekts (= Projektverzeichnis)
│   ├── .env          # Produktions-Secrets (nicht im Git!)
│   └── media/        # User-Uploads (persistentes Volume)
└── camperbase/       # Zukünftiges Projekt (noch leer)
```

### Traefik-Konfiguration (wichtig für neue Projekte)
- Certresolver heißt **`le`** (nicht `letsencrypt`!)
- Netzwerk: `traefik-proxy` (external)
- HTTP→HTTPS Redirect läuft **global** über Traefik-Entrypoint
- Kein separater HTTP-Router in docker-compose nötig

### PostgreSQL-Zugangsdaten (Segelmanager)
- Host: `postgres` (Docker-interner Hostname)
- Datenbank: `segelmanager`
- User: `segelmanager_user`
- Superuser des PG-Containers: `admin`

### Deployment-Befehl (vom Mac aus)
```bash
# Lokal: CSS bauen, committen, pushen
npm run build:css
git add static/css/src/output.css
git commit -m "..."
git push origin main

# Auf Server deployen
ssh volker@46.224.226.138 "cd ~/docker/segelmanager && git pull origin main && docker compose build && docker compose up -d"
```

### deploy.sh (liegt im Repo, auf Server ausführen)
```bash
bash ~/docker/segelmanager/deploy.sh
```

---

## Projektstruktur

```
Segelmanager/
├── accounts/          # User-Modell, Login, Registrierung, Profil, Lizenzen, Onboarding
├── toern/             # Kernlogik: Törns, Teilnahmen, Kabinen, Packlisten, Skipper/Crew-Views
├── boote/             # Boot- und Kabinen-Modelle
├── home/              # Startseite / Törn-Übersicht
├── logistik/          # Boot-Packliste, Einkaufsliste, Mitbringer
├── finance/           # Zahlungslogik (rudimentär)
├── utils/             # Hilfsfunktionen (Profil-Fortschritt, Permissions, Packlisten-Daten)
├── templates/         # Globale Templates (base.html, nav, bottom_nav, footer)
├── static/css/src/    # input.css + output.css (Tailwind Build)
├── Dockerfile         # Python 3.13-slim, non-root appuser
├── entrypoint.sh      # migrate → collectstatic → gunicorn
├── docker-compose.yml # Traefik-Labels, Media-Volume, traefik-proxy Netzwerk
├── .env.example       # Template für Server-.env
└── package.json       # npm: "build:css" Befehl
```

---

## Wichtige Modelle

### User (accounts/models.py — AbstractUser)
Felder: `email` (Login), `first_name`, `last_name`, `telefonnummer`, `geburtsdatum`, `geburtsort`, `geburtsland`, `nationalitaet`, `identifikationstyp`, `passnummer`, `strasse`, `plz`, `ort`, `land`, `geschlecht`, `profilbild`, `is_anbieter`

### Toern (toern/models.py)
Felder: `titel`, `revier`, `startdatum`, `enddatum`, `preis_pro_person`, `nebenkosten`, `status` (DRAFT/ANMELDUNG_OFFEN/ANMELDUNG_GESCHLOSSEN/ZUTEILUNG_FIXIERT), `anbieter` (FK User), `bild_toern`, `anmeldeschluss`

### Teilnahme (toern/models.py)
Verbindet User ↔ Toern. Felder: `status` (angemeldet/warteliste/bestaetigt/abgesagt/abgelehnt), `rolle` (crew/skipper/coskipper), `boot` (FK), `kabine` (FK), `seglerische_erfahrung`, `gesegelte_meilen`, `notizen`, `essgewohnheiten` (alles/vegetarisch/vegan), `lebensmittelunvertraeglichkeiten`

### Boot (boote/models.py) → hat Kabinen (boote/models.py)
### KabinenWunsch (toern/models.py) — Kabinenpartner-Anfragen (pending/accepted/rejected)
### CrewPraeferenz (toern/models.py) — exclude/avoid Präferenzen für Auto-Zuteilung
### Lizenz (accounts/models.py) — Segellizenzen mit Dokument-Upload
### PacklisteVorlage / PacklisteVorlageEintrag (toern/models.py) — Skipper-Vorlagen
### Mahlzeit (logistik/models.py) — Datum, Typ, Name, Kochverantwortlicher

---

## Rollen & Berechtigungen

| Rolle | Zugang |
|---|---|
| Anonym | Startseite, Törn-Details |
| Crew | Crew-Übersicht, Crew-Dashboard (Tab: Info/Crew/Packliste/Meine Daten), Profilseiten |
| Skipper/Co-Skipper | + Skipper-Dashboard (Tabs: Übersicht/Zuteilung/Crew/Packliste) |
| Anbieter (`is_anbieter=True`) | + Anbieter-Dashboard, Törn erstellen/bearbeiten |
| Staff (`is_staff=True`) | + Django Admin |

Decorators: `@login_required`, `@anbieter_required` (utils/permissions.py), `@require_POST`

---

## URL-Muster (wichtigste)

```python
crew_overview        → /toern/meine/
crew_dashboard       → /toern/<id>/crew/          (Tab per ?tab=info|crew|packliste|daten)
skipper_dashboard    → /toern/<id>/skipper/       (Tab per ?tab=uebersicht|zuteilung|crew|packliste)
boot_dashboard       → /toern/<id>/boot/
anbieter_dashboard   → /anbieter/
my_account           → /accounts/profil/
account_edit         → /accounts/profil/bearbeiten/
onboarding           → /accounts/onboarding/      (nach Registrierung)
```

---

## Frontend-Konventionen

- **Mobile-first**: Bottom-Navigation (`templates/includes/bottom_nav.html`) für Mobile, Top-Nav für Desktop (`lg:hidden` / `hidden lg:flex`)
- **Kein Burger-Menü auf Mobile** — Bottom-Nav übernimmt alle Links
- **Tailwind v4**: Keine `tailwind.config.js`, Auto-Scan aller Templates; Build-Befehl: `npm run build:css`
- **DaisyUI v5**: Komponenten wie `btn`, `card`, `badge`, `alert`, `modal`, `tabs`, `avatar`, `progress`
- **Kein DiceBear**: Avatare ohne Profilbild = CSS-Initialen-Div (kein externer HTTP-Request)
- **Flash-Messages**: DaisyUI `alert` Komponente mit Icons in `base.html`
- **Safe Area iPhone**: `viewport-fit=cover` + `env(safe-area-inset-bottom)` am Bottom-Nav, `pb-28 lg:pb-0` am `<main>`
- **Theme** (`input.css`): Eigenes DaisyUI-Theme "segelmanager" — Primary: dunkles Blau, Secondary: Teal (#0D9488)

---

## E-Mail-Integration — Stand & nächste Schritte

### Ziel
Vollständige Mailintegration mit:
1. **E-Mail-Verifikation** bei Registrierung (custom Token, kein allauth)
2. **Passwort-Reset** (Django built-in, nur Backend konfigurieren)
3. **Info-Mails** (Bootszuteilung erledigt, Dashboard freigeschaltet etc.)
4. **Erinnerungsmails** (Profil unvollständig, Daten fehlen etc.)

### Mail-Provider: Brevo
- **Warum**: Französisches EU-Unternehmen, DSGVO-konform, 300 Mails/Tag kostenlos
- **Account**: Noch nicht angelegt → **erster Schritt in der neuen Session**
- **SMTP-Daten** (nach Brevo-Registrierung eintragen):
  - Host: `smtp-relay.brevo.com`
  - Port: `587`
  - User: die bei Brevo registrierte E-Mail-Adresse
  - Password: SMTP-Key aus Brevo-Dashboard (unter Transactional → SMTP & API)

### .env auf dem Server ergänzen (nach Brevo-Setup)
```bash
ssh volker@46.224.226.138
nano ~/docker/segelmanager/.env
```
Folgende Zeilen eintragen:
```
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=deine@email.de
EMAIL_HOST_PASSWORD=xsmtpib-XXXXXXXXXXXXXXXX
DEFAULT_FROM_EMAIL=Meer erleben <info@undmeererleben.de>
```

### settings.py — E-Mail-Backend noch nicht konfiguriert!
Diese Settings fehlen noch in `config/settings.py` und müssen ergänzt werden:
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = env('EMAIL_HOST', default='localhost')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = True
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='noreply@beispiel.de')
```
Lokal (für Tests): `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'` in `.env` setzen.

### Implementierungsreihenfolge
1. Brevo-Account anlegen + Domain verifizieren (DNS-Einträge: SPF, DKIM)
2. `settings.py` E-Mail-Backend ergänzen
3. `.env` lokal + auf Server mit Brevo-Credentials füllen
4. Passwort-Reset aktivieren (Django built-in + Templates anpassen)
5. E-Mail-Verifikation bei Registrierung (custom Token in `accounts/`)
6. Info-Mails in Views (Bootszuteilung, Dashboard-Freischaltung)
7. Erinnerungsmails (Management Command + PythonAnywhere/Cron)

### Wichtig: Brevo Domain-Verifikation
Nach Brevo-Registrierung muss `undmeererleben.de` verifiziert werden:
- Brevo Dashboard → Senders & IPs → Domains → Domain hinzufügen
- DNS-Einträge (SPF + DKIM) beim Domain-Anbieter eintragen
- Dann kann als `info@undmeererleben.de` gesendet werden

---

## Performance-Patterns (bereits optimiert)

- `home/views.py`: `freie_plaetze` per Subquery-Annotation statt N×2 Queries
- `toern_detail`: Skipper-Query gebatcht (1 Query für alle Boote)
- `anbieter_dashboard`: `prefetch_related("boote__kabinen", "teilnahmen__user", "teilnahmen__boot")`
- `auto_assign`: `bulk_update` statt N individuelle UPDATE-Queries
- `Toern.freie_plaetze`: nutzt `_gesamtplaetze`/`_belegte_plaetze` Annotations wenn vorhanden

---

## Bekannte Eigenheiten / Fallstricke

- **Migrations**: `0012_remove_personalpacklistetemplate` nutzt `SeparateDatabaseAndState` — war nötig weil Tabelle auf PythonAnywhere nie existiert hatte
- **CSS Build**: Tailwind v4 scannt automatisch — `output.css` muss manuell committed werden
- **WhiteNoise + Tailwind**: `CompressedManifestStaticFilesStorage` bricht wegen `@import "tailwindcss"` in `input.css` → daher `CompressedStaticFilesStorage`
- **schema_viewer**: Nur wenn `DEBUG=True` aktiv (Production: deaktiviert)
- **Kabinenpartner**: Gegenseitige Anfrage-Logik in `KabinenWunsch` (pending → accepted löscht alle anderen Anfragen beider User)
- **PostgreSQL 15+**: `GRANT ALL ON SCHEMA public TO segelmanager_user` muss nach DB-Erstellung manuell gesetzt werden
- **Traefik certresolver**: Heißt `le` (nicht `letsencrypt`!)

---

## Wichtige Dateien auf einen Blick

| Datei | Inhalt |
|---|---|
| `config/settings.py` | Alle Django-Settings, env-basiert |
| `docker-compose.yml` | Traefik-Labels, Volumes, Netzwerk |
| `Dockerfile` | Python 3.13-slim, non-root appuser |
| `entrypoint.sh` | migrate → collectstatic → gunicorn |
| `.env.example` | Template für Server-Konfiguration |
| `deploy.sh` | git pull → docker build → up -d |
| `templates/base.html` | Basis-Template mit Nav, Main, Footer, Flash-Messages |
| `templates/includes/bottom_nav.html` | Mobile Bottom-Navigation |
| `templates/includes/nav.html` | Desktop Top-Navigation |
| `accounts/templates/accounts/onboarding.html` | 3-Schritt Onboarding nach Registrierung |
| `toern/templates/crew/crew_dashboard.html` | 4-Tab Crew-Ansicht |
| `toern/templates/skipper/skipper_dashboard.html` | 4-Tab Skipper-Ansicht mit Drag&Drop |
| `static/css/src/input.css` | Tailwind/DaisyUI Eingabe + Custom Theme |
| `static/css/src/output.css` | Gebautes CSS (ins Git committen!) |
