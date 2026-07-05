"""Tests für Boots-Dokumente (Mayday-/Notrollen-Plakat) und Boot-Bearbeitung durch Skipper."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

import json

from boote.models import Boot
from utils.dokumente import DOKUMENT_DEFAULTS
from .models import (
    Toern, Teilnahme, DokumentVorlage, DokumentEintrag,
    DokumentStandard, DokumentStandardEintrag,
)

User = get_user_model()


def _user(email):
    return User.objects.create(email=email, username=email, email_verified=True)


class DokumenteTestBase(TestCase):
    def setUp(self):
        anbieter_gruppe, _ = Group.objects.get_or_create(name="Anbieter")
        self.anbieter = _user("anbieter@test.de")
        self.anbieter.groups.add(anbieter_gruppe)
        self.skipper = _user("skipper@test.de")
        self.crew = _user("crew@test.de")

        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn",
            anbieter=self.anbieter,
            startdatum=start,
            enddatum=start + timedelta(days=7),
            revier="Ostsee",
            preis_pro_person=500,
            status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(
            name="Testboot", typ="Bavaria 46", toern=self.toern,
            funkrufzeichen="DGXY2", mmsi="211234560",
        )
        Teilnahme.objects.create(
            toern=self.toern, user=self.skipper, status="bestaetigt", rolle="skipper", boot=self.boot
        )
        Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt", rolle="crew", boot=self.boot
        )


class PlakatPdfTests(DokumenteTestBase):
    def test_mayday_pdf_fuer_skipper(self):
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("mayday_plakat_pdf", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_mayday_pdf_ohne_funkdaten_geht_trotzdem(self):
        self.boot.funkrufzeichen = ""
        self.boot.mmsi = ""
        self.boot.save()
        self.client.force_login(self.anbieter)
        resp = self.client.get(reverse("mayday_plakat_pdf", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_notrollen_pdf_fuer_anbieter(self):
        self.client.force_login(self.anbieter)
        resp = self.client.get(reverse("notrollen_plakat_pdf", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_crew_bekommt_403(self):
        self.client.force_login(self.crew)
        self.assertEqual(
            self.client.get(reverse("mayday_plakat_pdf", args=[self.boot.id])).status_code, 403
        )
        self.assertEqual(
            self.client.get(reverse("notrollen_plakat_pdf", args=[self.boot.id])).status_code, 403
        )


class BootUpdateBerechtigungTests(DokumenteTestBase):
    def test_skipper_darf_boot_bearbeiten(self):
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("boot_update", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 200)

    def test_anbieter_darf_boot_bearbeiten(self):
        self.client.force_login(self.anbieter)
        resp = self.client.get(reverse("boot_update", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 200)

    def test_crew_darf_boot_nicht_bearbeiten(self):
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("boot_update", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 403)

    def test_mmsi_validierung(self):
        from boote.forms import BootForm
        form = BootForm(data={"name": "Boot", "typ": "Yacht", "mmsi": "12345"})
        self.assertFalse(form.is_valid())
        self.assertIn("mmsi", form.errors)

        form = BootForm(data={"name": "Boot", "typ": "Yacht", "mmsi": "211234560"})
        self.assertTrue(form.is_valid(), form.errors)


class ChecklistenTests(DokumenteTestBase):
    def test_items_get_erstellt_defaults(self):
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("dokument_items_get", args=[self.toern.id, "ablegen"]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        erwartet = sum(len(items) for _, items in DOKUMENT_DEFAULTS["ablegen"])
        self.assertEqual(len(data["items"]), erwartet)
        sektionen = {i["sektion"] for i in data["items"]}
        self.assertIn("Pantry", sektionen)
        self.assertIn("Auf Deck", sektionen)

    def test_items_get_ungueltiger_typ_400(self):
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("dokument_items_get", args=[self.toern.id, "quatsch"]))
        self.assertEqual(resp.status_code, 400)

    def test_crew_hat_keinen_zugriff(self):
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("dokument_items_get", args=[self.toern.id, "ablegen"]))
        self.assertEqual(resp.status_code, 403)

    def test_item_add_update_delete(self):
        self.client.force_login(self.skipper)
        vorlage_id = self.client.get(
            reverse("dokument_items_get", args=[self.toern.id, "rueckgabe"])
        ).json()["vorlage_id"]

        resp = self.client.post(
            reverse("dokument_item_add", args=[self.toern.id]),
            data=json.dumps({"vorlage_id": vorlage_id, "sektion": "Rückgabe", "text": "WLAN-Router zurückgeben"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        item_id = resp.json()["id"]

        resp = self.client.post(
            reverse("dokument_item_update", args=[self.toern.id, item_id]),
            data=json.dumps({"sektion": "Rückgabe", "text": "Router zurückgeben"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(DokumentEintrag.objects.get(id=item_id).text, "Router zurückgeben")

        resp = self.client.post(reverse("dokument_item_delete", args=[self.toern.id, item_id]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(DokumentEintrag.objects.filter(id=item_id).exists())

    def test_reset_stellt_defaults_wieder_her(self):
        self.client.force_login(self.skipper)
        self.client.get(reverse("dokument_items_get", args=[self.toern.id, "anlegen"]))
        vorlage = DokumentVorlage.objects.get(toern=self.toern, typ="anlegen")
        vorlage.eintraege.all().delete()

        resp = self.client.post(
            reverse("dokument_reset", args=[self.toern.id]),
            data=json.dumps({"typ": "anlegen"}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        erwartet = sum(len(items) for _, items in DOKUMENT_DEFAULTS["anlegen"])
        neue_vorlage = DokumentVorlage.objects.get(toern=self.toern, typ="anlegen")
        self.assertEqual(neue_vorlage.eintraege.count(), erwartet)

    def test_checkliste_pdf_alle_typen(self):
        self.client.force_login(self.skipper)
        for typ in DOKUMENT_DEFAULTS.keys():
            resp = self.client.get(reverse("dokument_checkliste_pdf", args=[self.boot.id, typ]))
            self.assertEqual(resp.status_code, 200, typ)
            self.assertTrue(resp.content.startswith(b"%PDF"), typ)

    def test_checkliste_pdf_crew_403(self):
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("dokument_checkliste_pdf", args=[self.boot.id, "uebernahme"]))
        self.assertEqual(resp.status_code, 403)


class DokumentStandardTests(DokumenteTestBase):
    """Persönliche benannte Standards für die Boots-Checklisten (PR E)."""

    def _speichern(self, user, typ="uebernahme", name="Meine Übernahme", ist_default=False):
        self.client.force_login(user)
        return self.client.post(
            reverse("dok_standard_speichern", args=[self.toern.id]),
            data=json.dumps({"typ": typ, "name": name, "ist_default": ist_default}),
            content_type="application/json",
        )

    def test_speichern_erstellt_standard_mit_eintraegen(self):
        resp = self._speichern(self.skipper)
        self.assertEqual(resp.status_code, 200)
        standard = DokumentStandard.objects.get(user=self.skipper, typ="uebernahme", name="Meine Übernahme")
        vorlage = DokumentVorlage.objects.get(toern=self.toern, typ="uebernahme")
        self.assertEqual(standard.eintraege.count(), vorlage.eintraege.count())
        self.assertGreater(standard.eintraege.count(), 0)

    def test_speichern_ueberschreibt_gleichen_namen(self):
        self._speichern(self.skipper)
        vorlage = DokumentVorlage.objects.get(toern=self.toern, typ="uebernahme")
        vorlage.eintraege.all().delete()
        DokumentEintrag.objects.create(vorlage=vorlage, sektion="Test", text="Nur ein Punkt")
        self._speichern(self.skipper)
        standard = DokumentStandard.objects.get(user=self.skipper, typ="uebernahme", name="Meine Übernahme")
        self.assertEqual(standard.eintraege.count(), 1)
        self.assertEqual(DokumentStandard.objects.filter(user=self.skipper).count(), 1)

    def test_default_ist_exklusiv_pro_typ(self):
        self._speichern(self.skipper, name="A", ist_default=True)
        self._speichern(self.skipper, name="B", ist_default=True)
        defaults = DokumentStandard.objects.filter(user=self.skipper, typ="uebernahme", ist_default=True)
        self.assertEqual(defaults.count(), 1)
        self.assertEqual(defaults.first().name, "B")

    def test_laden_ersetzt_toern_checkliste(self):
        self._speichern(self.skipper)
        standard = DokumentStandard.objects.get(user=self.skipper)
        standard.eintraege.all().delete()
        DokumentStandardEintrag.objects.create(standard=standard, sektion="Eigene", text="Mein Punkt", reihenfolge=0)

        resp = self.client.post(
            reverse("dok_standard_laden", args=[self.toern.id]),
            data=json.dumps({"standard_id": standard.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        vorlage = DokumentVorlage.objects.get(toern=self.toern, typ="uebernahme")
        self.assertEqual(vorlage.eintraege.count(), 1)
        self.assertEqual(vorlage.eintraege.first().text, "Mein Punkt")

    def test_list_liefert_nur_eigene_standards_des_typs(self):
        self._speichern(self.skipper, typ="uebernahme", name="Übernahme-Std")
        self._speichern(self.skipper, typ="rueckgabe", name="Rückgabe-Std")
        self._speichern(self.anbieter, typ="uebernahme", name="Anbieter-Std")

        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("dok_standard_list") + "?typ=uebernahme")
        namen = [s["name"] for s in resp.json()["standards"]]
        self.assertEqual(namen, ["Übernahme-Std"])

    def test_fremder_standard_loeschen_gibt_404(self):
        self._speichern(self.anbieter)
        standard = DokumentStandard.objects.get(user=self.anbieter)
        self.client.force_login(self.skipper)
        resp = self.client.post(reverse("dok_standard_loeschen", args=[standard.id]))
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(DokumentStandard.objects.filter(id=standard.id).exists())

    def test_crew_darf_nicht_speichern(self):
        resp = self._speichern(self.crew)
        self.assertEqual(resp.status_code, 403)

    def test_default_standard_wird_bei_neuem_toern_vererbt(self):
        self._speichern(self.skipper, ist_default=True)
        standard = DokumentStandard.objects.get(user=self.skipper)
        standard.eintraege.all().delete()
        DokumentStandardEintrag.objects.create(standard=standard, sektion="Eigene", text="Vererbt", reihenfolge=0)

        start = timezone.now() + timedelta(days=90)
        toern2 = Toern.objects.create(
            titel="Zweiter Törn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        Teilnahme.objects.create(toern=toern2, user=self.skipper, status="bestaetigt", rolle="skipper")

        resp = self.client.get(reverse("dokument_items_get", args=[toern2.id, "uebernahme"]))
        self.assertEqual(resp.status_code, 200)
        texte = [i["text"] for i in resp.json()["items"]]
        self.assertEqual(texte, ["Vererbt"])

    def test_ohne_default_kommen_statische_inhalte(self):
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("dokument_items_get", args=[self.toern.id, "ablegen"]))
        erwartet = sum(len(items) for _, items in DOKUMENT_DEFAULTS["ablegen"])
        self.assertEqual(len(resp.json()["items"]), erwartet)

    def test_reset_nutzt_statische_defaults_trotz_default_standard(self):
        self._speichern(self.skipper, ist_default=True)
        resp = self.client.post(
            reverse("dokument_reset", args=[self.toern.id]),
            data=json.dumps({"typ": "uebernahme"}),
            content_type="application/json",
        )
        erwartet = sum(len(items) for _, items in DOKUMENT_DEFAULTS["uebernahme"])
        self.assertEqual(len(resp.json()["items"]), erwartet)
