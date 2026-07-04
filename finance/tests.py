"""Tests für die Bootskasse (Ausgabe bearbeiten)."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from toern.models import Toern, Teilnahme
from .models import Ausgabe

User = get_user_model()


def _user(email):
    return User.objects.create(email=email, username=email, email_verified=True)


class AusgabeBearbeitenTests(TestCase):
    def setUp(self):
        self.anbieter = _user("anbieter@test.de")
        self.zahler_user = _user("zahler@test.de")
        self.crew_user = _user("crew@test.de")
        self.fremder = _user("fremd@test.de")

        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)
        self.zahler = Teilnahme.objects.create(
            toern=self.toern, user=self.zahler_user, status="bestaetigt", rolle="crew", boot=self.boot
        )
        self.crew = Teilnahme.objects.create(
            toern=self.toern, user=self.crew_user, status="bestaetigt", rolle="crew", boot=self.boot
        )

        self.ausgabe = Ausgabe.objects.create(
            boot=self.boot, toern=self.toern,
            beschreibung="Einkauf Hafen", betrag=Decimal("30.00"),
            bezahlt_von=self.zahler, erstellt_von=self.zahler_user,
        )
        self.ausgabe.beteiligt.set([self.zahler, self.crew])

    def _bearbeiten(self, user, **overrides):
        self.client.force_login(user)
        data = {
            "beschreibung": "Einkauf Hafen + Eis",
            "betrag": "45,50",
            "bezahlt_von": self.crew.id,
            "beteiligt": [self.crew.id],
        }
        data.update(overrides)
        return self.client.post(reverse("ausgabe_bearbeiten", args=[self.ausgabe.id]), data)

    def test_zahler_darf_bearbeiten(self):
        resp = self._bearbeiten(self.zahler_user)
        self.assertEqual(resp.status_code, 302)
        self.ausgabe.refresh_from_db()
        self.assertEqual(self.ausgabe.beschreibung, "Einkauf Hafen + Eis")
        self.assertEqual(self.ausgabe.betrag, Decimal("45.50"))
        self.assertEqual(self.ausgabe.bezahlt_von, self.crew)
        self.assertEqual(list(self.ausgabe.beteiligt.all()), [self.crew])

    def test_anbieter_darf_bearbeiten(self):
        resp = self._bearbeiten(self.anbieter)
        self.assertEqual(resp.status_code, 302)
        self.ausgabe.refresh_from_db()
        self.assertEqual(self.ausgabe.beschreibung, "Einkauf Hafen + Eis")

    def test_fremder_darf_nicht_bearbeiten(self):
        resp = self._bearbeiten(self.fremder)
        self.assertEqual(resp.status_code, 403)
        self.ausgabe.refresh_from_db()
        self.assertEqual(self.ausgabe.beschreibung, "Einkauf Hafen")

    def test_ungueltiger_betrag_aendert_nichts(self):
        self._bearbeiten(self.zahler_user, betrag="quatsch")
        self.ausgabe.refresh_from_db()
        self.assertEqual(self.ausgabe.betrag, Decimal("30.00"))
