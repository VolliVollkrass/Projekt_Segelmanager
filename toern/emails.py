from django.core.mail import EmailMessage
from django.conf import settings


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
    profil_url = request.build_absolute_uri("/accounts/account-edit/")

    body = (
        f"Hallo {user.first_name},\n\n"
        f'deine Teilnahme am Toern \"{toern.titel}\" wurde bestaetigt.\n\n'
        f"Dein Crew-Dashboard:\n{dashboard_url}\n\n"
        "---\n"
        "Damit der Skipper alle noetigen Daten fuer die Crewliste hat, stelle bitte sicher,\n"
        "dass dein Profil vollstaendig ausgefuellt ist (Vorname, Nachname, Geburtsdatum,\n"
        "Geburtsort, Geburtsland, Nationalitaet, Ausweis-/Passnummer, Adresse, Telefon).\n\n"
        f"Jetzt Profil vervollstaendigen:\n{profil_url}\n"
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
    profil_url = request.build_absolute_uri("/accounts/account-edit/")
    fehlend_str = "\n".join(f"  - {f}" for f in fehlende_felder)

    body = (
        f"Hallo {user.first_name or user.email},\n\n"
        f'du bist fuer den Toern \"{toern.titel}\" angemeldet.\n\n'
        "Fuer die Crewliste fehlen noch folgende Angaben in deinem Profil:\n\n"
        f"{fehlend_str}\n\n"
        f"Bitte vervollstaendige dein Profil jetzt:\n{profil_url}\n\n"
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

        meilen_zeile = ""
        if boot and boot.skipper_meilen:
            meilen_zeile = f"Gesegelten Seemeilen: {boot.skipper_meilen} sm\n"

        foto_upload_zeile = ""
        if boot and boot.foto_upload_link:
            foto_upload_zeile = f"Fotos hochladen: {boot.foto_upload_link}\n"

        foto_download_zeile = ""
        if boot and boot.foto_download_link:
            foto_download_zeile = f"Fotos ansehen: {boot.foto_download_link}\n"

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
