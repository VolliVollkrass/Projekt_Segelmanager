"""Tests: Ausgleichszahlungen als beglichen markieren.

Die Vorschläge unter „So gleicht ihr aus" werden aus den Salden gerechnet und
stehen nirgends. Erst eine Ausgleichszahlung hält fest, dass wirklich Geld
geflossen ist — und lässt den Vorschlag verschwinden.
"""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot, Kabine
from finance.models import Ausgabe, Ausgleichszahlung
from toern.models import Teilnahme, Toern

User = get_user_model()


def _user(email, vorname):
    return User.objects.create(
        email=email, username=email, email_verified=True, first_name=vorname,
    )


class AusgleichTestBase(TestCase):
    def setUp(self):
        self.anbieter = _user("aus-anbieter@test.de", "Anna")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)
        Kabine.objects.create(boot=self.boot, name="K1", betten=4)

        self.erika = _user("aus-erika@test.de", "Erika")
        self.t_erika = Teilnahme.objects.create(
            toern=self.toern, user=self.erika, status="bestaetigt",
            rolle="skipper", boot=self.boot,
        )
        self.hubert = _user("aus-hubert@test.de", "Hubert")
        self.t_hubert = Teilnahme.objects.create(
            toern=self.toern, user=self.hubert, status="bestaetigt",
            rolle="crew", boot=self.boot,
        )
        self.carla = _user("aus-carla@test.de", "Carla")
        self.t_carla = Teilnahme.objects.create(
            toern=self.toern, user=self.carla, status="bestaetigt",
            rolle="crew", boot=self.boot,
        )
        self.fremder = _user("aus-fremd@test.de", "Fritz")

        # Erika zahlt 90 € für alle drei → je 30 €, Hubert und Carla schulden ihr je 30 €
        a = Ausgabe.objects.create(
            boot=self.boot, toern=self.toern, beschreibung="Grundeinkauf",
            betrag=Decimal("90.00"), bezahlt_von=self.t_erika, erstellt_von=self.erika,
        )
        a.beteiligt.set([self.t_erika, self.t_hubert, self.t_carla])

    def _url(self):
        return reverse("ausgleich_beglichen", args=[self.toern.id, self.boot.id])

    def _beglichen(self, user, von, an, betrag="30.00"):
        self.client.force_login(user)
        return self.client.post(self._url(), {"von": von.id, "an": an.id, "betrag": betrag})

    def _ctx(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("boot_dashboard", args=[self.toern.id])).context

    def _transfers(self, user=None):
        return [
            (t["von"].user.first_name, t["an"].user.first_name, t["betrag"])
            for t in self._ctx(user or self.erika)["kasse_transfers"]
        ]


class BeglichenMarkierenTests(AusgleichTestBase):
    def test_ausgangslage(self):
        transfers = self._transfers()
        self.assertEqual(len(transfers), 2)
        self.assertIn(("Hubert", "Erika", Decimal("30.00")), transfers)
        self.assertIn(("Carla", "Erika", Decimal("30.00")), transfers)

    def test_zahler_darf_beglichen_markieren(self):
        resp = self._beglichen(self.hubert, self.t_hubert, self.t_erika)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(Ausgleichszahlung.objects.count(), 1)

    def test_empfaenger_darf_ebenfalls_markieren(self):
        """Erika sieht den Eingang auf ihrem Konto und hakt selbst ab."""
        self._beglichen(self.erika, self.t_hubert, self.t_erika)
        self.assertEqual(Ausgleichszahlung.objects.count(), 1)

    def test_beglichener_transfer_verschwindet(self):
        self._beglichen(self.hubert, self.t_hubert, self.t_erika)
        transfers = self._transfers()
        self.assertEqual(len(transfers), 1)
        self.assertEqual(transfers[0], ("Carla", "Erika", Decimal("30.00")))

    def test_alle_beglichen_heisst_nichts_mehr_offen(self):
        self._beglichen(self.hubert, self.t_hubert, self.t_erika)
        self._beglichen(self.carla, self.t_carla, self.t_erika)
        self.assertEqual(self._transfers(), [])

    def test_salden_gehen_auf_null(self):
        self._beglichen(self.hubert, self.t_hubert, self.t_erika)
        self._beglichen(self.carla, self.t_carla, self.t_erika)
        salden = {s["teilnahme"].user.first_name: s["saldo"] for s in self._ctx(self.erika)["kasse_salden"]}
        for name in ("Erika", "Hubert", "Carla"):
            self.assertEqual(salden[name].quantize(Decimal("0.01")), Decimal("0.00"))

    def test_teilzahlung_laesst_den_rest_stehen(self):
        self._beglichen(self.hubert, self.t_hubert, self.t_erika, betrag="10.00")
        transfers = dict(((v, a), b) for v, a, b in self._transfers())
        self.assertEqual(transfers[("Hubert", "Erika")], Decimal("20.00"))

    def test_gesamtsumme_der_ausgaben_bleibt_unberuehrt(self):
        """Eine Ausgleichszahlung ist keine Ausgabe — sie ändert nichts daran,
        wie viel die Crew insgesamt ausgegeben hat."""
        self._beglichen(self.hubert, self.t_hubert, self.t_erika)
        self.assertEqual(self._ctx(self.erika)["kasse_gesamt"], Decimal("90.00"))


class RechteTests(AusgleichTestBase):
    def test_unbeteiligter_darf_nicht_markieren(self):
        """Carla kann nicht bestätigen, dass Hubert bei Erika bezahlt hat."""
        self._beglichen(self.carla, self.t_hubert, self.t_erika)
        self.assertEqual(Ausgleichszahlung.objects.count(), 0)

    def test_fremder_bekommt_403(self):
        self.client.force_login(self.fremder)
        resp = self.client.post(
            self._url(), {"von": self.t_hubert.id, "an": self.t_erika.id, "betrag": "30.00"}
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(Ausgleichszahlung.objects.count(), 0)

    def test_get_ist_nicht_erlaubt(self):
        self.client.force_login(self.hubert)
        self.assertEqual(self.client.get(self._url()).status_code, 405)

    def test_ungueltiger_betrag_wird_abgelehnt(self):
        self._beglichen(self.hubert, self.t_hubert, self.t_erika, betrag="-5")
        self.assertEqual(Ausgleichszahlung.objects.count(), 0)

    def test_zahlung_an_sich_selbst_wird_abgelehnt(self):
        self._beglichen(self.hubert, self.t_hubert, self.t_hubert)
        self.assertEqual(Ausgleichszahlung.objects.count(), 0)

    def test_komma_als_dezimaltrenner_wird_verstanden(self):
        self._beglichen(self.hubert, self.t_hubert, self.t_erika, betrag="12,50")
        self.assertEqual(Ausgleichszahlung.objects.get().betrag, Decimal("12.50"))


class ZuruecknehmenTests(AusgleichTestBase):
    def _zahlung(self):
        self._beglichen(self.hubert, self.t_hubert, self.t_erika)
        return Ausgleichszahlung.objects.get()

    def _zuruecknehmen(self, user, zahlung):
        self.client.force_login(user)
        return self.client.post(reverse("ausgleich_zuruecknehmen", args=[zahlung.id]))

    def test_zahler_darf_zuruecknehmen(self):
        z = self._zahlung()
        self._zuruecknehmen(self.hubert, z)
        self.assertEqual(Ausgleichszahlung.objects.count(), 0)

    def test_empfaenger_darf_zuruecknehmen(self):
        z = self._zahlung()
        self._zuruecknehmen(self.erika, z)
        self.assertEqual(Ausgleichszahlung.objects.count(), 0)

    def test_unbeteiligter_darf_nicht(self):
        z = self._zahlung()
        self._zuruecknehmen(self.carla, z)
        self.assertEqual(Ausgleichszahlung.objects.count(), 1)

    def test_nach_ruecknahme_steht_der_transfer_wieder_da(self):
        z = self._zahlung()
        self.assertEqual(len(self._transfers()), 1)
        self._zuruecknehmen(self.hubert, z)
        self.assertEqual(len(self._transfers()), 2)


class AnzeigeTests(AusgleichTestBase):
    def _knopf_anzahl(self, user):
        """Wie viele „Beglichen"-Formulare rendert die Seite für diese Person?"""
        self.client.force_login(user)
        html = self.client.get(reverse("boot_dashboard", args=[self.toern.id])).content.decode()
        return html.count(reverse("ausgleich_beglichen", args=[self.toern.id, self.boot.id]))

    def test_button_erscheint_nur_bei_den_beteiligten(self):
        """Carla sieht an Huberts Zeile keinen Knopf — nur an ihrer eigenen."""
        self.assertEqual(self._knopf_anzahl(self.carla), 1)

    def test_beide_beteiligten_sehen_ihren_knopf(self):
        # Erika ist an beiden Transfers beteiligt
        self.assertEqual(self._knopf_anzahl(self.erika), 2)

    def test_ohne_offene_transfers_kein_knopf(self):
        self._beglichen(self.hubert, self.t_hubert, self.t_erika)
        self._beglichen(self.carla, self.t_carla, self.t_erika)
        self.assertEqual(self._knopf_anzahl(self.erika), 0)

    def test_eingetragene_zahlung_wird_aufgelistet(self):
        self._beglichen(self.hubert, self.t_hubert, self.t_erika)
        self.client.force_login(self.carla)
        html = self.client.get(reverse("boot_dashboard", args=[self.toern.id])).content.decode()
        self.assertIn("Bereits beglichen", html)
