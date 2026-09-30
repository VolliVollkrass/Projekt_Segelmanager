"""Tests: Zahlungswege (PayPal, IBAN, Wero) im Profil und in der Bootskasse.

Die Zahlungsdaten einer Person sieht nur, wer ihr laut „So gleicht ihr aus"
gerade Geld schuldet — nicht die ganze Crew.
"""
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from accounts.forms import AccountEditForm
from accounts.zahlungswege import (
    formatiere_iban,
    normalisiere_iban,
    normalisiere_paypal,
    normalisiere_wero,
    paypal_link,
)
from finance.tests_ausgleich import AusgleichTestBase, _user

# Offizielles Beispiel der Deutschen Bundesbank
GUELTIGE_IBAN = "DE89370400440532013000"


class IbanTests(SimpleTestCase):
    def test_leerzeichen_und_kleinbuchstaben_werden_normalisiert(self):
        self.assertEqual(normalisiere_iban(" de89 3704 0044 0532 0130 00 "), GUELTIGE_IBAN)

    def test_leer_bleibt_leer(self):
        self.assertEqual(normalisiere_iban(""), "")
        self.assertEqual(normalisiere_iban(None), "")

    def test_falsche_pruefziffer_wird_abgelehnt(self):
        with self.assertRaises(ValidationError):
            normalisiere_iban("DE88370400440532013000")

    def test_zahlendreher_wird_erkannt(self):
        with self.assertRaises(ValidationError):
            normalisiere_iban("DE89370400440532010300")

    def test_kein_iban_format(self):
        with self.assertRaises(ValidationError):
            normalisiere_iban("1234567890")

    def test_andere_laender(self):
        self.assertEqual(normalisiere_iban("NL91 ABNA 0417 1643 00"), "NL91ABNA0417164300")
        self.assertEqual(normalisiere_iban("AT61 1904 3002 3457 3201"), "AT611904300234573201")

    def test_formatierung_in_vierergruppen(self):
        self.assertEqual(formatiere_iban(GUELTIGE_IBAN), "DE89 3704 0044 0532 0130 00")


class PaypalTests(SimpleTestCase):
    def test_varianten_werden_zum_namen(self):
        for eingabe in [
            "meinname",
            "@meinname",
            "paypal.me/meinname",
            "https://paypal.me/meinname",
            "https://www.paypal.me/meinname/",
            "https://paypal.me/meinname/20EUR",
        ]:
            with self.subTest(eingabe=eingabe):
                self.assertEqual(normalisiere_paypal(eingabe), "meinname")

    def test_email_bleibt_email(self):
        self.assertEqual(normalisiere_paypal("ich@example.de"), "ich@example.de")

    def test_unsinn_wird_abgelehnt(self):
        with self.assertRaises(ValidationError):
            normalisiere_paypal("mein name!")

    def test_link_mit_betrag(self):
        self.assertEqual(
            paypal_link("meinname", Decimal("18.5")),
            "https://paypal.me/meinname/18.50EUR",
        )

    def test_link_ohne_betrag(self):
        self.assertEqual(paypal_link("meinname"), "https://paypal.me/meinname")

    def test_email_hat_keinen_link(self):
        self.assertIsNone(paypal_link("ich@example.de", Decimal("10")))


class WeroTests(SimpleTestCase):
    def test_telefon_und_email(self):
        self.assertEqual(normalisiere_wero(" +49 171 1234567 "), "+49 171 1234567")
        self.assertEqual(normalisiere_wero("ich@example.de"), "ich@example.de")

    def test_unsinn_wird_abgelehnt(self):
        with self.assertRaises(ValidationError):
            normalisiere_wero("irgendwas")


class ProfilFormularTests(TestCase):
    def setUp(self):
        self.user = _user("zw-form@test.de", "Zora")

    def _form(self, **daten):
        basis = {"identifikationstyp": "pers", "geschlecht": "d"}
        basis.update(daten)
        return AccountEditForm(data=basis, instance=self.user)

    def test_speichert_normalisiert(self):
        form = self._form(
            zahlung_iban="de89 3704 0044 0532 0130 00",
            zahlung_paypal="https://paypal.me/zora",
            zahlung_wero="+49 171 1234567",
            zahlung_kontoinhaber="Zora Z.",
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()
        self.assertEqual(self.user.zahlung_iban, GUELTIGE_IBAN)
        self.assertEqual(self.user.zahlung_paypal, "zora")
        self.assertTrue(self.user.hat_zahlungswege)

    def test_falsche_iban_blockiert_speichern(self):
        form = self._form(zahlung_iban="DE00 1234")
        self.assertFalse(form.is_valid())
        self.assertIn("zahlung_iban", form.errors)

    def test_alles_leer_ist_erlaubt(self):
        form = self._form()
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.user.refresh_from_db()
        self.assertFalse(self.user.hat_zahlungswege)


class SichtbarkeitInBootskasseTests(AusgleichTestBase):
    """Ausgangslage: Hubert und Carla schulden Erika je 30 €."""

    def setUp(self):
        super().setUp()
        self.erika.zahlung_iban = GUELTIGE_IBAN
        self.erika.zahlung_paypal = "erikasegelt"
        self.erika.save()
        # Hubert hat auch eine IBAN — aber niemand schuldet ihm etwas.
        self.hubert.zahlung_iban = "NL91ABNA0417164300"
        self.hubert.save()

    def _html(self, user):
        self.client.force_login(user)
        return self.client.get(
            reverse("boot_dashboard", args=[self.toern.id])
        ).content.decode()

    def test_schuldner_sieht_zahlungswege_des_empfaengers(self):
        html = self._html(self.hubert)
        self.assertIn("DE89 3704 0044 0532 0130 00", html)
        self.assertIn("https://paypal.me/erikasegelt/30.00EUR", html)

    def test_empfaenger_sieht_eigene_daten_nicht_als_zahlungsweg(self):
        html = self._html(self.erika)
        self.assertNotIn("DE89 3704 0044 0532 0130 00", html)

    def test_unbeteiligte_sehen_fremde_iban_nicht(self):
        """Carla schuldet Hubert nichts → seine IBAN taucht bei ihr nicht auf."""
        html = self._html(self.carla)
        self.assertNotIn("NL91 ABNA 0417 1643 00", html)
        self.assertIn("DE89 3704 0044 0532 0130 00", html)

    def test_nach_begleichen_verschwinden_die_daten(self):
        self.client.force_login(self.hubert)
        self.client.post(
            reverse("ausgleich_beglichen", args=[self.toern.id, self.boot.id]),
            {"von": self.t_hubert.id, "an": self.t_erika.id, "betrag": "30.00"},
        )
        self.assertNotIn("DE89 3704 0044 0532 0130 00", self._html(self.hubert))

    def test_hinweis_wenn_nichts_hinterlegt(self):
        self.erika.zahlung_iban = ""
        self.erika.zahlung_paypal = ""
        self.erika.save()
        self.assertIn("Erika hat noch keine Zahlungswege hinterlegt", self._html(self.hubert))
