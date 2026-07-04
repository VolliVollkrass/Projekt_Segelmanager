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
