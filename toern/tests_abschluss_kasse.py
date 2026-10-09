"""Tests: Nach dem Abschluss bleibt die Bootskasse erreichbar.

Abgerechnet wird oft erst nach dem Törn — das Boot-Dashboard zeigt dann nur
noch die Kasse, die Navigation führt weiter dorthin, und im Crew-Dashboard
steht die Abschluss-Karte mit Seemeilen, Fotos und dem Weg zur Kasse oben.
"""
from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot, Kabine
from finance.tests_ausgleich import _user
from toern.models import Teilnahme, Toern


class AbschlussKasseTests(TestCase):
    def setUp(self):
        self.anbieter = _user("abk-anbieter@test.de", "Anna")
        start = timezone.now() - timedelta(days=10)
        self.toern = Toern.objects.create(
            titel="Vorbei", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ABGESCHLOSSEN",
            foto_upload_link="https://example.com/upload",
        )
        self.boot = Boot.objects.create(
            name="Alpha", typ="Yacht", toern=self.toern, skipper_meilen=142,
        )
        Kabine.objects.create(boot=self.boot, name="K1", betten=4)
        self.crew = _user("abk-crew@test.de", "Carla")
        self.t_crew = Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt", rolle="crew", boot=self.boot,
        )
        self.client.force_login(self.crew)

    def test_boot_dashboard_zeigt_nur_die_kasse(self):
        resp = self.client.get(reverse("boot_dashboard", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.context["toern_abgeschlossen"])
        self.assertContains(resp, "Der Törn ist abgeschlossen")
        self.assertContains(resp, 'id="tab-kasse" class="space-y-5"')
        self.assertNotContains(resp, 'data-tab="packliste"')

    def test_waehrend_des_toerns_alle_tabs(self):
        self.toern.status = "ZUTEILUNG_FIXIERT"
        self.toern.save()
        resp = self.client.get(reverse("boot_dashboard", args=[self.toern.id]))
        self.assertFalse(resp.context["toern_abgeschlossen"])
        self.assertContains(resp, 'data-tab="packliste"')

    def test_navigation_fuehrt_weiter_zum_boot(self):
        resp = self.client.get(reverse("crew_dashboard", args=[self.toern.id]))
        self.assertEqual(resp.context["nav_boot_toern_id"], self.toern.id)

    def test_laufender_toern_hat_vorrang_in_der_navigation(self):
        start = timezone.now() + timedelta(days=5)
        neu = Toern.objects.create(
            titel="Nächster", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Adria", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        boot = Boot.objects.create(name="Beta", typ="Yacht", toern=neu)
        Teilnahme.objects.create(
            toern=neu, user=self.crew, status="bestaetigt", rolle="crew", boot=boot,
        )
        resp = self.client.get(reverse("crew_dashboard", args=[self.toern.id]))
        self.assertEqual(resp.context["nav_boot_toern_id"], neu.id)

    def test_crew_dashboard_abschluss_karte(self):
        resp = self.client.get(reverse("crew_dashboard", args=[self.toern.id]))
        self.assertContains(resp, "Danke fürs Mitsegeln, Carla!")
        self.assertContains(resp, "142")
        self.assertContains(resp, "https://example.com/upload")
        self.assertContains(resp, f'{reverse("boot_dashboard", args=[self.toern.id])}?tab=kasse')

    def test_individuelle_meilen_haben_vorrang(self):
        self.t_crew.individuelle_meilen = 99
        self.t_crew.save()
        resp = self.client.get(reverse("crew_dashboard", args=[self.toern.id]))
        self.assertContains(resp, "individuell für dich eingetragen")
        self.assertContains(resp, ">99<")
