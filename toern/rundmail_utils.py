"""Hilfsfunktionen fuer Skipper-Rundmails: Bausteine (Platzhalter) + iCalendar (.ics)."""
import uuid
from datetime import timedelta, timezone as dt_timezone

from django.utils import timezone


def render_platzhalter(text, teilnahme, absender=None):
    """Ersetzt Bausteine im Text durch die persoenlichen Daten der Teilnahme.

    Unterstuetzte Bausteine (case-insensitiv):
      {{vorname}} {{nachname}} {{name}} {{boot}} {{kabine}} {{toern}} {{skipper}}
    Leere Werte werden durch einen leeren String ersetzt, damit keine
    "{{...}}"-Reste in der Mail landen.
    """
    if not text:
        return ""

    user = teilnahme.user
    boot = teilnahme.boot
    kabine = teilnahme.kabine
    toern = teilnahme.toern

    vorname = (user.first_name or "").strip()
    nachname = (user.last_name or "").strip()
    voller_name = f"{vorname} {nachname}".strip() or vorname or (user.email or "")

    skipper_name = ""
    if absender is not None:
        skipper_name = (absender.first_name or "").strip() or (absender.email or "")

    werte = {
        "vorname": vorname,
        "nachname": nachname,
        "name": voller_name,
        "boot": boot.name if boot else "",
        "kabine": kabine.name if kabine else "",
        "toern": toern.titel if toern else "",
        "skipper": skipper_name,
    }

    ergebnis = text
    for schluessel, wert in werte.items():
        # Zwei Schreibweisen erlauben: {{vorname}} und {{ vorname }}
        ergebnis = ergebnis.replace("{{" + schluessel + "}}", wert)
        ergebnis = ergebnis.replace("{{ " + schluessel + " }}", wert)
    return ergebnis


def _ics_escape(wert):
    """Escaping gemaess RFC 5545 (Komma, Semikolon, Backslash, Zeilenumbruch)."""
    if not wert:
        return ""
    return (
        str(wert)
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _ics_dt(dt):
    """Aware datetime -> UTC-Basiszeit im iCalendar-Format (YYYYMMDDTHHMMSSZ)."""
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(rundmail, organisator_email=None):
    """Erzeugt den iCalendar-Text (VEVENT) fuer eine Rundmail mit Termin.

    Enthaelt Start/Ende, Titel, Ort (bzw. 'Online'), den Meeting-Link in
    Beschreibung + URL sowie eine Erinnerung 1 Stunde vorher (VALARM).
    Gibt None zurueck, wenn kein Termin gesetzt ist.
    """
    if not rundmail.termin_start:
        return None

    start = rundmail.termin_start
    ende = rundmail.termin_ende or (start + timedelta(hours=1))

    titel = rundmail.termin_titel or rundmail.betreff or "Vortreffen"
    ort = rundmail.termin_ort or ("Online" if rundmail.meeting_link else "")

    beschreibung_teile = []
    if rundmail.meeting_link:
        beschreibung_teile.append(f"Meeting-Link: {rundmail.meeting_link}")
    beschreibung = "\n".join(beschreibung_teile)

    uid = f"rundmail-{rundmail.pk or uuid.uuid4().hex}@undmeererleben.de"

    zeilen = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Meer erleben//Segelmanager//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_ics_dt(timezone.now())}",
        f"DTSTART:{_ics_dt(start)}",
        f"DTEND:{_ics_dt(ende)}",
        f"SUMMARY:{_ics_escape(titel)}",
    ]
    if beschreibung:
        zeilen.append(f"DESCRIPTION:{_ics_escape(beschreibung)}")
    if ort:
        zeilen.append(f"LOCATION:{_ics_escape(ort)}")
    if rundmail.meeting_link:
        zeilen.append(f"URL:{_ics_escape(rundmail.meeting_link)}")
    if organisator_email:
        zeilen.append(f"ORGANIZER:mailto:{organisator_email}")
    zeilen += [
        "BEGIN:VALARM",
        "TRIGGER:-PT1H",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{_ics_escape(titel)}",
        "END:VALARM",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    # RFC 5545 verlangt CRLF als Zeilentrenner.
    return "\r\n".join(zeilen) + "\r\n"
