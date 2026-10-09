import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.templatetags.static import static

logger = logging.getLogger(__name__)

LOGO_PFAD = "medien/Logo_Meer_erleben.png"


def logo_url(request):
    """Öffentliche Logo-URL für Mails. Brevo kann keine Inline-/CID-Bilder,
    und WhiteNoise liefert /static/ auch ohne Login aus."""
    return request.build_absolute_uri(static(LOGO_PFAD)) if request else None


def render_mail_html(request, template="emails/standard.html", **context):
    """HTML-Teil einer Mail im gemeinsamen Meer-erleben-Design."""
    return render_to_string(template, {"logo_url": logo_url(request), **context})


def _send(subject, body, recipient, html=None):
    """Plaintext + HTML-Alternative an eine Adresse.

    Ein Fehler bei Brevo bricht den auslösenden Vorgang (Bestätigen,
    Abschließen …) nicht ab, landet aber im Log statt still zu verschwinden.
    """
    reply_to = [settings.REPLY_TO_EMAIL] if settings.REPLY_TO_EMAIL else []
    mail = EmailMultiAlternatives(
        subject=subject,
        body=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[recipient],
        reply_to=reply_to,
    )
    if html:
        mail.attach_alternative(html, "text/html")
    try:
        mail.send(fail_silently=False)
    except Exception:
        logger.exception("Mailversand fehlgeschlagen: %r an %s", subject, recipient)


def _zeitraum(toern):
    return f"{toern.startdatum.strftime('%d.%m.%Y')} – {toern.enddatum.strftime('%d.%m.%Y')}"


def mail_zuteilung_fixiert(teilnahme, request):
    toern = teilnahme.toern
    user = teilnahme.user
    boot = teilnahme.boot
    kabine = teilnahme.kabine

    dashboard_url = request.build_absolute_uri(f"/toern/{toern.id}/crew/")
    boot_name = boot.name if boot else "noch nicht zugewiesen"
    kabine_zeile = f"Kabine: {kabine.name}\n" if kabine else ""

    body = (
        f"Hallo {user.first_name},\n\n"
        f'die Zuteilung für den Törn "{toern.titel}" ist abgeschlossen!\n\n'
        f"Boot: {boot_name}\n"
        f"{kabine_zeile}"
        f"\nDu kannst ab sofort dein Crew-Dashboard aufrufen:\n{dashboard_url}\n\n"
        "Wir freuen uns auf deinen Törn!\n\n"
        "Bis bald an Bord,\n"
        "Das Meer erleben Team"
    )
    infozeilen = [("Boot", boot_name)]
    if kabine:
        infozeilen.append(("Kabine", kabine.name))
    html = render_mail_html(
        request,
        anrede=f"Hallo {user.first_name},",
        absaetze=[f"die Zuteilung für den Törn „{toern.titel}“ ist abgeschlossen!"],
        infozeilen=infozeilen,
        buttons=[{"url": dashboard_url, "label": "Zum Crew-Dashboard"}],
        nachsatz=["Wir freuen uns auf deinen Törn!"],
        gruss="Bis bald an Bord,",
    )

    _send(
        subject=f'Deine Bootszuteilung für "{toern.titel}" steht fest!',
        body=body,
        recipient=user.email,
        html=html,
    )


def mail_teilnahme_bestaetigt(teilnahme, request):
    toern = teilnahme.toern
    user = teilnahme.user
    dashboard_url = request.build_absolute_uri(f"/toern/{toern.id}/crew/")
    # Törn-Datenformular (enthält auch Essgewohnheiten/Unverträglichkeiten) — nicht das Account-Profil
    daten_url = request.build_absolute_uri(f"/toern/{toern.id}/daten/")
    daten_text = (
        "Damit der Skipper alle nötigen Daten für die Crewliste hat, stelle bitte sicher, "
        "dass deine Törn-Daten vollständig ausgefüllt sind (Vorname, Nachname, Geburtsdatum, "
        "Geburtsort, Geburtsland, Nationalität, Ausweis-/Passnummer, Adresse, Telefon, "
        "Essgewohnheiten und Unverträglichkeiten)."
    )

    body = (
        f"Hallo {user.first_name},\n\n"
        f'deine Teilnahme am Törn "{toern.titel}" wurde bestätigt.\n\n'
        f"Dein Crew-Dashboard:\n{dashboard_url}\n\n"
        "---\n"
        f"{daten_text}\n\n"
        f"Jetzt Daten vervollständigen:\n{daten_url}\n"
        "---\n\n"
        "Bis bald an Bord,\n"
        "Das Meer erleben Team"
    )
    html = render_mail_html(
        request,
        anrede=f"Hallo {user.first_name},",
        absaetze=[f"deine Teilnahme am Törn „{toern.titel}“ wurde bestätigt.", daten_text],
        buttons=[
            {"url": daten_url, "label": "Jetzt Daten vervollständigen"},
            {"url": dashboard_url, "label": "Zum Crew-Dashboard", "zweitrangig": True},
        ],
        gruss="Bis bald an Bord,",
    )

    _send(
        subject=f"Teilnahme bestätigt – {toern.titel}",
        body=body,
        recipient=user.email,
        html=html,
    )


def mail_crew_daten_erinnerung(user, toern, fehlende_felder, request):
    # Törn-Datenformular (enthält auch Essgewohnheiten/Unverträglichkeiten) — nicht das Account-Profil
    daten_url = request.build_absolute_uri(f"/toern/{toern.id}/daten/")
    fehlend_str = "\n".join(f"  - {f}" for f in fehlende_felder)
    vorname = user.first_name or user.email

    body = (
        f"Hallo {vorname},\n\n"
        f'du bist für den Törn "{toern.titel}" angemeldet.\n\n'
        "Für die Crewliste fehlen noch folgende Angaben:\n\n"
        f"{fehlend_str}\n\n"
        f"Bitte vervollständige deine Daten jetzt:\n{daten_url}\n\n"
        "Das dauert nur wenige Minuten!\n\n"
        "Viele Grüße,\n"
        "Das Meer erleben Team"
    )
    html = render_mail_html(
        request,
        anrede=f"Hallo {vorname},",
        absaetze=[f"du bist für den Törn „{toern.titel}“ angemeldet."],
        liste_titel="Für die Crewliste fehlen noch:",
        liste=list(fehlende_felder),
        buttons=[{"url": daten_url, "label": "Daten vervollständigen"}],
        nachsatz=["Das dauert nur wenige Minuten!"],
        gruss="Viele Grüße,",
    )

    _send(
        subject=f"Bitte vervollständige deine Crewdaten – {toern.titel}",
        body=body,
        recipient=user.email,
        html=html,
    )


def mail_teilnahme_abgesagt(teilnahme, request):
    from toern.models import Teilnahme as _Teilnahme
    toern = teilnahme.toern
    user = teilnahme.user
    anbieter = toern.anbieter
    name = f"{user.first_name} {user.last_name}"

    info_text = f'{name} hat die Teilnahme am Törn "{toern.titel}" abgesagt.'
    body_info = (
        f"{info_text}\n\n"
        f"Datum: {_zeitraum(toern)}\n\n"
        "Viele Grüße,\n"
        "Das Meer erleben Team"
    )

    def info_html(vorname):
        return render_mail_html(
            request,
            anrede=f"Hallo {vorname},",
            absaetze=[f"{name} hat die Teilnahme am Törn „{toern.titel}“ abgesagt."],
            infozeilen=[("Törn", toern.titel), ("Datum", _zeitraum(toern))],
            gruss="Viele Grüße,",
        )

    _send(
        subject=f"Absage: {name} – {toern.titel}",
        body=f"Hallo {anbieter.first_name},\n\n" + body_info,
        recipient=anbieter.email,
        html=info_html(anbieter.first_name),
    )

    skipper_qs = _Teilnahme.objects.filter(
        toern=toern,
        rolle__in=("skipper", "coskipper"),
    ).exclude(user=anbieter).select_related("user")

    for s in skipper_qs:
        _send(
            subject=f"Absage: {name} – {toern.titel}",
            body=f"Hallo {s.user.first_name},\n\n" + body_info,
            recipient=s.user.email,
            html=info_html(s.user.first_name),
        )

    body_user = (
        f"Hallo {user.first_name},\n\n"
        f'deine Absage für den Törn "{toern.titel}" wurde bestätigt.\n\n'
        "Bei Fragen antworte einfach auf diese Mail.\n\n"
        "Viele Grüße,\n"
        "Das Meer erleben Team"
    )
    _send(
        subject=f"Deine Absage – {toern.titel}",
        body=body_user,
        recipient=user.email,
        html=render_mail_html(
            request,
            anrede=f"Hallo {user.first_name},",
            absaetze=[
                f"deine Absage für den Törn „{toern.titel}“ wurde bestätigt.",
                "Bei Fragen antworte einfach auf diese Mail.",
            ],
            gruss="Viele Grüße,",
        ),
    )


def mail_toern_abgeschlossen(toern, teilnahmen, request):
    dashboard_base = request.build_absolute_uri(f"/toern/{toern.id}/crew/")
    kasse_url = request.build_absolute_uri(f"/toern/{toern.id}/boot/?tab=kasse")

    for t in teilnahmen:
        user = t.user
        boot = t.boot

        meilen = t.individuelle_meilen or (boot.skipper_meilen if boot else None)
        meilen_zeile = f"Gesegelte Seemeilen: {meilen} sm\n" if meilen else ""

        foto_upload_zeile = f"Fotos hochladen: {toern.foto_upload_link}\n" if toern.foto_upload_link else ""
        foto_download_zeile = f"Fotos ansehen: {toern.foto_download_link}\n" if toern.foto_download_link else ""

        logbuch_url = None
        logbuch_zeile = ""
        if boot and boot.logbuch_pdf:
            logbuch_url = request.build_absolute_uri(boot.logbuch_pdf.url)
            logbuch_zeile = f"Logbuch-PDF: {logbuch_url}\n"

        extras = meilen_zeile + foto_upload_zeile + foto_download_zeile + logbuch_zeile

        body = (
            f"Hallo {user.first_name},\n\n"
            f'der Törn "{toern.titel}" ist offiziell abgeschlossen!\n\n'
            f"Revier: {toern.revier}\n"
            f"Zeitraum: {_zeitraum(toern)}\n"
        )
        if extras:
            body += f"\n{extras}"
        if boot:
            body += f"\nOffene Beträge in der Bootskasse:\n{kasse_url}\n"
        body += (
            f"\nDein Crew-Dashboard:\n{dashboard_base}\n\n"
            "Vielen Dank für eine tolle Zeit an Bord!\n\n"
            "Bis zum nächsten Törn,\n"
            "Das Meer erleben Team"
        )

        buttons = []
        if toern.foto_upload_link:
            buttons.append({"url": toern.foto_upload_link, "label": "📤 Deine Fotos hochladen"})
        if toern.foto_download_link:
            buttons.append({"url": toern.foto_download_link, "label": "🖼️ Alle Fotos ansehen", "zweitrangig": True})
        if logbuch_url:
            buttons.append({"url": logbuch_url, "label": "📖 Logbuch (PDF)", "zweitrangig": True})
        if boot:
            buttons.append({"url": kasse_url, "label": "💶 Zur Bootskasse", "zweitrangig": True})
        buttons.append({"url": dashboard_base, "label": "Zum Crew-Dashboard", "zweitrangig": True})

        html = render_mail_html(
            request,
            anrede=f"Hallo {user.first_name},",
            absaetze=[f"der Törn „{toern.titel}“ ist offiziell abgeschlossen! ⚓"],
            highlight={"wert": f"{meilen} sm", "label": "Deine gesegelten Seemeilen"} if meilen else None,
            infozeilen=[("Revier", toern.revier), ("Zeitraum", _zeitraum(toern))]
                       + ([("Boot", boot.name)] if boot else []),
            buttons=buttons,
            nachsatz=["Vielen Dank für eine tolle Zeit an Bord!"],
            gruss="Bis zum nächsten Törn,",
        )

        _send(
            subject=f'Törn abgeschlossen: "{toern.titel}"',
            body=body,
            recipient=user.email,
            html=html,
        )


def mail_teilnahme_abgelehnt(teilnahme, request):
    toern = teilnahme.toern
    user = teilnahme.user

    body = (
        f"Hallo {user.first_name},\n\n"
        f'leider können wir deine Teilnahme am Törn "{toern.titel}" nicht bestätigen.\n\n'
        "Bei Fragen antworte einfach auf diese Mail.\n\n"
        "Viele Grüße,\n"
        "Das Meer erleben Team"
    )

    _send(
        subject=f"Teilnahme – {toern.titel}",
        body=body,
        recipient=user.email,
        html=render_mail_html(
            request,
            anrede=f"Hallo {user.first_name},",
            absaetze=[
                f"leider können wir deine Teilnahme am Törn „{toern.titel}“ nicht bestätigen.",
                "Bei Fragen antworte einfach auf diese Mail.",
            ],
            gruss="Viele Grüße,",
        ),
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


def _rundmail_html(body_text, rundmail, logo_url=None):
    """HTML-Variante der Rundmail im gemeinsamen Mail-Layout
    (templates/emails/layout.html). Logo per öffentlicher URL — Brevo
    unterstützt keine Inline-/CID-Anhänge."""
    return render_to_string("emails/rundmail.html", {
        "logo_url": logo_url,
        "text": body_text,
        "meeting_link": rundmail.meeting_link,
        "termin_zeile": _termin_zeile(rundmail),
        "termin_ort": rundmail.termin_ort or ("Online" if rundmail.meeting_link else ""),
    })


def mail_rundmail(rundmail, teilnahme, ics_text=None, anhang_bytes=None,
                  anhang_name=None, logo_url=None, fail_silently=False):
    """Versendet eine personalisierte Rundmail an ein Crew-Mitglied.

    - Bausteine ({{vorname}} etc.) werden pro Empfänger gerendert.
    - Reply-To zeigt auf den Skipper, damit Antworten direkt bei ihm landen.
    - HTML-Variante im Corporate-Design mit Logo (per URL); Plaintext als Fallback.
    - Optionaler .ics-Termin und eine Datei werden als Anhang mitgeschickt.

    Wirft standardmäßig bei Versandfehlern (fail_silently=False), damit der
    Aufrufer echte Fehler melden kann statt sie still zu schlucken.
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
    mail.attach_alternative(_rundmail_html(body, rundmail, logo_url=logo_url), "text/html")

    if ics_text:
        mail.attach("Termin.ics", ics_text, "text/calendar")
    if anhang_bytes and anhang_name:
        mail.attach(anhang_name, anhang_bytes)

    mail.send(fail_silently=fail_silently)
