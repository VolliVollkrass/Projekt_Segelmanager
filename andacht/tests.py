"""Tests für den Andachtsgenerator (PDF-Auslieferung)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Andacht

User = get_user_model()


class AndachtPdfTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            email="andacht@test.de", username="andacht@test.de",
            email_verified=True, is_andacht=True,
        )
        self.andacht = Andacht.objects.create(
            user=self.user, typ="andacht", zielgruppe="erwachsene",
            dauer_minuten=10, thema="Vertrauen", titel="Testandacht",
        )

    def test_pdf_wird_inline_ausgeliefert(self):
        """attachment-Downloads laufen in der iOS-WebApp ins Leere — muss inline sein."""
        self.client.force_login(self.user)
        resp = self.client.get(reverse("andacht_pdf", args=[self.andacht.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))
        self.assertTrue(resp["Content-Disposition"].startswith("inline"))


class AndachtsbuchTests(TestCase):
    """Andachtsbuch: Veröffentlichen-Toggle, Sammelseite mit Suche, Lese-Detailseite, PDF-Zugriff."""

    def setUp(self):
        self.autor = User.objects.create(
            email="autor@test.de", username="autor@test.de",
            email_verified=True, is_andacht=True,
            first_name="Anna", last_name="Autorin",
        )
        self.leser = User.objects.create(
            email="leser@test.de", username="leser@test.de", email_verified=True,
        )
        self.publiziert = Andacht.objects.create(
            user=self.autor, typ="morgen", zielgruppe="erwachsene",
            dauer_minuten=10, thema="Vertrauen", titel="Sturmstillung",
            bibelstelle="Markus 4,35-41", veroeffentlicht=True,
        )
        self.privat = Andacht.objects.create(
            user=self.autor, typ="abend", zielgruppe="erwachsene",
            dauer_minuten=10, thema="Dank", titel="Abendruhe",
        )

    def test_buch_erfordert_login(self):
        resp = self.client.get(reverse("andacht_buch"))
        self.assertEqual(resp.status_code, 302)

    def test_buch_zeigt_nur_veroeffentlichte(self):
        self.client.force_login(self.leser)
        resp = self.client.get(reverse("andacht_buch"))
        self.assertContains(resp, "Sturmstillung")
        self.assertNotContains(resp, "Abendruhe")

    def test_suche_nach_titel_thema_autor(self):
        self.client.force_login(self.leser)
        for begriff in ("Sturm", "Vertrauen", "Autorin", "Markus"):
            resp = self.client.get(reverse("andacht_buch"), {"q": begriff})
            self.assertContains(resp, "Sturmstillung", msg_prefix=f"Suche nach '{begriff}'")
        resp = self.client.get(reverse("andacht_buch"), {"q": "gibtsnicht"})
        self.assertNotContains(resp, "Sturmstillung")

    def test_veroeffentlichen_toggle(self):
        self.client.force_login(self.autor)
        resp = self.client.post(reverse("andacht_veroeffentlichen", args=[self.privat.pk]))
        self.assertEqual(resp.status_code, 302)
        self.privat.refresh_from_db()
        self.assertTrue(self.privat.veroeffentlicht)
        self.assertIsNotNone(self.privat.veroeffentlicht_am)

        self.client.post(reverse("andacht_veroeffentlichen", args=[self.privat.pk]))
        self.privat.refresh_from_db()
        self.assertFalse(self.privat.veroeffentlicht)
        self.assertIsNone(self.privat.veroeffentlicht_am)

    def test_fremde_andacht_nicht_veroeffentlichbar(self):
        fremder = User.objects.create(
            email="fremd@test.de", username="fremd@test.de",
            email_verified=True, is_andacht=True,
        )
        self.client.force_login(fremder)
        resp = self.client.post(reverse("andacht_veroeffentlichen", args=[self.privat.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_veroeffentlichen_erfordert_andacht_recht(self):
        self.client.force_login(self.leser)
        resp = self.client.post(reverse("andacht_veroeffentlichen", args=[self.publiziert.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_buch_detail_fuer_alle_eingeloggten(self):
        self.client.force_login(self.leser)
        resp = self.client.get(reverse("andacht_buch_detail", args=[self.publiziert.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sturmstillung")

    def test_buch_detail_unveroeffentlicht_404_fuer_fremde(self):
        self.client.force_login(self.leser)
        resp = self.client.get(reverse("andacht_buch_detail", args=[self.privat.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_buch_detail_unveroeffentlicht_ok_fuer_autor(self):
        self.client.force_login(self.autor)
        resp = self.client.get(reverse("andacht_buch_detail", args=[self.privat.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_pdf_veroeffentlicht_fuer_alle_eingeloggten(self):
        self.client.force_login(self.leser)
        resp = self.client.get(reverse("andacht_pdf", args=[self.publiziert.pk]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_pdf_unveroeffentlicht_404_fuer_fremde(self):
        self.client.force_login(self.leser)
        resp = self.client.get(reverse("andacht_pdf", args=[self.privat.pk]))
        self.assertEqual(resp.status_code, 404)

    def test_pdf_unveroeffentlicht_ok_fuer_autor(self):
        self.client.force_login(self.autor)
        resp = self.client.get(reverse("andacht_pdf", args=[self.privat.pk]))
        self.assertEqual(resp.status_code, 200)
