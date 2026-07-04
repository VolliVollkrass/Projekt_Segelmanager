"""Tests für Packlisten: Skipper-Packliste, Vorlagen-Init, add_packitem."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from logistik.models import PersönlicherGegenstand
from utils.packliste import SKIPPER_LISTE
from .models import Toern, Teilnahme, PacklisteVorlage, PacklisteStandard, PacklisteStandardEintrag
from .views import _get_or_create_vorlage

User = get_user_model()


def _user(email):
    return User.objects.create(email=email, username=email, email_verified=True)


def _toern(anbieter, **kwargs):
    start = timezone.now() + timedelta(days=30)
    defaults = dict(
        titel="Testtörn",
        anbieter=anbieter,
        startdatum=start,
        enddatum=start + timedelta(days=7),
        revier="Ostsee",
        preis_pro_person=500,
        status="ZUTEILUNG_FIXIERT",
    )
    defaults.update(kwargs)
    return Toern.objects.create(**defaults)


class PacklisteTestBase(TestCase):
    def setUp(self):
        anbieter_gruppe, _ = Group.objects.get_or_create(name="Anbieter")
        self.anbieter = _user("anbieter@test.de")
        self.anbieter.groups.add(anbieter_gruppe)
        self.skipper = _user("skipper@test.de")
        self.coskipper = _user("coskipper@test.de")
        self.crew = _user("crew@test.de")

        self.toern = _toern(self.anbieter)
        self.boot = Boot.objects.create(name="Testboot", typ="Bavaria 46", toern=self.toern)

        self.t_skipper = Teilnahme.objects.create(
            toern=self.toern, user=self.skipper, status="bestaetigt", rolle="skipper", boot=self.boot
        )
        self.t_coskipper = Teilnahme.objects.create(
            toern=self.toern, user=self.coskipper, status="bestaetigt", rolle="coskipper", boot=self.boot
        )
        self.t_crew = Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt", rolle="crew", boot=self.boot
        )


class SkipperVorlageTests(PacklisteTestBase):
    def test_skipper_vorlage_wird_mit_standardliste_erstellt(self):
        vorlage = _get_or_create_vorlage(self.toern, "skipper")
        namen = set(vorlage.eintraege.values_list("name", flat=True))
        self.assertEqual(namen, {name for name, _ in SKIPPER_LISTE})
        self.assertIn("Chartervertrag", namen)
        self.assertIn("Rettungsweste", namen)

    def test_revier_wechsel_reset_laesst_skipper_vorlage_unangetastet(self):
        vorlage = _get_or_create_vorlage(self.toern, "skipper")
        vorlage.eintraege.create(name="Eigenes Skipper-Item", menge=1)
        self.client.force_login(self.skipper)
        resp = self.client.post(
            reverse("packl_revier_set", args=[self.toern.id]),
            data=json.dumps({"revier_typ": "kalt", "reset": True}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            PacklisteVorlage.objects.get(toern=self.toern, typ="skipper")
            .eintraege.filter(name="Eigenes Skipper-Item").exists()
        )

    def test_vorlage_items_get_akzeptiert_skipper_typ(self):
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("vorlage_items_get", args=[self.toern.id, "skipper"]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(len(data["items"]), len(SKIPPER_LISTE))


class VorlageAnwendenTests(PacklisteTestBase):
    def _anwenden(self, **payload):
        self.client.force_login(self.skipper)
        return self.client.post(
            reverse("vorlage_anwenden", args=[self.toern.id]),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_skipper_liste_geht_nur_an_skipper_und_coskipper(self):
        resp = self._anwenden(apply_personal=False, apply_boot=False, apply_skipper=True)
        self.assertEqual(resp.status_code, 200)

        for t in (self.t_skipper, self.t_coskipper):
            namen = set(t.persoenliche_packliste.filter(ist_skipper=True).values_list("name", flat=True))
            self.assertEqual(namen, {name for name, _ in SKIPPER_LISTE})
        self.assertFalse(self.t_crew.persoenliche_packliste.exists())

    def test_skipper_liste_wird_nicht_doppelt_ergaenzt(self):
        self._anwenden(apply_personal=False, apply_boot=False, apply_skipper=True)
        resp = self._anwenden(apply_personal=False, apply_boot=False, apply_skipper=True)
        self.assertEqual(resp.json()["added"]["skipper"], 0)
        self.assertEqual(
            self.t_skipper.persoenliche_packliste.count(), len(SKIPPER_LISTE)
        )


class BootDashboardInitTests(PacklisteTestBase):
    def test_persoenliche_liste_kommt_aus_kalt_vorlage(self):
        self.toern.packliste_revier_typ = "kalt"
        self.toern.save(update_fields=["packliste_revier_typ"])
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("boot_dashboard", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 200)
        namen = set(self.t_crew.persoenliche_packliste.values_list("name", flat=True))
        self.assertIn("Thermounterwäsche", namen)

    def test_skipper_bekommt_skipper_items_crew_nicht(self):
        self.client.force_login(self.skipper)
        self.client.get(reverse("boot_dashboard", args=[self.toern.id]))
        self.assertTrue(self.t_skipper.persoenliche_packliste.filter(ist_skipper=True, name="Chartervertrag").exists())

        self.client.force_login(self.crew)
        self.client.get(reverse("boot_dashboard", args=[self.toern.id]))
        self.assertFalse(self.t_crew.persoenliche_packliste.filter(ist_skipper=True).exists())

    def test_nicht_bestaetigte_teilnahme_bekommt_keine_liste(self):
        abgelehnt = _user("abgelehnt@test.de")
        t = Teilnahme.objects.create(toern=self.toern, user=abgelehnt, status="abgelehnt", rolle="crew")
        self.client.force_login(abgelehnt)
        resp = self.client.get(reverse("boot_dashboard", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(t.persoenliche_packliste.exists())


class PacklisteStandardTests(PacklisteTestBase):
    def _speichern(self, user, **payload):
        self.client.force_login(user)
        return self.client.post(
            reverse("packl_standard_speichern", args=[self.toern.id]),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_speichern_kopiert_toern_vorlage(self):
        vorlage = _get_or_create_vorlage(self.toern, "skipper")
        vorlage.eintraege.create(name="Extra-Item", menge=3)
        resp = self._speichern(self.skipper, typ="skipper", name="Mein Charter-Set")
        self.assertEqual(resp.status_code, 200)
        standard = PacklisteStandard.objects.get(user=self.skipper, typ="skipper", name="Mein Charter-Set")
        self.assertTrue(standard.eintraege.filter(name="Extra-Item", menge=3).exists())
        self.assertEqual(standard.eintraege.count(), len(SKIPPER_LISTE) + 1)

    def test_speichern_gleicher_name_ueberschreibt(self):
        self._speichern(self.skipper, typ="personal", name="Mittelmeer")
        self._speichern(self.skipper, typ="personal", name="Mittelmeer")
        self.assertEqual(
            PacklisteStandard.objects.filter(user=self.skipper, typ="personal", name="Mittelmeer").count(), 1
        )

    def test_default_ist_exklusiv_pro_typ(self):
        self._speichern(self.skipper, typ="personal", name="A", ist_default=True)
        self._speichern(self.skipper, typ="personal", name="B", ist_default=True)
        defaults = PacklisteStandard.objects.filter(user=self.skipper, typ="personal", ist_default=True)
        self.assertEqual(defaults.count(), 1)
        self.assertEqual(defaults.first().name, "B")

    def test_crew_darf_nicht_speichern(self):
        resp = self._speichern(self.crew, typ="personal", name="Hack")
        self.assertEqual(resp.status_code, 403)

    def test_laden_ersetzt_toern_vorlage(self):
        standard = PacklisteStandard.objects.create(user=self.skipper, typ="personal", name="Minimal")
        PacklisteStandardEintrag.objects.create(standard=standard, name="Zahnbürste", menge=1)
        self.client.force_login(self.skipper)
        resp = self.client.post(
            reverse("packl_standard_laden", args=[self.toern.id]),
            data=json.dumps({"standard_id": standard.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        vorlage = PacklisteVorlage.objects.get(toern=self.toern, typ="personal")
        self.assertEqual(list(vorlage.eintraege.values_list("name", flat=True)), ["Zahnbürste"])

    def test_fremder_standard_laden_404(self):
        fremd = PacklisteStandard.objects.create(user=self.coskipper, typ="personal", name="Fremd")
        self.client.force_login(self.skipper)
        resp = self.client.post(
            reverse("packl_standard_laden", args=[self.toern.id]),
            data=json.dumps({"standard_id": fremd.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 404)

    def test_fremder_standard_loeschen_404(self):
        fremd = PacklisteStandard.objects.create(user=self.coskipper, typ="personal", name="Fremd")
        self.client.force_login(self.skipper)
        resp = self.client.post(reverse("packl_standard_loeschen", args=[fremd.id]))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(PacklisteStandard.objects.filter(id=fremd.id).exists())

    def test_default_standard_wird_bei_neuem_toern_verwendet(self):
        standard = PacklisteStandard.objects.create(
            user=self.skipper, typ="personal", name="Meins", ist_default=True
        )
        PacklisteStandardEintrag.objects.create(standard=standard, name="Lieblingsmesser", menge=1)

        neuer_toern = _toern(self.anbieter, titel="Neuer Törn")
        Teilnahme.objects.create(
            toern=neuer_toern, user=self.skipper, status="bestaetigt", rolle="skipper"
        )
        vorlage = _get_or_create_vorlage(neuer_toern, "personal", user=self.skipper)
        self.assertEqual(list(vorlage.eintraege.values_list("name", flat=True)), ["Lieblingsmesser"])

    def test_default_standard_greift_nicht_fuer_crew(self):
        standard = PacklisteStandard.objects.create(
            user=self.crew, typ="personal", name="Crew-Standard", ist_default=True
        )
        PacklisteStandardEintrag.objects.create(standard=standard, name="Crew-Item", menge=1)

        neuer_toern = _toern(self.anbieter, titel="Neuer Törn 2")
        Teilnahme.objects.create(
            toern=neuer_toern, user=self.crew, status="bestaetigt", rolle="crew"
        )
        vorlage = _get_or_create_vorlage(neuer_toern, "personal", user=self.crew)
        namen = list(vorlage.eintraege.values_list("name", flat=True))
        self.assertNotIn("Crew-Item", namen)
        self.assertIn("Reisepass / Ausweis", namen)

    def test_standard_list_nur_eigene(self):
        PacklisteStandard.objects.create(user=self.skipper, typ="personal", name="Meins")
        PacklisteStandard.objects.create(user=self.coskipper, typ="personal", name="Fremd")
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("packl_standard_list"), {"typ": "personal"})
        namen = [s["name"] for s in resp.json()["standards"]]
        self.assertEqual(namen, ["Meins"])


class AddPackitemTests(PacklisteTestBase):
    def test_add_packitem_liefert_json_response(self):
        self.client.force_login(self.crew)
        resp = self.client.post(
            reverse("add_packitem", args=[self.toern.id]),
            {"name": "Sonnenhut", "menge": 2},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ok")
        self.assertTrue(self.t_crew.persoenliche_packliste.filter(name="Sonnenhut", menge=2).exists())

    def test_add_packitem_ohne_name_400_und_kein_item(self):
        self.client.force_login(self.crew)
        resp = self.client.post(reverse("add_packitem", args=[self.toern.id]), {"name": "  "})
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(self.t_crew.persoenliche_packliste.exists())
