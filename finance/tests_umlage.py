"""Tests: Törn-Umlage — eine Rechnung über alle Boote verteilen.

Beispiel aus der Praxis: Der Skipper zahlt das Restaurant, Olaf hat vorab
30 € gegeben, Harald hatte Wein extra. Jeder sieht seinen Anteil in seiner
Bootskasse, auch auf dem anderen Boot.
"""
from datetime import timedelta
from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot, Kabine
from finance.models import Umlage, UmlageAnteil
from finance.tests_ausgleich import _user
from finance.utils import verteile_umlage
from toern.models import Teilnahme, Toern


class VerteilungTests(SimpleTestCase):
    def test_gleichmaessig(self):
        anteile = verteile_umlage(Decimal("90"), [1, 2, 3])
        self.assertEqual(set(anteile.values()), {Decimal("30.00")})

    def test_cents_gehen_auf(self):
        anteile = verteile_umlage(Decimal("100"), [1, 2, 3])
        self.assertEqual(anteile, {1: Decimal("33.34"), 2: Decimal("33.33"), 3: Decimal("33.33")})
        self.assertEqual(sum(anteile.values()), Decimal("100.00"))

    def test_1300_auf_30_personen(self):
        anteile = verteile_umlage(Decimal("1300"), list(range(30)))
        self.assertEqual(sum(anteile.values()), Decimal("1300.00"))
        self.assertEqual(max(anteile.values()) - min(anteile.values()), Decimal("0.01"))

    def test_extras_werden_herausgerechnet(self):
        """Haralds Wein (100 €) steckt in den 1300 € — der Rest wird geteilt."""
        anteile = verteile_umlage(Decimal("1300"), [1, 2, 3, 4], {3: Decimal("100")})
        self.assertEqual(anteile[1], Decimal("300.00"))
        self.assertEqual(anteile[3], Decimal("400.00"))
        self.assertEqual(sum(anteile.values()), Decimal("1300.00"))

    def test_extras_von_nicht_ausgewaehlten_zaehlen_nicht(self):
        anteile = verteile_umlage(Decimal("100"), [1, 2], {9: Decimal("50")})
        self.assertEqual(anteile, {1: Decimal("50.00"), 2: Decimal("50.00")})

    def test_zu_hohe_extras(self):
        with self.assertRaises(ValueError):
            verteile_umlage(Decimal("50"), [1, 2], {1: Decimal("60")})

    def test_niemand_ausgewaehlt(self):
        with self.assertRaises(ValueError):
            verteile_umlage(Decimal("50"), [])


class UmlageTestBase(TestCase):
    def setUp(self):
        self.anbieter = _user("uml-anbieter@test.de", "Anna")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Umlagetörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Adria", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot1 = Boot.objects.create(name="Alpha", typ="Yacht", toern=self.toern)
        self.boot2 = Boot.objects.create(name="Beta", typ="Yacht", toern=self.toern)
        Kabine.objects.create(boot=self.boot1, name="K1", betten=4)
        Kabine.objects.create(boot=self.boot2, name="K1", betten=4)

        def teilnahme(email, vorname, boot, rolle="crew"):
            user = _user(email, vorname)
            return user, Teilnahme.objects.create(
                toern=self.toern, user=user, status="bestaetigt", rolle=rolle, boot=boot,
            )

        self.volker, self.t_volker = teilnahme("uml-volker@test.de", "Volker", self.boot1, "skipper")
        self.olaf, self.t_olaf = teilnahme("uml-olaf@test.de", "Olaf", self.boot1)
        self.ralf, self.t_ralf = teilnahme("uml-ralf@test.de", "Ralf", self.boot2)
        self.harald, self.t_harald = teilnahme("uml-harald@test.de", "Harald", self.boot2)

        self.volker.zahlung_iban = "DE89370400440532013000"
        self.volker.save()

    def _anlegen(self, user=None, **extra):
        daten = {
            "beschreibung": "Restaurant",
            "betrag": "400",
            "bezahlt_von": self.t_volker.id,
            "teilnehmer": [self.t_volker.id, self.t_olaf.id, self.t_ralf.id, self.t_harald.id],
            f"extra_{self.t_harald.id}": "40",
            f"gegeben_{self.t_olaf.id}": "30",
        }
        daten.update(extra)
        self.client.force_login(user or self.volker)
        return self.client.post(reverse("umlage_erstellen", args=[self.toern.id]), daten)

    def _anteil(self, t):
        return UmlageAnteil.objects.get(teilnahme=t)

    def _ctx(self, user):
        self.client.force_login(user)
        return self.client.get(reverse("boot_dashboard", args=[self.toern.id])).context


class AnlegenTests(UmlageTestBase):
    def test_skipper_legt_an_und_rechnung_stimmt(self):
        resp = self._anlegen()
        self.assertEqual(resp.status_code, 302)
        # 400 − 40 Wein = 360 / 4 = 90 pro Kopf
        self.assertEqual(self._anteil(self.t_olaf).anteil, Decimal("90.00"))
        self.assertEqual(self._anteil(self.t_olaf).offen, Decimal("60.00"))
        self.assertEqual(self._anteil(self.t_harald).anteil, Decimal("130.00"))
        self.assertEqual(self._anteil(self.t_ralf).offen, Decimal("90.00"))
        summe = sum(a.anteil for a in UmlageAnteil.objects.all())
        self.assertEqual(summe, Decimal("400.00"))

    def test_zahler_zahlt_sich_nichts_selbst_an(self):
        self._anlegen(**{f"gegeben_{self.t_volker.id}": "50"})
        self.assertEqual(self._anteil(self.t_volker).schon_gegeben, Decimal("0"))

    def test_zu_viel_angezahlt_heisst_zurueck(self):
        self._anlegen(**{f"gegeben_{self.t_olaf.id}": "100"})
        self.assertEqual(self._anteil(self.t_olaf).zurueck, Decimal("10.00"))

    def test_crew_darf_nicht_anlegen(self):
        self.assertEqual(self._anlegen(user=self.olaf).status_code, 403)
        self.assertFalse(Umlage.objects.exists())

    def test_anbieter_darf_anlegen(self):
        self._anlegen(user=self.anbieter)
        self.assertEqual(Umlage.objects.count(), 1)

    def test_fehler_behaelt_eingaben(self):
        resp = self._anlegen(**{f"extra_{self.t_harald.id}": "500"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Die Extras sind zusammen höher")
        self.assertContains(resp, 'value="Restaurant"')
        self.assertFalse(Umlage.objects.exists())

    def test_fremde_teilnahme_wird_ignoriert(self):
        anderer_toern = Toern.objects.create(
            titel="Anderer", anbieter=self.anbieter,
            startdatum=timezone.now(), enddatum=timezone.now() + timedelta(days=3),
            revier="Ostsee", preis_pro_person=1,
        )
        fremd = Teilnahme.objects.create(
            toern=anderer_toern, user=_user("uml-fremd@test.de", "Fritz"), status="bestaetigt",
        )
        self._anlegen(teilnehmer=[self.t_olaf.id, fremd.id])
        self.assertEqual(
            list(UmlageAnteil.objects.values_list("teilnahme_id", flat=True)), [self.t_olaf.id]
        )


class BootskasseAnzeigeTests(UmlageTestBase):
    def setUp(self):
        super().setUp()
        self._anlegen()

    def test_crew_auf_anderem_boot_sieht_eigenen_anteil(self):
        ctx = self._ctx(self.ralf)
        anteile = ctx["umlage_meine_anteile"]
        self.assertEqual(len(anteile), 1)
        self.assertEqual(anteile[0].offen, Decimal("90.00"))
        self.assertTrue(any(w["art"] == "iban" for w in anteile[0].zahlungswege))

    def test_crew_sieht_keine_gesamtuebersicht(self):
        self.assertEqual(self._ctx(self.ralf)["umlage_uebersicht"], [])

    def test_zahler_sieht_uebersicht_aber_keinen_eigenen_anteil(self):
        ctx = self._ctx(self.volker)
        self.assertEqual(ctx["umlage_meine_anteile"], [])
        uebersicht = ctx["umlage_uebersicht"][0]
        self.assertEqual(uebersicht["offen_anzahl"], 3)
        self.assertEqual(uebersicht["offen_summe"], Decimal("280.00"))  # 60 + 90 + 130

    def test_boots_salden_bleiben_unberuehrt(self):
        ctx = self._ctx(self.olaf)
        self.assertEqual(ctx["kasse_gesamt"], Decimal("0"))
        self.assertEqual(ctx["kasse_transfers"], [])

    def test_seite_rendert_mit_iban(self):
        self.client.force_login(self.harald)
        resp = self.client.get(reverse("boot_dashboard", args=[self.toern.id]))
        self.assertContains(resp, "Törn-Umlagen")
        self.assertContains(resp, "DE89 3704 0044 0532 0130 00")


class BeglichenTests(UmlageTestBase):
    def setUp(self):
        super().setUp()
        self._anlegen()
        self.a_ralf = self._anteil(self.t_ralf)
        self.url = reverse("umlage_anteil_beglichen", args=[self.a_ralf.id])

    def test_schuldner_markiert(self):
        self.client.force_login(self.ralf)
        self.client.post(self.url)
        self.a_ralf.refresh_from_db()
        self.assertIsNotNone(self.a_ralf.beglichen_am)
        self.assertIsNone(self._ctx(self.ralf)["umlage_meine_anteile"][0].zahlungswege)

    def test_zahler_markiert_und_nimmt_zurueck(self):
        self.client.force_login(self.volker)
        self.client.post(self.url)
        self.client.post(self.url)
        self.a_ralf.refresh_from_db()
        self.assertIsNone(self.a_ralf.beglichen_am)

    def test_dritte_duerfen_nicht(self):
        self.client.force_login(self.harald)
        self.assertEqual(self.client.post(self.url).status_code, 403)


class BearbeitenTests(UmlageTestBase):
    def setUp(self):
        super().setUp()
        self._anlegen()
        self.umlage = Umlage.objects.get()
        for t in (self.t_olaf, self.t_ralf):
            a = self._anteil(t)
            a.beglichen_am = timezone.now()
            a.save()

    def _bearbeiten(self, user=None, **extra):
        daten = {
            "beschreibung": "Restaurant",
            "betrag": "400",
            "bezahlt_von": self.t_volker.id,
            "teilnehmer": [self.t_volker.id, self.t_olaf.id, self.t_ralf.id, self.t_harald.id],
            f"extra_{self.t_harald.id}": "40",
            f"gegeben_{self.t_olaf.id}": "30",
        }
        daten.update(extra)
        self.client.force_login(user or self.volker)
        return self.client.post(
            reverse("umlage_bearbeiten", args=[self.toern.id, self.umlage.id]), daten
        )

    def test_formular_ist_vorausgefuellt(self):
        self.client.force_login(self.volker)
        resp = self.client.get(reverse("umlage_bearbeiten", args=[self.toern.id, self.umlage.id]))
        self.assertContains(resp, 'value="400,00"')
        self.assertContains(resp, f'name="extra_{self.t_harald.id}" value="40,00"')

    def test_beglichen_bleibt_wenn_betrag_gleich(self):
        """Olafs Anzahlung ändert sich, sein offener Betrag aber nicht."""
        self._bearbeiten(beschreibung="Restaurant Konoba")
        self.assertIsNotNone(self._anteil(self.t_olaf).beglichen_am)
        self.assertIsNotNone(self._anteil(self.t_ralf).beglichen_am)

    def test_beglichen_wird_zurueckgesetzt_wenn_betrag_anders(self):
        self._bearbeiten(betrag="440")
        self.assertIsNone(self._anteil(self.t_ralf).beglichen_am)

    def test_abgewaehlte_person_faellt_raus(self):
        self._bearbeiten(teilnehmer=[self.t_volker.id, self.t_olaf.id, self.t_harald.id])
        self.assertFalse(UmlageAnteil.objects.filter(teilnahme=self.t_ralf).exists())
        self.assertEqual(sum(a.anteil for a in UmlageAnteil.objects.all()), Decimal("400.00"))

    def test_crew_darf_nicht_bearbeiten(self):
        self.assertEqual(self._bearbeiten(user=self.ralf).status_code, 403)

    def test_loeschen(self):
        self.client.force_login(self.ralf)
        url = reverse("umlage_loeschen", args=[self.umlage.id])
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_login(self.volker)
        self.client.post(url)
        self.assertFalse(Umlage.objects.exists())
        self.assertFalse(UmlageAnteil.objects.exists())
