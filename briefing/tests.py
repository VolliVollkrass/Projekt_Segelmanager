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

    def test_schritte_werden_nummeriert(self):
        block = markup.parse("# Erst dies\n# Dann das")[0]
        self.assertEqual(block["typ"], markup.SCHRITTE)
        self.assertEqual(block["punkte"], ["Erst dies", "Dann das"])

    def test_schritte_html_ist_nummerierte_liste(self):
        html = markup.als_html("# Erst dies\n# Dann das")
        self.assertIn("<ol", html)
        self.assertIn(">1<", html)
        self.assertIn(">2<", html)

    def test_schritte_und_aufzaehlung_sind_verschieden(self):
        typen = [b["typ"] for b in markup.parse("- Punkt\n# Schritt")]
        self.assertEqual(typen, [markup.LISTE, markup.SCHRITTE])

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


class BriefingAuswahlTests(TestCase):
    """Reihenfolge und Boot-Zuordnung — beides waren Fehler in der ersten Fassung."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from boote.models import Boot
        from toern.models import BriefingAuswahl

        self.skipper = _user("s@example.test")
        self.toern = Toern.objects.create(
            titel="T", anbieter=self.skipper,
            startdatum=timezone.now(), enddatum=timezone.now() + timedelta(days=7),
            revier="R", preis_pro_person=1,
        )
        self.erstes_boot = Boot.objects.create(name="Erstes", toern=self.toern)
        self.mein_boot = Boot.objects.create(name="Meins", toern=self.toern)
        Teilnahme.objects.create(user=self.skipper, toern=self.toern, rolle="skipper",
                                 status="bestaetigt", boot=self.mein_boot)
        self.client.force_login(self.skipper)

    def test_briefing_nennt_das_boot_des_skippers(self):
        """Bei Flotten-Törns nicht einfach das erste Boot des Törns nehmen."""
        from toern.briefing_pdf import briefing_boot
        self.assertEqual(briefing_boot(self.skipper, self.toern), self.mein_boot)

    def test_boot_faellt_zurueck_wenn_keine_zuordnung(self):
        from toern.briefing_pdf import briefing_boot
        gast = _user("gast@example.test")
        self.assertEqual(briefing_boot(gast, self.toern), self.erstes_boot)

    def test_pdf_wird_erzeugt(self):
        r = self.client.get(reverse("briefing_pdf", args=[self.toern.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")

    def test_neuer_baustein_landet_in_seiner_kategorie(self):
        import json
        from toern.models import BriefingAuswahl

        for kat, titel in [("kommunikation", "K"), ("sonstiges", "S")]:
            b = BriefingBaustein.objects.create(titel=titel, text="x", kategorie=kat,
                                                ist_standard=True)
        self.client.get(reverse("briefing_liste", args=[self.toern.id]))  # Auto-Befüllung

        nachzuegler = BriefingBaustein.objects.create(
            titel="Später dazu", text="x", kategorie="kommunikation")
        self.client.post(
            reverse("briefing_baustein_hinzufuegen", args=[self.toern.id]),
            data=json.dumps({"baustein_id": nachzuegler.id}),
            content_type="application/json",
        )

        auswahl = list(BriefingAuswahl.objects.filter(toern=self.toern)
                       .select_related("baustein").order_by("reihenfolge"))
        kategorien = [a.baustein.kategorie for a in auswahl]
        # Der Nachzügler steht bei seiner Kategorie, nicht am Ende der Liste
        index = [a.baustein_id for a in auswahl].index(nachzuegler.id)
        self.assertEqual(kategorien[index], "kommunikation")
        self.assertNotEqual(index, len(auswahl) - 1)

        # und die Kategorie-Blöcke bleiben zusammenhängend
        gesehen = []
        for k in kategorien:
            if k not in gesehen:
                gesehen.append(k)
            else:
                self.assertEqual(gesehen[-1], k, "Kategorie-Block ist zerrissen")


class BildPositionTests(TestCase):
    def test_standardwert_ist_unten(self):
        b = BriefingBaustein.objects.create(titel="X", text="x")
        self.assertEqual(b.bild_position, "unten")

    def test_position_wird_gespeichert(self):
        skipper = _user("p@example.test")
        toern = Toern.objects.create(
            titel="T", anbieter=skipper,
            startdatum="2026-01-01T10:00:00Z", enddatum="2026-01-08T10:00:00Z",
            revier="R", preis_pro_person=1)
        Teilnahme.objects.create(user=skipper, toern=toern, rolle="skipper", status="bestaetigt")
        baustein = BriefingBaustein.objects.create(titel="X", text="x")

        self.client.force_login(skipper)
        self.client.post(
            reverse("briefing_baustein_bearbeiten", args=[baustein.pk]),
            {"titel": "X", "kategorie": "sonstiges", "text": "x", "bild_position": "links"},
        )
        baustein.refresh_from_db()
        self.assertEqual(baustein.bild_position, "links")


class RuecksprungTests(TestCase):
    """Der Zurück-Pfeil soll dahin führen, wo man hergekommen ist —
    inklusive Suche, Filter und Seite der Bibliothek."""

    def setUp(self):
        self.skipper = _user("r@example.test")
        toern = Toern.objects.create(
            titel="T", anbieter=self.skipper,
            startdatum="2026-01-01T10:00:00Z", enddatum="2026-01-08T10:00:00Z",
            revier="R", preis_pro_person=1)
        Teilnahme.objects.create(user=self.skipper, toern=toern, rolle="skipper",
                                 status="bestaetigt")
        self.baustein = BriefingBaustein.objects.create(
            titel="Leinen los", text="x", kategorie="anlegen")
        self.client.force_login(self.skipper)

    def test_liste_gibt_ihren_eigenen_zustand_als_ruecksprung_mit(self):
        r = self.client.get("/briefing/?q=Leinen&kategorie=anlegen")
        html = r.content.decode()
        self.assertIn("next=", html)
        # Suche und Filter stecken im Rücksprungziel
        self.assertIn("q%3DLeinen", html)
        self.assertIn("kategorie%3Danlegen", html)

    def test_detailseite_verlinkt_zurueck_auf_das_ruecksprungziel(self):
        r = self.client.get(
            reverse("briefing_baustein_detail", args=[self.baustein.pk]),
            {"next": "/toern/1/skipper/?tab=briefing"},
        )
        self.assertContains(r, "/toern/1/skipper/?tab=briefing")

    def test_fremde_hosts_werden_als_ruecksprungziel_verworfen(self):
        r = self.client.get(
            reverse("briefing_baustein_detail", args=[self.baustein.pk]),
            {"next": "https://boese.example.com/phish"},
        )
        self.assertNotContains(r, "boese.example.com")
