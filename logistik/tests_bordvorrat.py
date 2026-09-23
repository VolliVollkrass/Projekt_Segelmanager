"""Tests für den Bordvorrat — was an Bord ist, gehört nicht auf den Einkaufszettel."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from logistik.models import (
    Bordvorrat, BordvorratEintrag, EinkaufslistenEintrag, Mahlzeit,
)
from rezepte.models import Rezept, RezeptZutat
from toern.models import Teilnahme, Toern

User = get_user_model()


def _user(email, **extra):
    return User.objects.create(email=email, username=email, email_verified=True, **extra)


class BordvorratTestBase(TestCase):
    def setUp(self):
        self.anbieter = _user("bv-anbieter@test.de")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)
        self.skipper = _user("bv-skipper@test.de")
        Teilnahme.objects.create(
            toern=self.toern, user=self.skipper, status="bestaetigt",
            rolle="skipper", boot=self.boot,
        )
        self.crew = _user("bv-crew@test.de")
        Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt",
            rolle="crew", boot=self.boot,
        )
        self.datum = (start + timedelta(days=1)).date()

    def _ohne_grundeinkauf(self):
        """Die Törn-Vorlage kommt mit Standard-Artikeln (Wasser & Co.). Für die
        Filter-Tests interessieren nur die Rezeptzutaten — also Vorlage leeren."""
        from toern.views import _get_or_create_einkaufsvorlage
        _get_or_create_einkaufsvorlage(self.toern, user=self.skipper).eintraege.all().delete()

    def _add(self, name, **extra):
        self.client.force_login(self.skipper)
        return self.client.post(
            reverse("bordvorrat_add", args=[self.toern.id]),
            data=json.dumps({"name": name, **extra}),
            content_type="application/json",
        )

    def _aktiv(self):
        return EinkaufslistenEintrag.objects.filter(
            boot=self.boot, toern=self.toern, archiviert=False
        )

    def _rezept_mit(self, *zutaten):
        rezept = Rezept.objects.create(name="Testgericht", autor=self.skipper, portionen=2)
        for i, (name, menge) in enumerate(zutaten):
            RezeptZutat.objects.create(rezept=rezept, name=name, menge=menge, order=i)
        Mahlzeit.objects.create(
            boot=self.boot, toern=self.toern, datum=self.datum,
            typ="abend", name="Testgericht", rezept=rezept,
        )
        return rezept

    def _generieren(self):
        self.client.force_login(self.skipper)
        return json.loads(self.client.post(
            reverse("einkaufsliste_generieren", args=[self.toern.id, self.boot.id])
        ).content)


class PflegeTests(BordvorratTestBase):
    def test_eintrag_anlegen_und_lesen(self):
        self.assertEqual(self._add("Olivenöl").status_code, 200)

        self.client.force_login(self.skipper)
        d = json.loads(self.client.get(reverse("bordvorrat_get", args=[self.toern.id])).content)
        self.assertEqual([i["name"] for i in d["items"]], ["Olivenöl"])

    def test_doppelter_eintrag_wird_abgelehnt(self):
        self._add("Salz")
        resp = self._add("salz")  # andere Schreibweise, gleicher Artikel
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(BordvorratEintrag.objects.count(), 1)

    def test_vorschlaege_blenden_vorhandenes_aus(self):
        self._add("Salz")
        self.client.force_login(self.skipper)
        d = json.loads(self.client.get(reverse("bordvorrat_get", args=[self.toern.id])).content)
        self.assertNotIn("Salz", d["vorschlaege"])
        self.assertIn("Pfeffer", d["vorschlaege"])

    def test_loeschen(self):
        self._add("Essig")
        eintrag = BordvorratEintrag.objects.get()
        self.client.force_login(self.skipper)
        self.client.post(reverse("bordvorrat_delete", args=[self.toern.id, eintrag.id]))
        self.assertEqual(BordvorratEintrag.objects.count(), 0)

    def test_crew_darf_nicht_pflegen(self):
        self.client.force_login(self.crew)
        resp = self.client.post(
            reverse("bordvorrat_add", args=[self.toern.id]),
            data=json.dumps({"name": "Salz"}), content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(
            self.client.get(reverse("bordvorrat_get", args=[self.toern.id])).status_code, 403
        )


class FilterTests(BordvorratTestBase):
    def test_bordvorrat_posten_landen_nicht_auf_der_liste(self):
        self._ohne_grundeinkauf()
        self._rezept_mit(("Olivenöl", "5 EL"), ("Tomaten", "500 g"))
        self._add("Olivenöl")

        d = self._generieren()
        namen = set(self._aktiv().values_list("name", flat=True))
        self.assertNotIn("Olivenöl", namen)
        self.assertIn("Tomaten", namen)
        self.assertEqual(d["vom_bordvorrat"], 1)

    def test_schreibweise_mit_zusatz_wird_erkannt(self):
        """„Olivenöl (nur falls der Speck mager ist)" fällt unter „Olivenöl"."""
        self._ohne_grundeinkauf()
        self._rezept_mit(("Olivenöl (nur falls der Speck sehr mager ist)", "5 EL"))
        self._add("Olivenöl")

        self._generieren()
        self.assertEqual(self._aktiv().count(), 0)

    def test_ohne_bordvorrat_bleibt_alles_wie_bisher(self):
        self._ohne_grundeinkauf()
        self._rezept_mit(("Olivenöl", "5 EL"), ("Tomaten", "500 g"))
        d = self._generieren()
        self.assertEqual(d["vom_bordvorrat"], 0)
        self.assertEqual(self._aktiv().count(), 2)

    def test_eintrag_wirkt_erst_ab_dem_naechsten_generieren(self):
        """Ohne das Häkchen bleibt die laufende Liste unangetastet — sonst
        verschwände mitten im Einkauf etwas vom Zettel."""
        self._ohne_grundeinkauf()
        self._rezept_mit(("Olivenöl", "5 EL"))
        self._generieren()
        self.assertEqual(self._aktiv().count(), 1)

        self._add("Olivenöl")
        self.assertEqual(self._aktiv().count(), 1)

        self._generieren()
        self.assertEqual(self._aktiv().count(), 0)

    def test_mit_haekchen_verschwindet_der_posten_sofort(self):
        self._ohne_grundeinkauf()
        self._rezept_mit(("Olivenöl", "5 EL"))
        self._generieren()

        resp = self._add("Olivenöl", von_liste_entfernen=True)
        self.assertEqual(json.loads(resp.content)["entfernt"], 1)
        self.assertEqual(self._aktiv().count(), 0)

    def test_bordvorrat_gilt_pro_toern_nicht_global(self):
        anderer = Toern.objects.create(
            titel="Anderer Törn", anbieter=self.anbieter,
            startdatum=timezone.now() + timedelta(days=90),
            enddatum=timezone.now() + timedelta(days=97),
            revier="Nordsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self._add("Salz")
        self.assertEqual(Bordvorrat.objects.filter(toern=anderer).count(), 0)

        from logistik.bordvorrat_views import bordvorrat_schluessel
        self.assertEqual(bordvorrat_schluessel(anderer), set())
        self.assertIn("salz", bordvorrat_schluessel(self.toern))
