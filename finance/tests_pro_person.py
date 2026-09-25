"""Tests: „Pro Person" in der Bootskassen-Statistik.

Kauft jemand etwas nur für einen Einzelnen mit, gehört der Betrag nicht in
diese Kennzahl — er verteilt sich ja nicht auf alle. Salden und Ausgleich
darunter enthalten ihn weiterhin vollständig.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot, Kabine
from finance.models import Ausgabe
from toern.models import Teilnahme, Toern

User = get_user_model()


def _user(email, vorname):
    return User.objects.create(
        email=email, username=email, email_verified=True, first_name=vorname,
    )


class ProPersonTests(TestCase):
    def setUp(self):
        self.anbieter = _user("pp-anbieter@test.de", "Anna")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)
        Kabine.objects.create(boot=self.boot, name="Kabine 1", betten=4)

        # Vier Personen an Bord: Erika (Skipper), Hubert, Carla, Dirk
        self.erika = _user("pp-erika@test.de", "Erika")
        self.t_erika = Teilnahme.objects.create(
            toern=self.toern, user=self.erika, status="bestaetigt",
            rolle="skipper", boot=self.boot,
        )
        self.crew = {}
        for email, vorname in [("pp-hubert@test.de", "Hubert"),
                               ("pp-carla@test.de", "Carla"),
                               ("pp-dirk@test.de", "Dirk")]:
            u = _user(email, vorname)
            self.crew[vorname] = Teilnahme.objects.create(
                toern=self.toern, user=u, status="bestaetigt", rolle="crew", boot=self.boot,
            )

    def _ausgabe(self, beschreibung, betrag, beteiligt):
        a = Ausgabe.objects.create(
            boot=self.boot, toern=self.toern, beschreibung=beschreibung,
            betrag=Decimal(betrag), bezahlt_von=self.t_erika, erstellt_von=self.erika,
        )
        a.beteiligt.set(beteiligt)
        return a

    def _alle(self):
        return [self.t_erika] + list(self.crew.values())

    def _stats(self):
        self.client.force_login(self.erika)
        resp = self.client.get(reverse("boot_dashboard", args=[self.toern.id]))
        return resp.context

    def test_der_gemeldete_fall(self):
        """100 € Grundeinkauf für alle vier, 10 € Kaugummi nur für Hubert.
        Pro Person sind 25 €, nicht 27,50 €."""
        self._ausgabe("Grundeinkauf", "100.00", self._alle())
        self._ausgabe("Kaugummi", "10.00", [self.crew["Hubert"]])

        ctx = self._stats()
        self.assertEqual(ctx["kasse_pro_person"], Decimal("25.00"))
        self.assertEqual(ctx["kasse_gesamt"], Decimal("110.00"))
        self.assertEqual(ctx["kasse_einzeln"], Decimal("10.00"))

    def test_ohne_einzelausgaben_bleibt_alles_wie_bisher(self):
        self._ausgabe("Grundeinkauf", "100.00", self._alle())
        self._ausgabe("Hafengeld", "60.00", self._alle())

        ctx = self._stats()
        self.assertEqual(ctx["kasse_pro_person"], Decimal("40.00"))
        self.assertEqual(ctx["kasse_einzeln"], Decimal("0.00"))

    def test_ausgabe_fuer_einen_teil_der_crew_zaehlt_nicht(self):
        """Auch drei von vier sind nicht „alle"."""
        self._ausgabe("Grundeinkauf", "100.00", self._alle())
        self._ausgabe("Cocktails", "30.00",
                      [self.t_erika, self.crew["Carla"], self.crew["Dirk"]])

        ctx = self._stats()
        self.assertEqual(ctx["kasse_pro_person"], Decimal("25.00"))
        self.assertEqual(ctx["kasse_einzeln"], Decimal("30.00"))

    def test_nur_einzelausgaben_ergeben_null_pro_person(self):
        self._ausgabe("Kaugummi", "10.00", [self.crew["Hubert"]])

        ctx = self._stats()
        self.assertEqual(ctx["kasse_pro_person"], Decimal("0.00"))
        self.assertEqual(ctx["kasse_gesamt"], Decimal("10.00"))

    def test_gesamt_enthaelt_weiterhin_alles(self):
        self._ausgabe("Grundeinkauf", "100.00", self._alle())
        self._ausgabe("Kaugummi", "10.00", [self.crew["Hubert"]])

        self.assertEqual(self._stats()["kasse_gesamt"], Decimal("110.00"))

    def test_salden_enthalten_die_einzelausgabe_weiterhin(self):
        """Unterhalb der Statistik muss weiter vollständig gerechnet werden:
        Hubert schuldet 25 € Anteil am Grundeinkauf plus 10 € Kaugummi."""
        self._ausgabe("Grundeinkauf", "100.00", self._alle())
        self._ausgabe("Kaugummi", "10.00", [self.crew["Hubert"]])

        salden = {s["teilnahme"].user.first_name: s["saldo"] for s in self._stats()["kasse_salden"]}
        self.assertEqual(salden["Hubert"].quantize(Decimal("0.01")), Decimal("-35.00"))
        self.assertEqual(salden["Carla"].quantize(Decimal("0.01")), Decimal("-25.00"))
        self.assertEqual(salden["Erika"].quantize(Decimal("0.01")), Decimal("85.00"))

    def test_hinweis_erscheint_nur_bei_einzelausgaben(self):
        self._ausgabe("Grundeinkauf", "100.00", self._alle())
        self.client.force_login(self.erika)
        html = self.client.get(reverse("boot_dashboard", args=[self.toern.id])).content.decode()
        self.assertNotIn("für Einzelne", html)

        self._ausgabe("Kaugummi", "10.00", [self.crew["Hubert"]])
        html = self.client.get(reverse("boot_dashboard", args=[self.toern.id])).content.decode()
        self.assertIn("ohne 10,00 € für Einzelne", html)
