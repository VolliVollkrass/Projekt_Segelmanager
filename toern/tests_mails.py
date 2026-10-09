"""Tests: Alle automatischen Mails kommen im gemeinsamen Meer-erleben-Design.

Gleiches Layout wie die Rundmail (templates/emails/layout.html): HTML-Teil mit
Logo per URL (nie CID — Brevo kann das nicht), Plaintext als Fallback.
"""
from datetime import timedelta
from unittest import mock

from django.core import mail
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.views import send_verification_email
from boote.models import Boot, Kabine
from finance.tests_ausgleich import _user
from toern import emails
from toern.models import Teilnahme, Toern


def _html(m):
    return next((c for c, t in m.alternatives if t == "text/html"), "")


class MailDesignTests(TestCase):
    def setUp(self):
        self.request = RequestFactory().get("/")
        self.anbieter = _user("mail-anbieter@test.de", "Anna")
        start = timezone.now() + timedelta(days=20)
        self.toern = Toern.objects.create(
            titel="Sommertörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
            foto_upload_link="https://example.com/upload",
        )
        self.boot = Boot.objects.create(name="Alpha", typ="Yacht", toern=self.toern, skipper_meilen=187)
        self.kabine = Kabine.objects.create(boot=self.boot, name="Bug", betten=2)
        self.crew = _user("mail-crew@test.de", "Carla")
        self.t = Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt", rolle="crew",
            boot=self.boot, kabine=self.kabine,
        )

    def assertDesign(self, m, *inhalte):
        html = _html(m)
        self.assertIn("<html", html.lower())
        self.assertIn("Logo_Meer_erleben.png", html)
        self.assertNotIn("cid:", html)
        self.assertIn("#0D9488", html)  # Teal-Akzent des Layouts
        for inhalt in inhalte:
            self.assertIn(inhalt, html)
        # Echte Umlaute statt Ersatzschreibweise
        for alt in ("Toern", "fuer ", "bestaetig"):
            self.assertNotIn(alt, m.body)
            self.assertNotIn(alt, m.subject)

    def test_zuteilung_fixiert(self):
        emails.mail_zuteilung_fixiert(self.t, self.request)
        self.assertDesign(mail.outbox[0], "Hallo Carla,", "Alpha", "Bug", "Zum Crew-Dashboard")

    def test_teilnahme_bestaetigt(self):
        emails.mail_teilnahme_bestaetigt(self.t, self.request)
        self.assertDesign(mail.outbox[0], "Jetzt Daten vervollständigen", f"/toern/{self.toern.id}/daten/")

    def test_daten_erinnerung(self):
        emails.mail_crew_daten_erinnerung(self.crew, self.toern, ["Telefonnummer", "Passnummer"], self.request)
        self.assertDesign(mail.outbox[0], "• Telefonnummer", "• Passnummer")

    def test_abgelehnt(self):
        emails.mail_teilnahme_abgelehnt(self.t, self.request)
        self.assertDesign(mail.outbox[0], "nicht bestätigen")

    def test_abgesagt_an_alle_seiten(self):
        emails.mail_teilnahme_abgesagt(self.t, self.request)
        empfaenger = {m.to[0] for m in mail.outbox}
        self.assertEqual(empfaenger, {self.anbieter.email, self.crew.email})
        for m in mail.outbox:
            self.assertDesign(m)

    def test_toern_abgeschlossen(self):
        emails.mail_toern_abgeschlossen(self.toern, [self.t], self.request)
        self.assertDesign(
            mail.outbox[0], "187 sm", "Deine gesegelten Seemeilen",
            "https://example.com/upload", "Zur Bootskasse",
        )
        self.assertIn(f"/toern/{self.toern.id}/boot/?tab=kasse", mail.outbox[0].body)

    def test_email_bestaetigung(self):
        send_verification_email(self.crew, self.request)
        self.assertDesign(mail.outbox[0], "E-Mail-Adresse bestätigen", "/accounts/email-verifizieren/")

    def test_passwort_reset(self):
        self.client.post(reverse("password_reset"), {"email": self.crew.email})
        self.assertEqual(len(mail.outbox), 1)
        html = _html(mail.outbox[0])
        self.assertIn("Logo_Meer_erleben.png", html)
        self.assertIn("Neues Passwort vergeben", html)
        self.assertIn("/accounts/passwort-reset/", html)

    def test_versandfehler_bricht_nicht_ab_wird_aber_geloggt(self):
        with mock.patch("django.core.mail.EmailMultiAlternatives.send", side_effect=RuntimeError("Brevo down")), \
                self.assertLogs("toern.emails", level="ERROR"):
            emails.mail_teilnahme_abgelehnt(self.t, self.request)
