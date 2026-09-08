from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from toern.models import Teilnahme, Toern
from . import markup
from .models import BriefingBaustein

User = get_user_model()


def _user(email):
    return User.objects.create(email=email, username=email, email_verified=True)


class MarkupParserTests(TestCase):
    def test_absatz_ohne_praefix(self):
        bloecke = markup.parse("Nur ein Satz.")
        self.assertEqual(bloecke, [{"typ": markup.ABSATZ, "zeilen": ["Nur ein Satz."]}])

    def test_leerzeile_trennt_absaetze(self):
        bloecke = markup.parse("Erster.\n\nZweiter.")
        self.assertEqual(len(bloecke), 2)
        self.assertTrue(all(b["typ"] == markup.ABSATZ for b in bloecke))

    def test_gleiche_praefixe_werden_zusammengefasst(self):
        bloecke = markup.parse("! Erste Warnung\n! Zweite Zeile")
        self.assertEqual(len(bloecke), 1)
        self.assertEqual(bloecke[0]["typ"], markup.WARNUNG)
        self.assertEqual(bloecke[0]["zeilen"], ["Erste Warnung", "Zweite Zeile"])

    def test_wechsel_des_praefix_beginnt_neuen_block(self):
        typen = [b["typ"] for b in markup.parse("! Warnung\n> Hinweis\n* Merksatz")]
        self.assertEqual(typen, [markup.WARNUNG, markup.HINWEIS, markup.MERKSATZ])

    def test_liste_und_tabelle(self):
        bloecke = markup.parse("- Eins\n- Zwei\n\n| A | B |\n| 1 | 2 |")
        self.assertEqual(bloecke[0], {"typ": markup.LISTE, "punkte": ["Eins", "Zwei"]})
        self.assertEqual(bloecke[1]["zeilen"], [["A", "B"], ["1", "2"]])

    def test_praefix_nur_am_zeilenanfang(self):
        """Ein ! mitten im Satz darf keine Warnbox erzeugen."""
        bloecke = markup.parse("Das ist wichtig! Wirklich.")
        self.assertEqual(bloecke[0]["typ"], markup.ABSATZ)

    def test_leerer_text(self):
        self.assertEqual(markup.parse(""), [])
        self.assertEqual(markup.parse(None), [])

    def test_html_wird_escaped(self):
        """Baustein-Text landet mit |safe im Template — er muss hier escaped werden."""
        html = markup.als_html('<script>alert("x")</script>')
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)

    def test_html_escaping_auch_in_tabellen(self):
        html = markup.als_html("| <b>A</b> | B |")
        self.assertNotIn("<b>A</b>", html)
        self.assertIn("&lt;b&gt;", html)


class BriefingZugriffTests(TestCase):
    """Die Bibliothek ist Skippern vorbehalten — Crew darf sie nicht sehen."""

    def setUp(self):
        self.skipper = _user("skipper@example.test")
        self.crew = _user("crew@example.test")
        toern = Toern.objects.create(
            titel="T", anbieter=self.skipper,
            startdatum="2026-01-01T10:00:00Z", enddatum="2026-01-08T10:00:00Z",
            revier="Test", preis_pro_person=1,
        )
        Teilnahme.objects.create(user=self.skipper, toern=toern, rolle="skipper", status="bestaetigt")
        Teilnahme.objects.create(user=self.crew, toern=toern, rolle="crew", status="bestaetigt")

    def test_skipper_sieht_bibliothek(self):
        self.client.force_login(self.skipper)
        self.assertEqual(self.client.get(reverse("briefing_bibliothek")).status_code, 200)

    def test_crew_sieht_bibliothek_nicht(self):
        self.client.force_login(self.crew)
        self.assertEqual(self.client.get(reverse("briefing_bibliothek")).status_code, 403)

    def test_vorschau_rendert_markup(self):
        self.client.force_login(self.skipper)
        r = self.client.post(reverse("briefing_vorschau"),
                             data='{"text": "! Achtung"}', content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("Warnung", r.json()["html"])

    def test_vorschau_fuer_crew_gesperrt(self):
        self.client.force_login(self.crew)
        r = self.client.post(reverse("briefing_vorschau"),
                             data='{"text": "x"}', content_type="application/json")
        self.assertEqual(r.status_code, 403)

    def test_jeder_skipper_darf_fremden_baustein_bearbeiten(self):
        """Kollaboratives Bearbeiten: nicht nur der Autor."""
        fremd = _user("autor@example.test")
        baustein = BriefingBaustein.objects.create(titel="Alt", text="Alt", autor=fremd)
        self.client.force_login(self.skipper)
        r = self.client.post(
            reverse("briefing_baustein_bearbeiten", args=[baustein.pk]),
            {"titel": "Neu", "kategorie": "sonstiges", "text": "Neuer Text"},
        )
        self.assertEqual(r.status_code, 302)
        baustein.refresh_from_db()
        self.assertEqual(baustein.titel, "Neu")
        self.assertEqual(baustein.autor, fremd)                      # Autor bleibt
        self.assertEqual(baustein.zuletzt_bearbeitet_von, self.skipper)

    def test_nur_autor_darf_loeschen(self):
        fremd = _user("autor2@example.test")
        baustein = BriefingBaustein.objects.create(titel="X", text="X", autor=fremd)
        self.client.force_login(self.skipper)
        r = self.client.post(reverse("briefing_baustein_loeschen", args=[baustein.pk]))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(BriefingBaustein.objects.filter(pk=baustein.pk).exists())
