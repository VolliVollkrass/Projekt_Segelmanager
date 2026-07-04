"""Tests für den In-App-PDF-Viewer."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class PdfViewerTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            email="crew@test.de", username="crew@test.de", email_verified=True
        )

    def test_viewer_rendert_mit_gueltigem_pfad(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse("pdf_viewer"),
            {"src": "/toern/boot/1/mayday/pdf/", "titel": "Mayday-Plakat"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Mayday-Plakat")
        self.assertContains(resp, "/toern/boot/1/mayday/pdf/")

    def test_externe_urls_werden_abgelehnt(self):
        self.client.force_login(self.user)
        for src in ("https://evil.example/x.pdf", "//evil.example/x.pdf", "evil", ""):
            resp = self.client.get(reverse("pdf_viewer"), {"src": src})
            self.assertEqual(resp.status_code, 404, src)

    def test_login_erforderlich(self):
        resp = self.client.get(reverse("pdf_viewer"), {"src": "/toern/1/teilnehmerliste/pdf/"})
        self.assertEqual(resp.status_code, 302)

    def test_dateiname_aus_titel_wenn_kein_pdf_pfad(self):
        self.client.force_login(self.user)
        resp = self.client.get(
            reverse("pdf_viewer"),
            {"src": "/toern/5/teilnehmerliste/pdf/", "titel": "Teilnehmerliste Kroatien"},
        )
        self.assertContains(resp, "teilnehmerliste-kroatien.pdf")
