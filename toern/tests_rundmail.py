"""Tests für die Skipper-Rundmail (Vortreffen-Mail, .ics, Bausteine, KI, Archiv)."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot, Kabine
from .models import Toern, Teilnahme, Rundmail
from .rundmail_utils import render_platzhalter, build_ics

User = get_user_model()


def _user(email, vorname="", nachname="", verified=True):
    return User.objects.create(
        email=email, username=email, first_name=vorname,
        last_name=nachname, email_verified=verified,
    )


class RundmailTestBase(TestCase):
    def setUp(self):
        anbieter_gruppe, _ = Group.objects.get_or_create(name="Anbieter")
        self.anbieter = _user("anbieter@test.de", "Anke", "Anbieter")
        self.anbieter.groups.add(anbieter_gruppe)
        self.skipper = _user("skipper@test.de", "Skip", "Perkins")
        self.crew1 = _user("crew1@test.de", "Max", "Mustermann")
        self.crew2 = _user("crew2@test.de", "Erika", "Musterfrau")
        self.crew_unverif = _user("crew3@test.de", "Ohne", "Mail", verified=False)
        self.fremd = _user("fremd@test.de", "Fremd", "Ling")

        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Sommertörn Ostsee", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Aurora", typ="Bavaria 46", toern=self.toern)
        self.kabine = Kabine.objects.create(boot=self.boot, name="Bug-Kabine")

        Teilnahme.objects.create(toern=self.toern, user=self.skipper, status="bestaetigt", rolle="skipper", boot=self.boot)
        self.t_crew1 = Teilnahme.objects.create(toern=self.toern, user=self.crew1, status="bestaetigt", rolle="crew", boot=self.boot, kabine=self.kabine)
        self.t_crew2 = Teilnahme.objects.create(toern=self.toern, user=self.crew2, status="angemeldet", rolle="crew", boot=self.boot)
        self.t_unverif = Teilnahme.objects.create(toern=self.toern, user=self.crew_unverif, status="bestaetigt", rolle="crew", boot=self.boot)


class PlatzhalterTests(RundmailTestBase):
    def test_bausteine_werden_ersetzt(self):
        text = "Hallo {{vorname}}, dein Boot ist {{boot}}, Kabine {{kabine}}. Törn: {{toern}}. Gruß {{skipper}}"
        out = render_platzhalter(text, self.t_crew1, absender=self.skipper)
        self.assertIn("Hallo Max,", out)
        self.assertIn("Boot ist Aurora", out)
        self.assertIn("Kabine Bug-Kabine", out)
        self.assertIn("Sommertörn Ostsee", out)
        self.assertIn("Gruß Skip", out)
        self.assertNotIn("{{", out)

    def test_leere_werte_hinterlassen_keine_reste(self):
        text = "Boot: {{boot}}|Kabine: {{kabine}}"
        out = render_platzhalter(text, self.t_crew2, absender=self.skipper)
        self.assertEqual(out, "Boot: Aurora|Kabine: ")


class IcsTests(RundmailTestBase):
    def test_build_ics_enthaelt_termin_und_alarm(self):
        start = timezone.now() + timedelta(days=5)
        rm = Rundmail(
            toern=self.toern, absender=self.skipper, betreff="Vortreffen", text="…",
            meeting_link="https://teams.microsoft.com/l/xyz",
            termin_start=start, termin_ende=start + timedelta(hours=1),
            termin_titel="Digitales Vortreffen", termin_ort="Online",
        )
        ics = build_ics(rm, organisator_email=self.skipper.email)
        self.assertIn("BEGIN:VEVENT", ics)
        self.assertIn("SUMMARY:Digitales Vortreffen", ics)
        self.assertIn("BEGIN:VALARM", ics)
        self.assertIn("TRIGGER:-PT1H", ics)
        self.assertIn("teams.microsoft.com", ics)
        self.assertTrue(ics.endswith("\r\n"))

    def test_ohne_termin_kein_ics(self):
        rm = Rundmail(toern=self.toern, betreff="x", text="y")
        self.assertIsNone(build_ics(rm))


class RundmailVersandTests(RundmailTestBase):
    def _url(self):
        return reverse("rundmail_senden", args=[self.toern.id])

    def test_skipper_kann_senden_mit_kopie(self):
        self.client.force_login(self.skipper)
        resp = self.client.post(self._url(), {
            "aktion": "senden",
            "betreff": "Vortreffen {{vorname}}",
            "text": "Hallo {{vorname}}, wir treffen uns digital.",
            "meeting_link": "https://zoom.us/j/123",
            "empfaenger": [self.t_crew1.id, self.t_crew2.id],
        })
        self.assertEqual(resp.status_code, 302)
        # 2 Crew + 1 Kopie an Skipper
        self.assertEqual(len(mail.outbox), 3)
        empfaenger_adr = {m.to[0] for m in mail.outbox}
        self.assertEqual(empfaenger_adr, {"crew1@test.de", "crew2@test.de", "skipper@test.de"})
        # Personalisierung
        crew1_mail = next(m for m in mail.outbox if m.to == ["crew1@test.de"])
        self.assertIn("Hallo Max,", crew1_mail.body)
        self.assertEqual(crew1_mail.subject, "Vortreffen Max")
        # Reply-To zeigt auf den Skipper
        self.assertEqual(crew1_mail.reply_to, ["skipper@test.de"])
        # Archiv-Eintrag
        rm = Rundmail.objects.get(toern=self.toern)
        self.assertEqual(rm.status, "gesendet")
        self.assertEqual(rm.empfaenger_count, 2)

    def test_unverifizierte_erhalten_keine_mail(self):
        self.client.force_login(self.skipper)
        self.client.post(self._url(), {
            "aktion": "senden", "betreff": "Test", "text": "Hi {{vorname}}",
            "empfaenger": [self.t_crew1.id, self.t_unverif.id],
        })
        adressen = {m.to[0] for m in mail.outbox}
        self.assertNotIn("crew3@test.de", adressen)
        rm = Rundmail.objects.get(toern=self.toern)
        self.assertEqual(rm.empfaenger_count, 1)

    def test_termin_haengt_als_ics_an(self):
        self.client.force_login(self.skipper)
        start = (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(self._url(), {
            "aktion": "senden", "betreff": "Vortreffen", "text": "Hallo {{vorname}}",
            "termin_start": start, "termin_titel": "Vortreffen", "termin_ort": "Online",
            "empfaenger": [self.t_crew1.id],
        })
        m = mail.outbox[0]
        # Nur echte Datei-Anhänge (Tupel) prüfen – das Inline-Logo ist ein MIMEImage-Objekt.
        namen = [a[0] for a in m.attachments if isinstance(a, tuple)]
        self.assertIn("Termin.ics", namen)

    def test_html_variante_mit_logo_und_ohne_utf8_reste(self):
        self.client.force_login(self.skipper)
        start = (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M")
        self.client.post(self._url(), {
            "aktion": "senden", "betreff": "Vortreffen", "text": "Hallo {{vorname}}",
            "termin_start": start, "termin_titel": "Vortreffen", "termin_ort": "Online",
            "empfaenger": [self.t_crew1.id],
        })
        m = mail.outbox[0]
        # HTML-Alternative vorhanden, referenziert das Inline-Logo per cid
        html = next((c for c, t in m.alternatives if t == "text/html"), "")
        self.assertIn("<html", html.lower())
        self.assertIn("cid:", html)
        # Der technische Hinweis darf NICHT im Plaintext stehen
        self.assertNotIn("haengt als Kalenderdatei", m.body)
        # Saubere Umlaute im Plaintext-Termin (kein 'ae'-Ersatz)
        self.assertNotIn("haengt", m.body)

    def test_entwurf_speichern_versendet_nichts(self):
        self.client.force_login(self.skipper)
        self.client.post(self._url(), {
            "aktion": "entwurf", "betreff": "Entwurf", "text": "wip",
            "empfaenger": [self.t_crew1.id],
        })
        self.assertEqual(len(mail.outbox), 0)
        rm = Rundmail.objects.get(toern=self.toern)
        self.assertEqual(rm.status, "entwurf")

    def test_crew_darf_nicht_senden(self):
        self.client.force_login(self.crew1)
        resp = self.client.post(self._url(), {
            "aktion": "senden", "betreff": "x", "text": "y",
            "empfaenger": [self.t_crew2.id],
        })
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)

    def test_leerer_betreff_sendet_nicht(self):
        self.client.force_login(self.skipper)
        self.client.post(self._url(), {
            "aktion": "senden", "betreff": "", "text": "y",
            "empfaenger": [self.t_crew1.id],
        })
        self.assertEqual(len(mail.outbox), 0)


class RundmailArchivTests(RundmailTestBase):
    def test_dashboard_zeigt_post_tab(self):
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("skipper_dashboard", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Rundmail an die Crew")

    def test_vorlage_get(self):
        rm = Rundmail.objects.create(
            toern=self.toern, absender=self.skipper, betreff="Alt", text="Alter Text",
            meeting_link="https://x.de", status="gesendet",
        )
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("rundmail_vorlage_get", args=[rm.id]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["betreff"], "Alt")
        self.assertEqual(data["meeting_link"], "https://x.de")

    def test_fremder_darf_vorlage_nicht_lesen(self):
        rm = Rundmail.objects.create(toern=self.toern, absender=self.skipper, betreff="Alt", text="x")
        self.client.force_login(self.fremd)
        resp = self.client.get(reverse("rundmail_vorlage_get", args=[rm.id]))
        self.assertEqual(resp.status_code, 403)

    def test_loeschen(self):
        rm = Rundmail.objects.create(toern=self.toern, absender=self.skipper, betreff="Weg", text="x")
        self.client.force_login(self.skipper)
        resp = self.client.post(reverse("rundmail_loeschen", args=[rm.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Rundmail.objects.filter(id=rm.id).exists())


class RundmailKiTests(RundmailTestBase):
    def test_ki_ohne_stichpunkte(self):
        self.client.force_login(self.skipper)
        resp = self.client.post(
            reverse("rundmail_ki_generieren"),
            {"toern_id": self.toern.id, "stichpunkte": ""},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_ki_ohne_berechtigung(self):
        self.client.force_login(self.fremd)
        resp = self.client.post(
            reverse("rundmail_ki_generieren"),
            {"toern_id": self.toern.id, "stichpunkte": "Vortreffen"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 403)
