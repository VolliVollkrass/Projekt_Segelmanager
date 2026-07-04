"""Tests für Boots-Dokumente (Mayday-/Notrollen-Plakat) und Boot-Bearbeitung durch Skipper."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from .models import Toern, Teilnahme

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
