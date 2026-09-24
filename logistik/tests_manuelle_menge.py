"""Tests: Was von Hand auf der Liste steht, verschluckt keine Rezeptmenge.

Der Fehler: Wer „1 l Milch" manuell eintrug und dessen Rezept 50 ml verlangte,
bekam beim Generieren weiter nur 1 l — der Rezeptanteil wurde kommentarlos
verworfen. Man kaufte also zu wenig ein.
"""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from logistik.models import EinkaufslistenEintrag, Mahlzeit
from rezepte.models import Rezept, RezeptZutat
from toern.models import Teilnahme, Toern

User = get_user_model()


def _user(email, **extra):
    return User.objects.create(email=email, username=email, email_verified=True, **extra)


class ManuelleMengeTestBase(TestCase):
    def setUp(self):
        self.anbieter = _user("mm-anbieter@test.de")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)
        self.skipper = _user("mm-skipper@test.de")
        Teilnahme.objects.create(
            toern=self.toern, user=self.skipper, status="bestaetigt",
            rolle="skipper", boot=self.boot,
        )
        # Genau 2 Personen auf dem Boot → Rezept für 2 Portionen skaliert 1:1
        self.crew = _user("mm-crew@test.de")
        Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt",
            rolle="crew", boot=self.boot,
        )
        self.datum = (start + timedelta(days=1)).date()
        self.client.force_login(self.skipper)
        # Grundeinkauf leeren: hier interessieren nur Rezept und Handeingabe
        from toern.views import _get_or_create_einkaufsvorlage
        _get_or_create_einkaufsvorlage(self.toern, user=self.skipper).eintraege.all().delete()

    def _rezept(self, *zutaten, name="Testgericht"):
        rezept = Rezept.objects.create(name=name, autor=self.skipper, portionen=2)
        for i, (zname, menge) in enumerate(zutaten):
            RezeptZutat.objects.create(rezept=rezept, name=zname, menge=menge, order=i)
        Mahlzeit.objects.create(
            boot=self.boot, toern=self.toern, datum=self.datum,
            typ="abend", name=name, rezept=rezept,
        )
        return rezept

    def _add(self, name, menge):
        return self.client.post(
            reverse("einkaufsliste_add", args=[self.toern.id, self.boot.id]),
            {"name": name, "menge": menge},
        )

    def _generieren(self):
        return json.loads(self.client.post(
            reverse("einkaufsliste_generieren", args=[self.toern.id, self.boot.id])
        ).content)

    def _posten(self, name):
        return EinkaufslistenEintrag.objects.get(
            boot=self.boot, toern=self.toern, archiviert=False, name__iexact=name
        )

    def _aktiv(self):
        return EinkaufslistenEintrag.objects.filter(
            boot=self.boot, toern=self.toern, archiviert=False
        )


class RezeptmengeKommtDazuTests(ManuelleMengeTestBase):
    def test_der_gemeldete_fall_milch(self):
        """1 l von Hand + 50 ml aus dem Rezept = beides auf dem Zettel."""
        self._rezept(("Milch", "50 ml"))
        self._add("Milch", "1 l")

        self._generieren()
        menge = self._posten("Milch").menge
        self.assertIn("1 l", menge)
        self.assertIn("50 ml", menge)

    def test_gleiche_einheit_wird_addiert(self):
        self._rezept(("Milch", "500 ml"))
        self._add("Milch", "250 ml")

        self._generieren()
        self.assertEqual(self._posten("Milch").menge, "750 ml")

    def test_eier_werden_zusammengezaehlt(self):
        self._rezept(("Eier", "4"))
        self._add("Eier", "10")

        self._generieren()
        self.assertEqual(self._posten("Eier").menge, "14")

    def test_es_entsteht_keine_zweite_zeile(self):
        self._rezept(("Milch", "50 ml"))
        self._add("Milch", "1 l")

        self._generieren()
        self.assertEqual(self._aktiv().filter(name__iexact="Milch").count(), 1)

    def test_schreibweise_mit_zusatz_findet_den_manuellen_posten(self):
        self._rezept(("Milch (kalt)", "50 ml"))
        self._add("Milch", "1 l")

        self._generieren()
        self.assertEqual(self._aktiv().filter(name__iexact="Milch").count(), 1)
        self.assertIn("50 ml", self._posten("Milch").menge)

    def test_rezeptname_wird_vermerkt(self):
        self._rezept(("Milch", "50 ml"), name="Pfannkuchen")
        self._add("Milch", "1 l")

        self._generieren()
        self.assertIn("Pfannkuchen", self._posten("Milch").rezept_info)

    def test_posten_ohne_rezept_bleibt_wie_eingetragen(self):
        self._rezept(("Mehl", "500 g"))
        self._add("Schokolade", "2 Tafeln")

        self._generieren()
        self.assertEqual(self._posten("Schokolade").menge, "2 Tafeln")


class MehrfachGenerierenTests(ManuelleMengeTestBase):
    """Der Grund für das eigene Feld: zweimal generieren darf nicht doppelt zählen."""

    def test_zweimal_generieren_aendert_nichts(self):
        self._rezept(("Milch", "500 ml"))
        self._add("Milch", "250 ml")

        self._generieren()
        nach_eins = self._posten("Milch").menge
        self._generieren()
        self.assertEqual(self._posten("Milch").menge, nach_eins)

    def test_dreimal_generieren_bleibt_stabil(self):
        self._rezept(("Eier", "4"))
        self._add("Eier", "10")

        for _ in range(3):
            self._generieren()
        self.assertEqual(self._posten("Eier").menge, "14")

    def test_altbestand_ohne_eigene_menge_heilt_sich(self):
        """Posten, die vor dieser Änderung entstanden sind, haben das Feld
        noch nicht gefüllt — ihre aktuelle Menge IST die eigene."""
        self._rezept(("Milch", "500 ml"))
        alt = EinkaufslistenEintrag.objects.create(
            boot=self.boot, toern=self.toern, name="Milch", menge="250 ml",
            kategorie="milch_kase", quelle="manuell",  # manuelle_menge absichtlich leer
        )

        self._generieren()
        alt.refresh_from_db()
        self.assertEqual(alt.manuelle_menge, "250 ml")
        self.assertEqual(alt.menge, "750 ml")

        self._generieren()
        alt.refresh_from_db()
        self.assertEqual(alt.menge, "750 ml")

    def test_rezept_entfaellt_menge_faellt_zurueck(self):
        self._rezept(("Milch", "500 ml"))
        self._add("Milch", "250 ml")
        self._generieren()
        self.assertEqual(self._posten("Milch").menge, "750 ml")

        Mahlzeit.objects.all().delete()
        self._generieren()
        self.assertEqual(self._posten("Milch").menge, "250 ml")

    def test_bearbeitete_menge_wird_zur_eigenen_menge(self):
        self._rezept(("Milch", "500 ml"))
        self._add("Milch", "250 ml")
        self._generieren()

        posten = self._posten("Milch")
        self.client.post(
            reverse("einkaufsliste_update", args=[posten.id]),
            data=json.dumps({"menge": "1 l"}), content_type="application/json",
        )
        posten.refresh_from_db()
        self.assertEqual(posten.manuelle_menge, "1 l")

        # l und ml werden nicht ineinander umgerechnet — beides steht
        # nebeneinander, statt eine Angabe zu verlieren.
        self._generieren()
        self.assertEqual(self._posten("Milch").menge, "1 l + 500 ml")


class ZusammenlegenUndGenerierenTests(ManuelleMengeTestBase):
    """Nach dem Zusammenlegen darf das Generieren nicht doppelt zählen."""

    def test_zusammengelegtes_zaehlt_den_rezeptanteil_nur_einmal(self):
        self._rezept(("Milch", "500 ml"))
        self._add("Milch", "250 ml")
        self._generieren()

        # Zweiter Posten von Hand, dann beide zusammenlegen
        self._add("Vollmilch", "1 l")
        ids = list(self._aktiv().filter(name__in=["Milch", "Vollmilch"]).values_list("id", flat=True))
        self.client.post(
            reverse("einkaufsliste_merge", args=[self.toern.id, self.boot.id]),
            data=json.dumps({"ids": ids, "name": "Milch"}), content_type="application/json",
        )

        vorher = self._posten("Milch").menge
        self._generieren()
        self.assertEqual(self._posten("Milch").menge, vorher)

    def test_aufraeumen_behaelt_nur_den_manuellen_anteil_als_eigene_menge(self):
        self._add("Milch", "250 ml")
        EinkaufslistenEintrag.objects.create(
            boot=self.boot, toern=self.toern, name="Milch (kalt)", menge="500 ml",
            kategorie="milch_kase", quelle="rezept",
        )
        self.client.post(reverse("einkaufsliste_aufraeumen", args=[self.toern.id, self.boot.id]))

        posten = self._posten("Milch")
        self.assertEqual(posten.manuelle_menge, "250 ml")
        self.assertEqual(posten.menge, "750 ml")
