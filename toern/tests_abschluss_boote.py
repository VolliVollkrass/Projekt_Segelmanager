"""Tests: Seemeilen und Logbuch für alle Boote eintragen.

Skipper, Co-Skipper und Anbieter dürfen im Abschluss-Tab für jedes Boot des
Törns eintragen. Das eigene Boot steht vorn und ist vorausgewählt.
"""
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot, Kabine
from finance.tests_ausgleich import _user
from toern.models import Teilnahme, Toern


class AbschlussAlleBooteTests(TestCase):
    def setUp(self):
        self.anbieter = _user("abb-anbieter@test.de", "Anna")
        start = timezone.now() - timedelta(days=10)
        self.toern = Toern.objects.create(
            titel="Flottille", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Adria", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.alpha = Boot.objects.create(name="Alpha", typ="Yacht", toern=self.toern)
        self.beta = Boot.objects.create(name="Beta", typ="Yacht", toern=self.toern)
        for b in (self.alpha, self.beta):
            Kabine.objects.create(boot=b, name="K1", betten=4)

        def teilnahme(email, vorname, boot, rolle):
            user = _user(email, vorname)
            return user, Teilnahme.objects.create(
                toern=self.toern, user=user, status="bestaetigt", rolle=rolle, boot=boot,
            )

        self.sk_alpha, _ = teilnahme("abb-ska@test.de", "Sven", self.alpha, "skipper")
        self.co_beta, _ = teilnahme("abb-cob@test.de", "Clara", self.beta, "coskipper")
        self.crew_beta, self.t_crew_beta = teilnahme("abb-crew@test.de", "Bernd", self.beta, "crew")

    def _ctx(self, user, query=""):
        self.client.force_login(user)
        return self.client.get(reverse("skipper_dashboard", args=[self.toern.id]) + query).context

    def _speichern(self, user, boot, **daten):
        self.client.force_login(user)
        return self.client.post(reverse("boot_abschluss_update", args=[boot.id]), daten)

    def test_eigenes_boot_zuerst_und_vorausgewaehlt(self):
        ctx = self._ctx(self.co_beta)
        self.assertEqual([e["boot"].name for e in ctx["abschluss_data"]], ["Beta", "Alpha"])
        self.assertTrue(ctx["abschluss_data"][0]["ist_eigenes"])
        self.assertEqual(ctx["abschluss_boot_id"], self.beta.id)

    def test_anderes_boot_per_query_waehlbar(self):
        ctx = self._ctx(self.co_beta, f"?tab=abschluss&boot={self.alpha.id}")
        self.assertEqual(ctx["abschluss_boot_id"], self.alpha.id)

    def test_fremde_boot_id_faellt_auf_eigenes_zurueck(self):
        ctx = self._ctx(self.sk_alpha, "?boot=999999")
        self.assertEqual(ctx["abschluss_boot_id"], self.alpha.id)

    def test_anbieter_sieht_alle_boote(self):
        ctx = self._ctx(self.anbieter)
        self.assertEqual(len(ctx["abschluss_data"]), 2)

    def test_skipper_traegt_fuer_fremdes_boot_ein(self):
        resp = self._speichern(
            self.sk_alpha, self.beta, skipper_meilen="210",
            **{f"individuelle_meilen_{self.t_crew_beta.id}": "150"},
        )
        self.assertRedirects(
            resp,
            f"{reverse('skipper_dashboard', args=[self.toern.id])}?tab=abschluss&boot={self.beta.id}",
            fetch_redirect_response=False,
        )
        self.beta.refresh_from_db()
        self.t_crew_beta.refresh_from_db()
        self.assertEqual(self.beta.skipper_meilen, 210)
        self.assertEqual(self.t_crew_beta.individuelle_meilen, 150)

    def test_coskipper_laedt_logbuch_fuer_fremdes_boot_hoch(self):
        pdf = SimpleUploadedFile("logbuch.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        self._speichern(self.co_beta, self.alpha, skipper_meilen="0", logbuch_pdf=pdf)
        self.alpha.refresh_from_db()
        self.assertTrue(self.alpha.logbuch_pdf)

    def test_crew_darf_nicht(self):
        resp = self._speichern(self.crew_beta, self.beta, skipper_meilen="99")
        self.assertEqual(resp.status_code, 403)
        self.beta.refresh_from_db()
        self.assertEqual(self.beta.skipper_meilen, 0)

    def test_bootsauswahl_wird_angezeigt(self):
        self.client.force_login(self.co_beta)
        resp = self.client.get(reverse("skipper_dashboard", args=[self.toern.id]))
        self.assertContains(resp, "Für welches Boot trägst du ein?")
        self.assertContains(resp, "dein Boot")
