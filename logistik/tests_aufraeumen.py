"""Tests für das Zusammenführen von Dubletten — und vor allem für den Rückweg."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from logistik.models import EinkaufslistenEintrag, EinkaufslistenSnapshot
from toern.models import Teilnahme, Toern

User = get_user_model()


def _user(email, **extra):
    return User.objects.create(email=email, username=email, email_verified=True, **extra)


class AufraeumenTestBase(TestCase):
    def setUp(self):
        self.anbieter = _user("auf-anbieter@test.de")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)
        self.boot2 = Boot.objects.create(name="Zweitboot", typ="Yacht", toern=self.toern)
        self.skipper = _user("auf-skipper@test.de", first_name="Svea")
        self.t_skipper = Teilnahme.objects.create(
            toern=self.toern, user=self.skipper, status="bestaetigt",
            rolle="skipper", boot=self.boot,
        )
        self.fremder = _user("auf-fremd@test.de")

    def _eintrag(self, name, menge="", boot=None, **extra):
        return EinkaufslistenEintrag.objects.create(
            boot=boot or self.boot, toern=self.toern, name=name, menge=menge,
            kategorie=extra.pop("kategorie", "sonstiges"),
            quelle=extra.pop("quelle", "rezept"), **extra,
        )

    def _aktiv(self, boot=None):
        return EinkaufslistenEintrag.objects.filter(
            boot=boot or self.boot, toern=self.toern, archiviert=False
        )

    def _url(self, name, boot=None):
        return reverse(name, args=[self.toern.id, (boot or self.boot).id])

    def _vorschau(self):
        self.client.force_login(self.skipper)
        return json.loads(self.client.get(self._url("einkaufsliste_aufraeumen_vorschau")).content)

    def _aufraeumen(self):
        self.client.force_login(self.skipper)
        return json.loads(self.client.post(self._url("einkaufsliste_aufraeumen")).content)

    def _undo(self):
        self.client.force_login(self.skipper)
        return self.client.post(self._url("einkaufsliste_aufraeumen_undo"))


class VorschauTests(AufraeumenTestBase):
    def test_vorschau_aendert_nichts(self):
        self._eintrag("Kartoffeln", "1000 g")
        self._eintrag("Kartoffeln (klein gewürfelt)", "500 g")

        d = self._vorschau()
        self.assertEqual(len(d["gruppen"]), 1)
        self.assertEqual(d["zeilen_vorher"], 2)
        self.assertEqual(d["zeilen_nachher"], 1)
        # Datenbank unberührt
        self.assertEqual(self._aktiv().count(), 2)

    def test_vorschau_nennt_die_betroffenen_zeilen(self):
        self._eintrag("Salami", "500 g", quelle="standard")
        self._eintrag("Salami", "30 Scheiben", quelle="rezept")

        gruppe = self._vorschau()["gruppen"][0]
        self.assertEqual(gruppe["name"], "Salami")
        self.assertEqual(gruppe["anzahl"], 2)
        self.assertIn("500 g", gruppe["menge"])
        self.assertIn("30 Scheiben", gruppe["menge"])

    def test_saubere_liste_ergibt_keine_gruppen(self):
        self._eintrag("Brot")
        self._eintrag("Käse")
        self.assertEqual(self._vorschau()["gruppen"], [])


class ZusammenfuehrenTests(AufraeumenTestBase):
    def test_mengen_werden_summiert(self):
        self._eintrag("Butter", "250g")
        self._eintrag("Butter", "450 g")

        self._aufraeumen()
        self.assertEqual(self._aktiv().count(), 1)
        self.assertEqual(self._aktiv().first().menge, "700 g")

    def test_unterschiedliche_einheiten_bleiben_nebeneinander(self):
        """Scheiben lassen sich nicht in Gramm umrechnen — dann muss beides
        stehen bleiben, statt eine Angabe stillschweigend zu verlieren."""
        self._eintrag("Salami", "30 Scheiben")
        self._eintrag("Salami", "500g")

        self._aufraeumen()
        menge = self._aktiv().first().menge
        self.assertIn("30 Scheiben", menge)
        self.assertIn("500 g", menge)

    def test_kuerzester_name_bleibt_varianten_werden_vermerkt(self):
        self._eintrag("Kartoffeln (klein gewürfelt)", "500 g")
        self._eintrag("Kartoffeln", "1000 g")

        self._aufraeumen()
        eintrag = self._aktiv().first()
        self.assertEqual(eintrag.name, "Kartoffeln")
        self.assertIn("Kartoffeln (klein gewürfelt)", eintrag.rezept_info)

    def test_erledigtes_bleibt_erledigt(self):
        """Was schon im Einkaufswagen liegt, darf nicht wieder offen sein."""
        self._eintrag("Gurke", "2", erledigt=True, erledigt_von=self.skipper)
        self._eintrag("Gurke", "40 Scheiben")

        self._aufraeumen()
        self.assertTrue(self._aktiv().first().erledigt)

    def test_manueller_eintrag_setzt_sich_als_quelle_durch(self):
        """Sonst würde der zusammengeführte Posten beim nächsten Generieren
        gelöscht, obwohl ihn jemand von Hand erfasst hat."""
        self._eintrag("Hummus", "2", quelle="rezept")
        self._eintrag("Hummus", "1 Becher", quelle="manuell")

        self._aufraeumen()
        self.assertEqual(self._aktiv().first().quelle, "manuell")

    def test_anderes_boot_bleibt_unberuehrt(self):
        self._eintrag("Butter", "250 g")
        self._eintrag("Butter", "450 g")
        self._eintrag("Butter", "100 g", boot=self.boot2)
        self._eintrag("Butter", "200 g", boot=self.boot2)

        self._aufraeumen()
        self.assertEqual(self._aktiv().count(), 1)
        self.assertEqual(self._aktiv(self.boot2).count(), 2)

    def test_archiviertes_wird_nicht_angefasst(self):
        self._eintrag("Wasser", "30 l")
        self._eintrag("Wasser", "20 l")
        self._eintrag("Wasser", "10 l", archiviert=True)

        self._aufraeumen()
        self.assertEqual(self._aktiv().count(), 1)
        self.assertEqual(
            EinkaufslistenEintrag.objects.filter(
                boot=self.boot, toern=self.toern, archiviert=True
            ).count(), 1
        )

    def test_ohne_dubletten_passiert_nichts_und_kein_snapshot(self):
        self._eintrag("Brot")
        d = self._aufraeumen()
        self.assertEqual(d["zusammengefuehrt"], 0)
        self.assertEqual(EinkaufslistenSnapshot.objects.count(), 0)


class SicherheitsnetzTests(AufraeumenTestBase):
    """Der Rückweg ist der Kern: auf dem Törn darf nichts verlorengehen."""

    def _liste(self):
        return sorted(
            (e.name, e.menge, e.kategorie, e.quelle, e.erledigt)
            for e in self._aktiv()
        )

    def test_snapshot_wird_vor_der_aenderung_angelegt(self):
        self._eintrag("Butter", "250 g")
        self._eintrag("Butter", "450 g")

        self._aufraeumen()
        snapshot = EinkaufslistenSnapshot.objects.get()
        self.assertEqual(len(snapshot.daten), 2)
        self.assertEqual(snapshot.erstellt_von, self.skipper)

    def test_undo_stellt_die_liste_exakt_wieder_her(self):
        self._eintrag("Butter", "250g", kategorie="milch_kase", quelle="standard")
        self._eintrag("Butter", "450 g", kategorie="milch_kase", quelle="rezept")
        self._eintrag("Kartoffeln", "1 kg", kategorie="obst_gemuese")
        self._eintrag("Kartoffeln (gewürfelt)", "500 g", kategorie="obst_gemuese")
        self._eintrag("Brot", "2 Stück", kategorie="brot", erledigt=True)
        vorher = self._liste()

        self._aufraeumen()
        self.assertEqual(self._aktiv().count(), 3)

        resp = self._undo()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._aktiv().count(), 5)
        self.assertEqual(self._liste(), vorher)

    def test_undo_stellt_auch_erledigt_und_einkaeufer_wieder_her(self):
        self._eintrag("Gurke", "2", erledigt=True, erledigt_von=self.skipper,
                      einkaufer=self.t_skipper)
        self._eintrag("Gurke", "40 Scheiben")

        self._aufraeumen()
        self._undo()

        zeilen = {e.menge: e for e in self._aktiv()}
        self.assertTrue(zeilen["2"].erledigt)
        self.assertEqual(zeilen["2"].erledigt_von, self.skipper)
        self.assertEqual(zeilen["2"].einkaufer, self.t_skipper)
        self.assertFalse(zeilen["40 Scheiben"].erledigt)

    def test_undo_ist_nur_einmal_moeglich(self):
        self._eintrag("Butter", "250 g")
        self._eintrag("Butter", "450 g")
        self._aufraeumen()

        self.assertEqual(self._undo().status_code, 200)
        self.assertEqual(self._undo().status_code, 404)

    def test_undo_ohne_snapshot_gibt_404(self):
        self._eintrag("Brot")
        self.assertEqual(self._undo().status_code, 404)

    def test_undo_laesst_anderes_boot_in_ruhe(self):
        self._eintrag("Butter", "250 g")
        self._eintrag("Butter", "450 g")
        self._eintrag("Milch", "1 l", boot=self.boot2)
        self._aufraeumen()
        self._undo()

        self.assertEqual(self._aktiv(self.boot2).count(), 1)


class RechteTests(AufraeumenTestBase):
    def test_fremder_darf_nicht_aufraeumen(self):
        self._eintrag("Butter", "250 g")
        self._eintrag("Butter", "450 g")
        self.client.force_login(self.fremder)

        self.assertEqual(self.client.get(self._url("einkaufsliste_aufraeumen_vorschau")).status_code, 403)
        self.assertEqual(self.client.post(self._url("einkaufsliste_aufraeumen")).status_code, 403)
        self.assertEqual(self.client.post(self._url("einkaufsliste_aufraeumen_undo")).status_code, 403)
        self.assertEqual(self._aktiv().count(), 2)

    def test_get_auf_aufraeumen_ist_nicht_erlaubt(self):
        self.client.force_login(self.skipper)
        self.assertEqual(self.client.get(self._url("einkaufsliste_aufraeumen")).status_code, 405)
