"""Tests: Einkaufslisten-Generierung skaliert Rezepte korrekt auf die Boots-Crew."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from logistik.models import Mahlzeit, EinkaufslistenEintrag
from rezepte.models import Rezept, RezeptZutat
from utils.rezept_skalierung import summiere_mengen
from .models import Toern, Teilnahme

User = get_user_model()


def _user(email):
    return User.objects.create(email=email, username=email, email_verified=True)


class EinkaufslisteSkalierungTests(TestCase):
    def setUp(self):
        self.anbieter = _user("anbieter@test.de")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)

        # 10 bestätigte Personen auf dem Boot
        self.crew = []
        for i in range(10):
            u = _user(f"crew{i}@test.de")
            self.crew.append(Teilnahme.objects.create(
                toern=self.toern, user=u, status="bestaetigt", rolle="crew", boot=self.boot
            ))

        # Rezept für 4 Portionen
        self.rezept = Rezept.objects.create(name="Nudeln", autor=self.anbieter, portionen=4)
        RezeptZutat.objects.create(rezept=self.rezept, name="Farfalle", menge="250 g", order=1)
        RezeptZutat.objects.create(rezept=self.rezept, name="Wassermelone", menge="ca. 1 kg", order=2)
        RezeptZutat.objects.create(rezept=self.rezept, name="Minze", menge="½ Bund", order=3)
        RezeptZutat.objects.create(rezept=self.rezept, name="Pfeffer", menge="nach Belieben", order=4)

        self.datum = (start + timedelta(days=1)).date()

    def _generieren(self):
        self.client.force_login(self.crew[0].user)
        return self.client.post(
            reverse("einkaufsliste_generieren", args=[self.toern.id, self.boot.id])
        )

    def _menge(self, zutat_name):
        return EinkaufslistenEintrag.objects.get(
            boot=self.boot, toern=self.toern, name__iexact=zutat_name
        ).menge

    def test_rezept_fuer_4_wird_auf_10_personen_skaliert(self):
        Mahlzeit.objects.create(
            boot=self.boot, toern=self.toern, datum=self.datum,
            typ="abend", name="Nudeln", rezept=self.rezept,
        )
        resp = self._generieren()
        self.assertEqual(resp.status_code, 200)
        # Faktor 10/4 = 2,5
        self.assertEqual(self._menge("Farfalle"), "625 g")
        self.assertEqual(self._menge("Wassermelone"), "ca. 2,5 kg")
        self.assertEqual(self._menge("Minze"), "1,2 Bund")
        self.assertEqual(self._menge("Pfeffer"), "nach Belieben")

    def test_gleiche_zutat_aus_zwei_mahlzeiten_wird_summiert(self):
        for tag in (1, 2):
            Mahlzeit.objects.create(
                boot=self.boot, toern=self.toern,
                datum=(self.toern.startdatum + timedelta(days=tag)).date(),
                typ="abend", name="Nudeln", rezept=self.rezept,
            )
        self._generieren()
        # 2 × 625 g = 1250 g; 2 × ca. 2,5 kg = ca. 5 kg
        self.assertEqual(self._menge("Farfalle"), "1250 g")
        self.assertEqual(self._menge("Wassermelone"), "ca. 5 kg")

    def test_wasser_standard_artikel_nach_crew(self):
        self._generieren()
        self.assertEqual(self._menge("Wasser"), "50 Liter")


class EinkaufsArchivTests(TestCase):
    """Punkt 7: Erledigtes wandert ins Archiv und kommt nicht ungefragt wieder."""

    def setUp(self):
        self.anbieter = _user("anbieter@test.de")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)
        self.skipper = _user("skipper@test.de")
        self.t_skipper = Teilnahme.objects.create(
            toern=self.toern, user=self.skipper, status="bestaetigt", rolle="skipper", boot=self.boot
        )

    def _generieren(self):
        self.client.force_login(self.skipper)
        return self.client.post(
            reverse("einkaufsliste_generieren", args=[self.toern.id, self.boot.id])
        )

    def _aktive(self):
        return EinkaufslistenEintrag.objects.filter(boot=self.boot, toern=self.toern, archiviert=False)

    def _archiv(self):
        return EinkaufslistenEintrag.objects.filter(boot=self.boot, toern=self.toern, archiviert=True)

    def test_erledigtes_wandert_beim_generieren_ins_archiv(self):
        self._generieren()
        wasser = self._aktive().get(name="Wasser")
        wasser.erledigt = True
        wasser.erledigt_von = self.skipper
        wasser.save()

        self._generieren()
        wasser.refresh_from_db()
        self.assertTrue(wasser.archiviert)
        # Wasser wird NICHT erneut auf die aktive Liste gesetzt
        self.assertFalse(self._aktive().filter(name__iexact="Wasser").exists())
        # andere Standard-Artikel sind wieder da
        self.assertTrue(self._aktive().filter(name="Kaffee").exists())

    def test_archivierte_rezept_zutat_wird_nicht_neu_angelegt(self):
        rezept = Rezept.objects.create(name="Nudeln", autor=self.anbieter, portionen=4)
        RezeptZutat.objects.create(rezept=rezept, name="Farfalle", menge="250 g", order=1)
        Mahlzeit.objects.create(
            boot=self.boot, toern=self.toern,
            datum=(self.toern.startdatum + timedelta(days=1)).date(),
            typ="abend", name="Nudeln", rezept=rezept,
        )
        self._generieren()
        farfalle = self._aktive().get(name="Farfalle")
        farfalle.erledigt = True
        farfalle.save()

        self._generieren()
        self.assertFalse(self._aktive().filter(name__iexact="Farfalle").exists())
        self.assertTrue(self._archiv().filter(name="Farfalle").exists())

    def test_offene_eintraege_werden_nicht_archiviert(self):
        self._generieren()
        self._generieren()
        self.assertEqual(self._archiv().count(), 0)
        # keine Duplikate auf der aktiven Liste
        self.assertEqual(self._aktive().filter(name="Wasser").count(), 1)

    def test_manueller_offener_eintrag_ueberlebt_generieren(self):
        EinkaufslistenEintrag.objects.create(
            boot=self.boot, toern=self.toern, name="Sonnenmilch", quelle="manuell"
        )
        self._generieren()
        self.assertTrue(self._aktive().filter(name="Sonnenmilch").exists())

    def test_reaktivieren_erzeugt_neue_aktive_zeile_archiv_bleibt(self):
        self._generieren()
        wasser = self._aktive().get(name="Wasser")
        wasser.erledigt = True
        wasser.save()
        self._generieren()

        archiv_eintrag = self._archiv().get(name="Wasser")
        self.client.force_login(self.skipper)
        resp = self.client.post(reverse("einkaufsliste_reaktivieren", args=[archiv_eintrag.id]))
        self.assertEqual(resp.status_code, 200)

        aktiv = self._aktive().get(name="Wasser")
        self.assertFalse(aktiv.erledigt)
        self.assertEqual(aktiv.quelle, "manuell")  # überlebt weiteres Generieren
        self.assertTrue(self._archiv().filter(id=archiv_eintrag.id).exists())

        # Nächstes Generieren: reaktivierter Eintrag bleibt, kein Duplikat vom Standard
        self._generieren()
        self.assertEqual(self._aktive().filter(name__iexact="Wasser").count(), 1)


class GrundeinkaufVorlageTests(EinkaufsArchivTests):
    """Punkt 8: Grundeinkauf ist pro Törn bearbeitbar + persönlicher Standard."""

    def _vorlage_get(self, als=None):
        self.client.force_login(als or self.skipper)
        return self.client.get(reverse("einkaufsvorlage_get", args=[self.toern.id]))

    def test_vorlage_wird_aus_standard_artikeln_erstellt(self):
        data = self._vorlage_get().json()
        namen = [i["name"] for i in data["items"]]
        self.assertIn("Wasser", namen)
        self.assertIn("Klopapier", namen)

    def test_crew_darf_vorlage_nicht_sehen_oder_aendern(self):
        crew = _user("crew@test.de")
        Teilnahme.objects.create(toern=self.toern, user=crew, status="bestaetigt", rolle="crew", boot=self.boot)
        self.assertEqual(self._vorlage_get(als=crew).status_code, 403)
        resp = self.client.post(
            reverse("einkaufsvorlage_add", args=[self.toern.id]),
            data='{"name": "Hack"}', content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)

    def test_generieren_nutzt_bearbeitete_vorlage(self):
        import json as _json
        data = self._vorlage_get().json()
        wasser = next(i for i in data["items"] if i["name"] == "Wasser")

        # Wasser-Menge ändern, Kaffee löschen, eigenen Artikel ergänzen
        self.client.post(
            reverse("einkaufsvorlage_update", args=[self.toern.id, wasser["id"]]),
            data=_json.dumps({"menge_template": "{crew} Kanister"}),
            content_type="application/json",
        )
        kaffee = next(i for i in data["items"] if i["name"] == "Kaffee")
        self.client.post(reverse("einkaufsvorlage_delete", args=[self.toern.id, kaffee["id"]]))
        self.client.post(
            reverse("einkaufsvorlage_add", args=[self.toern.id]),
            data=_json.dumps({"name": "Grillkohle", "menge_template": "2 Säcke"}),
            content_type="application/json",
        )

        self._generieren()
        self.assertEqual(self._aktive().get(name="Wasser").menge, "1 Kanister")
        self.assertFalse(self._aktive().filter(name="Kaffee").exists())
        self.assertTrue(self._aktive().filter(name="Grillkohle").exists())

    def test_als_standard_speichern_und_neuer_toern_seedet_daraus(self):
        import json as _json
        self._vorlage_get()
        self.client.post(
            reverse("einkaufsvorlage_add", args=[self.toern.id]),
            data=_json.dumps({"name": "Grillkohle", "menge_template": "2 Säcke"}),
            content_type="application/json",
        )
        resp = self.client.post(reverse("einkaufsvorlage_als_standard", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 200)

        # Neuer Törn desselben Skippers → Vorlage kommt aus dem persönlichen Standard
        start = timezone.now() + timedelta(days=60)
        toern2 = Toern.objects.create(
            titel="Törn 2", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        Teilnahme.objects.create(toern=toern2, user=self.skipper, status="bestaetigt", rolle="skipper")
        from .views import _get_or_create_einkaufsvorlage
        vorlage2 = _get_or_create_einkaufsvorlage(toern2, user=self.skipper)
        self.assertTrue(vorlage2.eintraege.filter(name="Grillkohle").exists())


class SummiereMengenTests(TestCase):
    def test_summiert_pro_einheit(self):
        self.assertEqual(summiere_mengen(["250 g", "500 g"]), "750 g")

    def test_ca_wird_uebernommen(self):
        self.assertEqual(summiere_mengen(["ca. 1,5 kg", "1 kg"]), "ca. 2,5 kg")

    def test_brueche_werden_summiert(self):
        self.assertEqual(summiere_mengen(["½ Bund", "½ Bund"]), "1 Bund")

    def test_nicht_parsebares_bleibt_erhalten(self):
        self.assertEqual(summiere_mengen(["nach Belieben", "200 ml"]), "200 ml + nach Belieben")

    def test_verschiedene_einheiten_getrennt(self):
        self.assertEqual(summiere_mengen(["2 EL", "200 ml"]), "2 EL + 200 ml")
