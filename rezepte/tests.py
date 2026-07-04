"""Tests für die Rezept-Mengen-Skalierung (Einzel-PDF + gemeinsames Modul)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from utils.rezept_skalierung import skaliere_menge
from .models import Rezept, RezeptZutat

User = get_user_model()


class SkaliereMengeTests(TestCase):
    def test_einfache_zahl(self):
        self.assertEqual(skaliere_menge("250g", 2), "500g")
        self.assertEqual(skaliere_menge("0,5 Zitrone", 2), "1 Zitrone")

    def test_bereich(self):
        self.assertEqual(skaliere_menge("2-3 EL", 2), "4–6 EL")

    def test_ca_praefix(self):
        self.assertEqual(skaliere_menge("ca. 1 kg", 1.5), "ca. 1,5 kg")

    def test_unicode_bruch(self):
        self.assertEqual(skaliere_menge("½ Bund", 2), "1 Bund")
        self.assertEqual(skaliere_menge("1½ EL", 2), "3 EL")

    def test_ascii_bruch(self):
        self.assertEqual(skaliere_menge("1/2 TL", 2), "1 TL")

    def test_nicht_parsebar_bleibt(self):
        self.assertEqual(skaliere_menge("nach Belieben", 2), "nach Belieben")
        self.assertEqual(skaliere_menge("etwas", 3), "etwas")

    def test_faktor_1_unveraendert(self):
        self.assertEqual(skaliere_menge("ca. 1 kg", 1), "ca. 1 kg")

    def test_leer(self):
        self.assertEqual(skaliere_menge("", 2), "")
        self.assertEqual(skaliere_menge(None, 2), "")


class RezeptPdfSkalierungTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(
            email="koch@test.de", username="koch@test.de", email_verified=True
        )
        self.rezept = Rezept.objects.create(
            name="Testgericht", autor=self.user, portionen=4,
        )
        RezeptZutat.objects.create(rezept=self.rezept, name="Wassermelone", menge="ca. 1 kg", order=1)
        RezeptZutat.objects.create(rezept=self.rezept, name="Minze", menge="½ Bund", order=2)

    def test_pdf_mit_personen_skaliert(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse("rezept_pdf", args=[self.rezept.pk]), {"personen": 8})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))
