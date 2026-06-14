from django.core.management.base import BaseCommand
from django.core.mail import EmailMessage
from django.conf import settings
from django.utils import timezone

from accounts.models import User
from toern.models import Teilnahme


FELDER = [
    ("first_name", "Vorname"),
    ("last_name", "Nachname"),
    ("geburtsdatum", "Geburtsdatum"),
    ("nationalitaet", "Nationalitaet"),
    ("passnummer", "Ausweis-/Passnummer"),
    ("strasse", "Strasse"),
    ("plz", "Postleitzahl"),
    ("ort", "Wohnort"),
    ("telefonnummer", "Telefonnummer"),
    ("profilbild", "Profilbild"),
]


def fehlende_felder(user):
    return [label for attr, label in FELDER if not getattr(user, attr)]


def profil_prozent(user):
    gefuellt = sum(1 for attr, _ in FELDER if getattr(user, attr))
    return int((gefuellt / len(FELDER)) * 100)


class Command(BaseCommand):
    help = "Sendet Erinnerungsmails an User mit unvollstaendigem Profil und aktiver Toern-Anmeldung"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Keine Mails senden, nur ausgeben wer benoachrichtigt wuerden",
        )
        parser.add_argument(
            "--schwellwert",
            type=int,
            default=80,
            help="Profil-Vollstaendigkeit unterhalb derer erinnert wird (Standard: 80)",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        schwellwert = options["schwellwert"]
        jetzt = timezone.now()

        # User mit zukuenftiger Toern-Teilnahme und unvollstaendigem Profil
        user_ids = Teilnahme.objects.filter(
            toern__startdatum__gt=jetzt,
            status__in=["angemeldet", "bestaetigt"],
        ).values_list("user_id", flat=True).distinct()

        users = User.objects.filter(id__in=user_ids, email_verified=True)

        versandt = 0
        uebersprungen = 0

        for user in users:
            prozent = profil_prozent(user)
            if prozent >= schwellwert:
                uebersprungen += 1
                continue

            fehlend = fehlende_felder(user)
            fehlend_str = "\n".join(f"  - {f}" for f in fehlend)

            self.stdout.write(
                f"{user.email} ({prozent}%) — fehlt: {', '.join(fehlend)}"
            )

            if not dry_run:
                self._send_reminder(user, fehlend_str, prozent)

            versandt += 1

        modus = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{modus}{versandt} Erinnerung(en) {'wuerden gesendet' if dry_run else 'gesendet'}, "
            f"{uebersprungen} uebersprungen (Profil vollstaendig genug)."
        ))

    def _send_reminder(self, user, fehlend_str, prozent):
        reply_to = [settings.REPLY_TO_EMAIL] if settings.REPLY_TO_EMAIL else []
        profil_url = "https://segelmanager.undmeererleben.de/accounts/account-edit/"

        body = (
            f"Hallo {user.first_name or user.email},\n\n"
            f"du hast dich fuer einen Toern angemeldet, aber dein Profil ist erst zu {prozent}% ausgefuellt.\n\n"
            "Damit der Skipper alle noetigen Daten hat, vervollstaendige bitte noch:\n\n"
            f"{fehlend_str}\n\n"
            f"Hier geht es direkt zu deinem Profil:\n{profil_url}\n\n"
            "Das dauert nur wenige Minuten!\n\n"
            "Viele Gruesse,\n"
            "Das Meer erleben Team"
        )

        EmailMessage(
            subject="Bitte vervollstaendige dein Profil fuer den Toern",
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
            reply_to=reply_to,
        ).send(fail_silently=True)
