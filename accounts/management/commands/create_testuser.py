from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()


class Command(BaseCommand):
    help = "Erstellt Testuser"

    def add_arguments(self, parser):
        parser.add_argument("anzahl", type=int, help="Anzahl der Testuser")

    def handle(self, *args, **kwargs):
        anzahl = kwargs["anzahl"]

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

            user = User.objects.create_user(
                username=email,  # wichtig wegen REQUIRED_FIELDS
                email=email,
                password="Test",
                first_name=vorname,
                last_name=nachname,
                geschlecht=geschlecht,
            )

            self.stdout.write(self.style.SUCCESS(f"Erstellt: {email}"))