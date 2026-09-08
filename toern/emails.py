import os

from django.core.mail import EmailMessage, EmailMultiAlternatives
from django.conf import settings
from django.utils.html import escape


def _send(subject, body, recipient):
    reply_to = [settings.REPLY_TO_EMAIL] if settings.REPLY_TO_EMAIL else []
    EmailMessage(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
        reply_to=reply_to,
    ).send(fail_silently=True)


def mail_zuteilung_fixiert(teilnahme, request):
    toern = teilnahme.toern
    user = teilnahme.user
    boot = teilnahme.boot
    kabine = teilnahme.kabine

    dashboard_url = request.build_absolute_uri(f"/toern/{toern.id}/crew/")
    boot_info = f"Boot: {boot.name}" if boot else "Boot: noch nicht zugewiesen"
    kabine_zeile = f"Kabine: {kabine.name}\n" if kabine else ""

    body = (
        f"Hallo {user.first_name},\n\n"
        f'die Zuteilung fuer den Toern "{toern.titel}" ist abgeschlossen!\n\n'
        f"{boot_info}\n"
        f"{kabine_zeile}"
        f"\nDu kannst ab sofort dein Crew-Dashboard aufrufen:\n{dashboard_url}\n\n"
        "Wir freuen uns auf deinen Toern!\n\n"
        "Bis bald an Bord,\n"
        "Das Meer erleben Team"
    )

    _send(
        subject=f'Deine Bootszuteilung fuer "{toern.titel}" steht fest!',
        body=body,
        recipient=user.email,
    )


def mail_teilnahme_bestaetigt(teilnahme, request):
    toern = teilnahme.toern
    user = teilnahme.user
    dashboard_url = request.build_absolute_uri(f"/toern/{toern.id}/crew/")
    # Toern-Datenformular (enthaelt auch Essgewohnheiten/Unvertraeglichkeiten) — nicht das Account-Profil
    daten_url = request.build_absolute_uri(f"/toern/{toern.id}/daten/")

    body = (
        f"Hallo {user.first_name},\n\n"
        f'deine Teilnahme am Toern \"{toern.titel}\" wurde bestaetigt.\n\n'
        f"Dein Crew-Dashboard:\n{dashboard_url}\n\n"
        "---\n"
        "Damit der Skipper alle noetigen Daten fuer die Crewliste hat, stelle bitte sicher,\n"
        "dass deine Toern-Daten vollstaendig ausgefuellt sind (Vorname, Nachname, Geburtsdatum,\n"
        "Geburtsort, Geburtsland, Nationalitaet, Ausweis-/Passnummer, Adresse, Telefon,\n"
        "Essgewohnheiten und Unvertraeglichkeiten).\n\n"
        f"Jetzt Daten vervollstaendigen:\n{daten_url}\n"
        "---\n\n"
        "Bis bald an Bord,\n"
        "Das Meer erleben Team"
    )

    _send(
        subject=f"Teilnahme bestaetigt - {toern.titel}",
        body=body,
        recipient=user.email,
    )


def mail_crew_daten_erinnerung(user, toern, fehlende_felder, request):
    # Toern-Datenformular (enthaelt auch Essgewohnheiten/Unvertraeglichkeiten) — nicht das Account-Profil
    daten_url = request.build_absolute_uri(f"/toern/{toern.id}/daten/")
    fehlend_str = "\n".join(f"  - {f}" for f in fehlende_felder)

    body = (
        f"Hallo {user.first_name or user.email},\n\n"
        f'du bist fuer den Toern \"{toern.titel}\" angemeldet.\n\n'
        "Fuer die Crewliste fehlen noch folgende Angaben:\n\n"
        f"{fehlend_str}\n\n"
        f"Bitte vervollstaendige deine Daten jetzt:\n{daten_url}\n\n"
        "Das dauert nur wenige Minuten!\n\n"
        "Viele Gruesse,\n"
        "Das Meer erleben Team"
    )

    _send(
        subject=f"Bitte vervollstaendige deine Crewdaten - {toern.titel}",
        body=body,
        recipient=user.email,
    )


def mail_teilnahme_abgesagt(teilnahme, request):
    from toern.models import Teilnahme as _Teilnahme
    toern = teilnahme.toern
    user = teilnahme.user
    anbieter = toern.anbieter

    body_info = (
        f"{user.first_name} {user.last_name} hat die Teilnahme am Toern \"{toern.titel}\" abgesagt.\n\n"
        f"Datum: {toern.startdatum.strftime('%d.%m.%Y')} – {toern.enddatum.strftime('%d.%m.%Y')}\n\n"
        "Viele Gruesse,\n"
        "Das Meer erleben Team"
    )

    _send(
        subject=f"Absage: {user.first_name} {user.last_name} – {toern.titel}",
        body=f"Hallo {anbieter.first_name},\n\n" + body_info,
        recipient=anbieter.email,
    )

    skipper_qs = _Teilnahme.objects.filter(
        toern=toern,
        rolle__in=("skipper", "coskipper"),
    ).exclude(user=anbieter).select_related("user")

    for s in skipper_qs:
        _send(
            subject=f"Absage: {user.first_name} {user.last_name} – {toern.titel}",
            body=f"Hallo {s.user.first_name},\n\n" + body_info,
            recipient=s.user.email,
        )

    body_user = (
        f"Hallo {user.first_name},\n\n"
        f"deine Absage fuer den Toern \"{toern.titel}\" wurde bestaetigt.\n\n"
        "Bei Fragen antworte einfach auf diese Mail.\n\n"
        "Viele Gruesse,\n"
        "Das Meer erleben Team"
    )
    _send(
        subject=f"Deine Absage – {toern.titel}",
        body=body_user,
        recipient=user.email,
    )


def mail_toern_abgeschlossen(toern, teilnahmen, request):
    dashboard_base = request.build_absolute_uri(f"/toern/{toern.id}/crew/")

    for t in teilnahmen:
        user = t.user
        boot = t.boot

        meilen = t.individuelle_meilen or (boot.skipper_meilen if boot else None)
        meilen_zeile = f"Gesegelten Seemeilen: {meilen} sm\n" if meilen else ""

        foto_upload_zeile = f"Fotos hochladen: {toern.foto_upload_link}\n" if toern.foto_upload_link else ""
        foto_download_zeile = f"Fotos ansehen: {toern.foto_download_link}\n" if toern.foto_download_link else ""

        logbuch_zeile = ""
        if boot and boot.logbuch_pdf:
            logbuch_url = request.build_absolute_uri(boot.logbuch_pdf.url)
            logbuch_zeile = f"Logbuch-PDF: {logbuch_url}\n"

        extras = meilen_zeile + foto_upload_zeile + foto_download_zeile + logbuch_zeile

        body = (
            f"Hallo {user.first_name},\n\n"
            f'der Toern "{toern.titel}" ist offiziell abgeschlossen!\n\n'
            f"Revier: {toern.revier}\n"
            f"Zeitraum: {toern.startdatum.strftime('%d.%m.%Y')} – {toern.enddatum.strftime('%d.%m.%Y')}\n"
        )

        if extras:
            body += f"\n{extras}"

        body += (
            f"\nDein Crew-Dashboard:\n{dashboard_base}\n\n"
            "Vielen Dank fuer eine tolle Zeit an Bord!\n\n"
            "Bis zum naechsten Toern,\n"
            "Das Meer erleben Team"
        )

        _send(
            subject=f'Toern abgeschlossen: "{toern.titel}"',
            body=body,
            recipient=user.email,
        )


def mail_teilnahme_abgelehnt(teilnahme, request):
    toern = teilnahme.toern
    user = teilnahme.user

    body = (
        f"Hallo {user.first_name},\n\n"
        f'leider koennen wir deine Teilnahme am Toern "{toern.titel}" nicht bestaetigen.\n\n'
        "Bei Fragen antworte einfach auf diese Mail.\n\n"
        "Viele Gruesse,\n"
        "Das Meer erleben Team"
    )

    _send(
        subject=f"Teilnahme - {toern.titel}",
        body=body,
        recipient=user.email,
    )


def _termin_zeile(rundmail):
    """Formatierte Datums-/Zeitzeile eines Termins, z.B. '12.09.2026 um 19:00 – 20:30 Uhr'."""
    if not rundmail.termin_start:
        return ""
    from django.utils import timezone
    start = timezone.localtime(rundmail.termin_start)
    zeile = start.strftime("%d.%m.%Y um %H:%M")
    if rundmail.termin_ende:
        ende = timezone.localtime(rundmail.termin_ende)
        if ende.date() == start.date():
            zeile += ende.strftime(" – %H:%M Uhr")
        else:
            zeile += ende.strftime(" Uhr bis %d.%m.%Y %H:%M Uhr")
    else:
        zeile += " Uhr"
    return zeile


def _termin_text(rundmail):
    """Termin-Block für den Plaintext-Teil der Mail (ohne technische Hinweise)."""
    zeile = _termin_zeile(rundmail)
    if not zeile:
        return ""
    block = f"\n\nTermin: {zeile}"
    ort = rundmail.termin_ort or ("Online" if rundmail.meeting_link else "")
    if ort:
        block += f"\nOrt: {ort}"
    return block


_LOGO_CACHE = None


def _logo_bytes():
    """Logo einmalig einlesen und cachen (leerer Bytes-String, falls nicht vorhanden)."""
    global _LOGO_CACHE
    if _LOGO_CACHE is None:
        pfad = os.path.join(settings.BASE_DIR, "static", "medien", "Logo_Meer_erleben.png")
        try:
            with open(pfad, "rb") as f:
                _LOGO_CACHE = f.read()
        except OSError:
            _LOGO_CACHE = b""
    return _LOGO_CACHE


def _rundmail_html(body_text, rundmail, logo_cid=None):
    """Baut die HTML-Variante der Rundmail im Corporate-Design (Logo, Farben)."""
    primary = "#0f2942"   # dunkles Blau
    teal = "#0D9488"      # Secondary

    text_html = escape(body_text).replace("\n", "<br>")

    logo_html = ""
    if logo_cid:
        logo_html = (
            f'<img src="cid:{logo_cid}" alt="Meer erleben" '
            f'width="150" style="display:block;margin:0 auto;max-width:150px;height:auto;">'
        )

    info_blocks = ""
    if rundmail.meeting_link:
        link = escape(rundmail.meeting_link)
        info_blocks += (
            f'<tr><td style="padding:6px 0;">'
            f'<a href="{link}" style="display:inline-block;background:{teal};color:#ffffff;'
            f'text-decoration:none;padding:11px 22px;border-radius:8px;font-weight:600;font-size:15px;">'
            f'💻 Zum digitalen Treffen</a></td></tr>'
        )
    termin_zeile = _termin_zeile(rundmail)
    if termin_zeile:
        ort = rundmail.termin_ort or ("Online" if rundmail.meeting_link else "")
        ort_html = (f'<div style="color:#4b5563;font-size:14px;margin-top:2px;">📍 {escape(ort)}</div>'
                    if ort else "")
        info_blocks += (
            f'<tr><td style="padding:10px 0 0;">'
            f'<div style="background:#f1f5f9;border-radius:10px;padding:14px 16px;">'
            f'<div style="color:{primary};font-weight:600;font-size:15px;">📅 {escape(termin_zeile)}</div>'
            f'{ort_html}'
            f'<div style="color:#94a3b8;font-size:12px;margin-top:6px;">Termin liegt dieser Mail als Kalenderdatei bei.</div>'
            f'</div></td></tr>'
        )

    return f"""\
<!DOCTYPE html>
<html lang="de">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"></head>
<body style="margin:0;padding:0;background:#eef2f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#eef2f5;padding:24px 12px;">
    <tr><td align="center">
      <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,0.08);border:1px solid #e5e7eb;">
        <tr><td style="background:#ffffff;padding:26px 24px 20px;text-align:center;">{logo_html}</td></tr>
        <tr><td style="height:3px;background:{teal};line-height:3px;font-size:0;">&nbsp;</td></tr>
        <tr><td style="padding:28px 28px 8px;color:#1f2937;font-size:16px;line-height:1.6;">
          {text_html}
        </td></tr>
        <tr><td style="padding:4px 28px 24px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{info_blocks}</table>
        </td></tr>
        <tr><td style="padding:16px 28px;background:#f8fafc;border-top:1px solid #e5e7eb;text-align:center;color:#94a3b8;font-size:12px;">
          Meer erleben · Diese Mail wurde über den Segelmanager verschickt.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def mail_rundmail(rundmail, teilnahme, ics_text=None, anhang_bytes=None, anhang_name=None):
    """Versendet eine personalisierte Rundmail an ein Crew-Mitglied.

    - Bausteine ({{vorname}} etc.) werden pro Empfänger gerendert.
    - Reply-To zeigt auf den Skipper, damit Antworten direkt bei ihm landen.
    - HTML-Variante im Corporate-Design mit Logo; Plaintext als Fallback.
    - Optionaler .ics-Termin und eine Datei werden als Anhang mitgeschickt.
    """
    from .rundmail_utils import render_platzhalter

    absender = rundmail.absender
    user = teilnahme.user

    betreff = render_platzhalter(rundmail.betreff, teilnahme, absender)
    body = render_platzhalter(rundmail.text, teilnahme, absender)

    # Plaintext-Variante (Fallback + Zustellbarkeit)
    plain = body
    if rundmail.meeting_link:
        plain += f"\n\nZum digitalen Treffen:\n{rundmail.meeting_link}"
    plain += _termin_text(rundmail)

    if absender and absender.email:
        reply_to = [absender.email]
    elif settings.REPLY_TO_EMAIL:
        reply_to = [settings.REPLY_TO_EMAIL]
    else:
        reply_to = []

    mail = EmailMultiAlternatives(
        subject=betreff,
        body=plain,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
        reply_to=reply_to,
    )

    # Logo als Inline-Bild (CID) einbetten, falls vorhanden
    logo_cid = None
    logo = _logo_bytes()
    if logo:
        try:
            from anymail.message import attach_inline_image
            logo_cid = attach_inline_image(mail, logo, subtype="png")
        except Exception:
            logo_cid = None

    mail.attach_alternative(_rundmail_html(body, rundmail, logo_cid=logo_cid), "text/html")

    if ics_text:
        mail.attach("Termin.ics", ics_text, "text/calendar")
    if anhang_bytes and anhang_name:
        mail.attach(anhang_name, anhang_bytes)

    mail.send(fail_silently=True)
