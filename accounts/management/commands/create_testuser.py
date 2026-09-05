import secrets

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Erstellt Testuser (nur bei DEBUG=True)"

    def add_arguments(self, parser):
        parser.add_argument("anzahl", type=int, help="Anzahl der Testuser")
        parser.add_argument(
            "--password",
            help="Passwort für alle Testuser. Ohne Angabe wird pro User ein "
                 "zufälliges Passwort erzeugt und ausgegeben.",
        )

    def handle(self, *args, **kwargs):
        # Testuser haben triviale Daten und dürfen niemals in Produktion landen.
        if not settings.DEBUG:
            raise CommandError("create_testuser ist nur bei DEBUG=True erlaubt.")

        anzahl = kwargs["anzahl"]
        festes_passwort = kwargs.get("password")

        for i in range(1, anzahl + 1):

            vorname = f"Tester {i}"

            # 👉 Wechsel zwischen Mustermann / Musterfrau
            if i % 2 == 0:
                nachname = "Musterfrau"
                geschlecht = "w"
            else:
                nachname = "Mustermann"
                geschlecht = "m"

            email = f"tester{i}@user.de"

            if User.objects.filter(email=email).exists():
                self.stdout.write(self.style.WARNING(f"{email} existiert bereits"))
                continue

            passwort = festes_passwort or secrets.token_urlsafe(12)

            user = User.objects.create_user(
                username=email,  # wichtig wegen REQUIRED_FIELDS
                email=email,
                password=passwort,
                first_name=vorname,
                last_name=nachname,
                geschlecht=geschlecht,
            )

            if festes_passwort:
                self.stdout.write(self.style.SUCCESS(f"Erstellt: {email}"))
            else:
                self.stdout.write(self.style.SUCCESS(f"Erstellt: {email}  (Passwort: {passwort})"))