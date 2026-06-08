# Projektkontext: Segelmanager "Meer erleben"

## Was ist das Projekt?
Eine Django-Webapp zur Verwaltung von Segeltörns. Anbieter erstellen Törns, Crew-Mitglieder melden sich an, Skipper verwalten Kabinenzuteilung und Packlisten. Gehostet auf PythonAnywhere unter `blechmettl.pythonanywhere.com`.

---

## Tech Stack

| Was | Version |
|---|---|
| Backend | Django 5.2 |
| Frontend | Tailwind CSS 4.2.1 + DaisyUI 5.5.19 |
| Datenbank | SQLite (PythonAnywhere) |
| Hosting | PythonAnywhere (Free Tier) |
| Auth | E-Mail-basiert (AbstractUser), django-axes für Login-Schutz |
| PDF | ReportLab (Crewliste) |
| Bilder | django-imagekit + Pillow |

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
├── deploy.sh          # Deployment-Skript für PythonAnywhere
└── package.json       # npm: "build:css" Befehl
```

---

## Wichtige Modelle

### User (accounts/models.py — AbstractUser)
Felder: `email` (Login), `first_name`, `last_name`, `telefonnummer`, `geburtsdatum`, `geburtsort`, `geburtsland`, `nationalitaet`, `identifikationstyp`, `passnummer`, `strasse`, `plz`, `ort`, `land`, `geschlecht`, `profilbild`, `is_anbieter`

### Toern (toern/models.py)
Felder: `titel`, `revier`, `startdatum`, `enddatum`, `preis_pro_person`, `nebenkosten`, `status` (DRAFT/ANMELDUNG_OFFEN/ANMELDUNG_GESCHLOSSEN/ZUTEILUNG_FIXIERT), `anbieter` (FK User), `bild_toern`, `anmeldeschluss`
Properties: `freie_plaetze`, `gesamtplaetze`, `gesamtpreis` — unterstützen DB-Annotationen via `_gesamtplaetze` / `_belegte_plaetze` für Performance

### Teilnahme (toern/models.py)
Verbindet User ↔ Toern. Felder: `status` (angemeldet/warteliste/bestaetigt/abgesagt/abgelehnt), `rolle` (crew/skipper/coskipper), `boot` (FK), `kabine` (FK), `seglerische_erfahrung`, `gesegelte_meilen`, `notizen`

### Boot (boote/models.py) → hat Kabinen (boote/models.py)
### KabinenWunsch (toern/models.py) — Kabinenpartner-Anfragen (pending/accepted/rejected)
### CrewPraeferenz (toern/models.py) — exclude/avoid Präferenzen für Auto-Zuteilung
### Lizenz (accounts/models.py) — Segellizenzen mit Dokument-Upload
### PacklisteVorlage / PacklisteVorlageEintrag (toern/models.py) — Skipper-Vorlagen

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

## Deployment-Workflow

### Lokal entwickeln → CSS bauen → pushen:
```bash
npm run build:css          # Tailwind CSS neu bauen (IMMER vor Push!)
git add static/css/src/output.css
git commit -m "..."
git push origin main
```

### PythonAnywhere deployen:
```bash
./deploy.sh
```
Das Skript: git pull → pip install → migrate → collectstatic → WSGI reload

### Wichtig:
- `output.css` MUSS ins Git committed sein (PythonAnywhere baut kein npm)
- SQLite-Datenbank liegt lokal auf PythonAnywhere, wird nicht versioniert
- Static Files: `python manage.py collectstatic` kopiert nach `staticfiles/`

---

## Performance-Patterns (bereits optimiert)

- `home/views.py`: `freie_plaetze` per Subquery-Annotation statt N×2 Queries
- `toern_detail`: Skipper-Query gebatcht (1 Query für alle Boote)
- `anbieter_dashboard`: `prefetch_related("boote__kabinen", "teilnahmen__user", "teilnahmen__boot")`
- `auto_assign`: `bulk_update` statt N individuelle UPDATE-Queries
- `Toern.freie_plaetze`: nutzt `_gesamtplaetze`/`_belegte_plaetze` Annotations wenn vorhanden

---

## Bekannte Eigenheiten / Fallstricke

- **Migrations**: `0012_remove_personalpacklistetemplate` nutzt `SeparateDatabaseAndState` + `DROP TABLE IF EXISTS` — war nötig weil auf PythonAnywhere die Tabelle nie existiert hatte
- **CSS Build**: Tailwind v4 scannt automatisch — aber `output.css` muss manuell committed werden
- **Kabinenpartner**: Gegenseitige Anfrage-Logik in `KabinenWunsch` (pending → accepted löscht alle anderen Anfragen beider User)
- **Auto-Zuteilung**: Scoring-Algorithmus mit Alter/Erfahrung/Geschlecht-Modi, Skipper werden fixiert
- **`teilnahme_fortschritt`** (utils): Berechnet Vollständigkeit einer Teilnahme für Skipper-Dashboard
- **`user_profil_fortschritt`** (utils): Berechnet Profil-Vollständigkeit (0–100%) für Onboarding-Banner

---

## Wichtige Dateien auf einen Blick

| Datei | Inhalt |
|---|---|
| `templates/base.html` | Basis-Template mit Nav, Main, Footer, Flash-Messages |
| `templates/includes/bottom_nav.html` | Mobile Bottom-Navigation |
| `templates/includes/nav.html` | Desktop Top-Navigation |
| `accounts/templates/accounts/onboarding.html` | 3-Schritt Onboarding nach Registrierung |
| `toern/templates/crew/crew_overview.html` | Post-Login Dashboard mit Hero-Card |
| `toern/templates/crew/crew_dashboard.html` | 4-Tab Crew-Ansicht |
| `toern/templates/skipper/skipper_dashboard.html` | 4-Tab Skipper-Ansicht mit Drag&Drop |
| `utils/packliste.py` | Basis-Packlisten-Daten (BASIS_PACKLISTE, BOOT_STANDARD_LISTE etc.) |
| `static/css/src/input.css` | Tailwind/DaisyUI Eingabe + Custom Theme |
| `static/css/src/output.css` | Gebautes CSS (ins Git committen!) |
