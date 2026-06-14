from django.core.management.base import BaseCommand
from django.conf import settings
from django.utils import timezone

from accounts.models import User
from toern.models import Teilnahme
from toern.crew_utils import fehlende_crew_felder
from toern.emails import mail_crew_daten_erinnerung


class FakeRequest:
    def build_absolute_uri(self, path):
        base = getattr(settings, "SITE_URL", "https://segelmanager.undmeererleben.de")
        return f"{base.rstrip('/')}{path}"


class Command(BaseCommand):
    help = "Sendet Erinnerungsmails an User mit unvollstaendigen Crewdaten und aktiver Toern-Anmeldung"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Keine Mails senden, nur ausgeben wer benachrichtigt wuerden",
        )
        parser.add_argument(
            "--toern-id",
            type=int,
            default=None,
            help="Nur Teilnehmer eines bestimmten Toerns pruefen",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        toern_id = options.get("toern_id")
        jetzt = timezone.now()

        qs = Teilnahme.objects.filter(
            toern__startdatum__gt=jetzt,
            status__in=["angemeldet", "bestaetigt"],
        )
        if toern_id:
            qs = qs.filter(toern_id=toern_id)

        user_ids = qs.values_list("user_id", flat=True).distinct()
        users = User.objects.filter(id__in=user_ids, email_verified=True)

        fake_request = FakeRequest()
        versandt = 0
        uebersprungen = 0

        for user in users:
            fehlend = fehlende_crew_felder(user)
            if not fehlend:
                uebersprungen += 1
                continue

            self.stdout.write(
                f"{user.email} — fehlt: {', '.join(fehlend)}"
            )

            if not dry_run:
                # Find first relevant toern for this user
                teilnahme = qs.filter(user=user).select_related("toern").first()
                if teilnahme:
                    mail_crew_daten_erinnerung(user, teilnahme.toern, fehlend, fake_request)

            versandt += 1

        modus = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"\n{modus}{versandt} Erinnerung(en) {'wuerden gesendet' if dry_run else 'gesendet'}, "
            f"{uebersprungen} uebersprungen (alle Crewdaten vollstaendig)."
        ))
