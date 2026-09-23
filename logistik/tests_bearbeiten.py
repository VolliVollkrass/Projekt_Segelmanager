"""Tests für das Bearbeiten der Einkaufsliste von Hand und die Kochmengen-Regel."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from logistik.models import EinkaufslistenEintrag, EinkaufslistenSnapshot
from toern.models import Teilnahme, Toern
from utils.rezept_skalierung import ist_kochmenge, summiere_mengen

User = get_user_model()


def _user(email, **extra):
    return User.objects.create(email=email, username=email, email_verified=True, **extra)


class KochmengenTests(SimpleTestCase):
    """„5 Prisen Salz" sagt nichts darüber, wie viel Salz zu kaufen ist."""

    def test_kochmengen_werden_erkannt(self):
        for menge in ["5 Prise", "2 Prisen", "1 Messerspitze", "etwas", "nach Bedarf",
                      "nach Belieben", "1 Spritzer", "ein Schuss".replace("ein ", "1 ")]:
            self.assertTrue(ist_kochmenge(menge), f"{menge!r} sollte Kochmenge sein")

    def test_kaufmengen_werden_nicht_geschluckt(self):
        for menge in ["1 Packung", "500 g", "2 kg", "1 Flasche", "3 Stück",
                      "5 EL", "2 TL", "40 Scheiben", "1 Bund"]:
            self.assertFalse(ist_kochmenge(menge), f"{menge!r} ist eine Kaufmenge")

    def test_packung_bleibt_prisen_verschwinden(self):
        """Der Fall aus der Praxis: Grundeinkauf sagt „1 Packung Salz",
        drei Rezepte sagen „Prise"."""
        self.assertEqual(summiere_mengen(["1 Packung", "5 Prise", "2 Prise"]), "1 Packung")

    def test_flasche_bleibt_etwas_verschwindet(self):
        self.assertEqual(summiere_mengen(["1 Flasche", "etwas"]), "1 Flasche")

    def test_alleinige_kochmenge_bleibt_stehen(self):
        """Sonst stünde der Posten ohne Menge da — gekauft werden muss er ja."""
        self.assertEqual(summiere_mengen(["etwas"]), "etwas")
        self.assertEqual(summiere_mengen(["5 Prise", "2 Prise"]), "7 Prise")

    def test_esslöffel_und_scheiben_bleiben(self):
        """40 Scheiben Gurke sind mehr als 2 Gurken — wer das schluckt,
        kauft zu wenig ein."""
        self.assertEqual(summiere_mengen(["40 Scheiben", "2"]), "40 Scheiben + 2")
        self.assertEqual(summiere_mengen(["5 EL", "1 Flasche"]), "5 EL + 1 Flasche")


class BearbeitenTestBase(TestCase):
    def setUp(self):
        self.anbieter = _user("bea-anbieter@test.de")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)
        self.skipper = _user("bea-skipper@test.de")
        Teilnahme.objects.create(
            toern=self.toern, user=self.skipper, status="bestaetigt",
            rolle="skipper", boot=self.boot,
        )
        self.fremder = _user("bea-fremd@test.de")

    def _eintrag(self, name, menge="", **extra):
        return EinkaufslistenEintrag.objects.create(
            boot=self.boot, toern=self.toern, name=name, menge=menge,
            kategorie=extra.pop("kategorie", "sonstiges"),
            quelle=extra.pop("quelle", "rezept"), **extra,
        )

    def _aktiv(self):
        return EinkaufslistenEintrag.objects.filter(
            boot=self.boot, toern=self.toern, archiviert=False
        )

    def _update(self, eintrag, **daten):
        self.client.force_login(self.skipper)
        return self.client.post(
            reverse("einkaufsliste_update", args=[eintrag.id]),
            data=json.dumps(daten), content_type="application/json",
        )

    def _merge(self, ids, **daten):
        self.client.force_login(self.skipper)
        return self.client.post(
            reverse("einkaufsliste_merge", args=[self.toern.id, self.boot.id]),
            data=json.dumps({"ids": ids, **daten}), content_type="application/json",
        )


class PostenBearbeitenTests(BearbeitenTestBase):
    def test_menge_aendern(self):
        e = self._eintrag("Kartoffeln", "2000 g")
        self._update(e, menge="5 kg")
        e.refresh_from_db()
        self.assertEqual(e.menge, "5 kg")

    def test_name_und_kategorie_aendern(self):
        e = self._eintrag("Sardinien", "1 Packung", kategorie="sonstiges")
        self._update(e, name="Sardinen", kategorie="konserven")
        e.refresh_from_db()
        self.assertEqual(e.name, "Sardinen")
        self.assertEqual(e.kategorie, "konserven")

    def test_bearbeiteter_posten_gilt_als_manuell(self):
        """Damit er beim nächsten Generieren nicht wieder überschrieben wird."""
        e = self._eintrag("Kartoffeln", "2000 g", quelle="rezept")
        self._update(e, menge="5 kg")
        e.refresh_from_db()
        self.assertEqual(e.quelle, "manuell")

    def test_leerer_name_wird_abgelehnt(self):
        e = self._eintrag("Kartoffeln", "2 kg")
        resp = self._update(e, name="  ")
        self.assertEqual(resp.status_code, 400)
        e.refresh_from_db()
        self.assertEqual(e.name, "Kartoffeln")

    def test_menge_darf_geleert_werden(self):
        e = self._eintrag("Kartoffeln", "2 kg")
        self._update(e, menge="")
        e.refresh_from_db()
        self.assertEqual(e.menge, "")

    def test_unbekannte_kategorie_wird_ignoriert(self):
        e = self._eintrag("Kartoffeln", "2 kg", kategorie="obst_gemuese")
        self._update(e, kategorie="quatsch")
        e.refresh_from_db()
        self.assertEqual(e.kategorie, "obst_gemuese")

    def test_fremder_darf_nicht_bearbeiten(self):
        e = self._eintrag("Kartoffeln", "2 kg")
        self.client.force_login(self.fremder)
        resp = self.client.post(
            reverse("einkaufsliste_update", args=[e.id]),
            data=json.dumps({"menge": "99 kg"}), content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        e.refresh_from_db()
        self.assertEqual(e.menge, "2 kg")


class HandMergeTests(BearbeitenTestBase):
    def test_zwei_posten_zusammenlegen(self):
        a = self._eintrag("Karotten", "6")
        b = self._eintrag("Möhre", "2,5")

        resp = self._merge([a.id, b.id], name="Karotten")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._aktiv().count(), 1)
        self.assertEqual(self._aktiv().first().name, "Karotten")

    def test_menge_wird_automatisch_summiert(self):
        a = self._eintrag("Toast", "500 g")
        b = self._eintrag("Toastbrot", "250 g")

        self._merge([a.id, b.id], name="Toast")
        self.assertEqual(self._aktiv().first().menge, "750 g")

    def test_eigene_menge_schlaegt_die_summe(self):
        a = self._eintrag("Gurke", "40 Scheiben")
        b = self._eintrag("Gurke", "2")

        self._merge([a.id, b.id], name="Gurke", menge="4 Stück")
        self.assertEqual(self._aktiv().first().menge, "4 Stück")

    def test_ergebnis_gilt_als_manuell(self):
        a = self._eintrag("Karotten", "6", quelle="rezept")
        b = self._eintrag("Möhre", "2,5", quelle="standard")

        self._merge([a.id, b.id], name="Karotten")
        self.assertEqual(self._aktiv().first().quelle, "manuell")

    def test_herkunft_bleibt_nachvollziehbar(self):
        a = self._eintrag("Karotten", "6")
        b = self._eintrag("Möhre", "2,5")

        self._merge([a.id, b.id], name="Karotten")
        self.assertIn("Möhre", self._aktiv().first().rezept_info)

    def test_erledigtes_bleibt_erledigt(self):
        a = self._eintrag("Karotten", "6", erledigt=True)
        b = self._eintrag("Möhre", "2,5")

        self._merge([a.id, b.id], name="Karotten")
        self.assertTrue(self._aktiv().first().erledigt)

    def test_snapshot_erlaubt_das_zuruecknehmen(self):
        a = self._eintrag("Karotten", "6")
        b = self._eintrag("Möhre", "2,5")
        self._merge([a.id, b.id], name="Karotten")
        self.assertEqual(EinkaufslistenSnapshot.objects.count(), 1)

        self.client.post(reverse("einkaufsliste_aufraeumen_undo",
                                 args=[self.toern.id, self.boot.id]))
        self.assertEqual(self._aktiv().count(), 2)
        self.assertEqual(
            sorted(self._aktiv().values_list("name", flat=True)), ["Karotten", "Möhre"]
        )

    def test_ein_einzelner_posten_reicht_nicht(self):
        a = self._eintrag("Karotten", "6")
        resp = self._merge([a.id])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._aktiv().count(), 1)

    def test_fremde_ids_werden_nicht_angefasst(self):
        boot2 = Boot.objects.create(name="Zweitboot", typ="Yacht", toern=self.toern)
        a = self._eintrag("Karotten", "6")
        fremd = EinkaufslistenEintrag.objects.create(
            boot=boot2, toern=self.toern, name="Karotten", menge="3",
            kategorie="obst_gemuese", quelle="rezept",
        )
        resp = self._merge([a.id, fremd.id])
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(self._aktiv().count(), 1)
        fremd.refresh_from_db()
        self.assertEqual(fremd.menge, "3")

    def test_fremder_darf_nicht_zusammenlegen(self):
        a = self._eintrag("Karotten", "6")
        b = self._eintrag("Möhre", "2,5")
        self.client.force_login(self.fremder)
        resp = self.client.post(
            reverse("einkaufsliste_merge", args=[self.toern.id, self.boot.id]),
            data=json.dumps({"ids": [a.id, b.id]}), content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(self._aktiv().count(), 2)
