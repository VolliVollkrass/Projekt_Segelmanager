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
    """Auswahl hängt am Boot, nicht am Törn — auf Flottentörns hat jede Crew ihr eigenes."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from boote.models import Boot

        self.skipper = _user("s@example.test")
        self.anderer = _user("s2@example.test")
        self.toern = Toern.objects.create(
            titel="T", anbieter=_user("anbieter@example.test"),
            startdatum=timezone.now(), enddatum=timezone.now() + timedelta(days=7),
            revier="R", preis_pro_person=1,
        )
        self.mein_boot = Boot.objects.create(name="Meins", toern=self.toern)
        self.anderes_boot = Boot.objects.create(name="Anderes", toern=self.toern)
        Teilnahme.objects.create(user=self.skipper, toern=self.toern, rolle="skipper",
                                 status="bestaetigt", boot=self.mein_boot)
        Teilnahme.objects.create(user=self.anderer, toern=self.toern, rolle="skipper",
                                 status="bestaetigt", boot=self.anderes_boot)
        self.client.force_login(self.skipper)

    def test_pdf_wird_erzeugt(self):
        r = self.client.get(reverse("briefing_pdf", args=[self.mein_boot.id]))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/pdf")

    def test_skipper_erreicht_alle_boote_seines_toerns(self):
        """Wer das Skipper-Dashboard sehen darf, darf für jedes Boot des Törns
        vorbereiten — auf Flottentörns macht das meist eine Person."""
        r = self.client.get(reverse("briefing_liste", args=[self.anderes_boot.id]))
        self.assertEqual(r.status_code, 200)

    def test_fremder_toern_bleibt_gesperrt(self):
        """Die Grenze verläuft am Törn: fremde Törns bleiben zu."""
        from datetime import timedelta
        from django.utils import timezone
        from boote.models import Boot
        fremder = Toern.objects.create(
            titel="Fremd", anbieter=_user("fremd-anbieter@example.test"),
            startdatum=timezone.now(), enddatum=timezone.now() + timedelta(days=7),
            revier="R", preis_pro_person=1)
        fremdes_boot = Boot.objects.create(name="Fremdes", toern=fremder)
        r = self.client.get(reverse("briefing_liste", args=[fremdes_boot.id]))
        self.assertEqual(r.status_code, 403)

    def test_boote_haben_getrennte_auswahl(self):
        import json
        from toern.models import BriefingAuswahl

        BriefingBaustein.objects.create(titel="A", text="x", kategorie="sicherheit",
                                        ist_standard=True)
        self.client.get(reverse("briefing_liste", args=[self.mein_boot.id]))
        self.client.force_login(self.anderer)
        self.client.get(reverse("briefing_liste", args=[self.anderes_boot.id]))

        # Auf dem eigenen Boot etwas abschalten
        self.client.force_login(self.skipper)
        auswahl = BriefingAuswahl.objects.filter(boot=self.mein_boot).first()
        self.client.post(reverse("briefing_toggle", args=[self.mein_boot.id, auswahl.id]))

        auswahl.refresh_from_db()
        self.assertFalse(auswahl.aktiv)
        # Das andere Boot ist davon unberührt
        gegenstueck = BriefingAuswahl.objects.get(
            boot=self.anderes_boot, baustein=auswahl.baustein)
        self.assertTrue(gegenstueck.aktiv)

    def test_neuer_baustein_landet_in_seiner_kategorie(self):
        import json
        from toern.models import BriefingAuswahl

        for kat, titel in [("kommunikation", "K"), ("sonstiges", "S")]:
            BriefingBaustein.objects.create(titel=titel, text="x", kategorie=kat, ist_standard=True)
        self.client.get(reverse("briefing_liste", args=[self.mein_boot.id]))

        nachzuegler = BriefingBaustein.objects.create(
            titel="Später dazu", text="x", kategorie="kommunikation")
        self.client.post(
            reverse("briefing_baustein_hinzufuegen", args=[self.mein_boot.id]),
            data=json.dumps({"baustein_id": nachzuegler.id}),
            content_type="application/json",
        )

        auswahl = list(BriefingAuswahl.objects.filter(boot=self.mein_boot)
                       .select_related("baustein").order_by("reihenfolge"))
        kategorien = [a.baustein.kategorie for a in auswahl]
        index = [a.baustein_id for a in auswahl].index(nachzuegler.id)
        self.assertEqual(kategorien[index], "kommunikation")
        self.assertNotEqual(index, len(auswahl) - 1)

        gesehen = []
        for k in kategorien:
            if k not in gesehen:
                gesehen.append(k)
            else:
                self.assertEqual(gesehen[-1], k, "Kategorie-Block ist zerrissen")


class BriefingVorlagenTests(TestCase):
    """Persönliche Vorlagen: von Törn zu Törn mitnehmbar."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        from boote.models import Boot

        self.skipper = _user("v@example.test")
        toern = Toern.objects.create(
            titel="T", anbieter=self.skipper,
            startdatum=timezone.now(), enddatum=timezone.now() + timedelta(days=7),
            revier="R", preis_pro_person=1)
        self.boot = Boot.objects.create(name="B", toern=toern)
        self.zweites_boot = Boot.objects.create(name="B2", toern=toern)
        Teilnahme.objects.create(user=self.skipper, toern=toern, rolle="skipper",
                                 status="bestaetigt", boot=self.boot)
        self.a = BriefingBaustein.objects.create(titel="A", text="x", ist_standard=True)
        self.b = BriefingBaustein.objects.create(titel="B", text="x", ist_standard=True)
        self.client.force_login(self.skipper)

    def _vorlage_anlegen(self, name="Meine Standardrunde"):
        import json
        return self.client.post(
            reverse("briefing_standard_speichern", args=[self.boot.id]),
            data=json.dumps({"name": name}), content_type="application/json")

    def test_vorlage_speichert_nur_aktive_bausteine(self):
        from toern.models import BriefingAuswahl, BriefingStandard
        self.client.get(reverse("briefing_liste", args=[self.boot.id]))
        eine = BriefingAuswahl.objects.filter(boot=self.boot).first()
        self.client.post(reverse("briefing_toggle", args=[self.boot.id, eine.id]))  # abschalten

        r = self._vorlage_anlegen()
        self.assertEqual(r.status_code, 200)
        standard = BriefingStandard.objects.get(user=self.skipper)

        aktive = BriefingAuswahl.objects.filter(boot=self.boot, aktiv=True).count()
        self.assertEqual(standard.eintraege.count(), aktive)
        self.assertNotIn(eine.baustein_id,
                         standard.eintraege.values_list("baustein_id", flat=True))

    def test_vorlage_laden_ersetzt_die_auswahl(self):
        import json
        from toern.models import BriefingAuswahl, BriefingStandard
        self.client.get(reverse("briefing_liste", args=[self.boot.id]))
        self._vorlage_anlegen()
        standard = BriefingStandard.objects.get(user=self.skipper)

        # Auf dem zweiten Boot alles abwählen, dann Vorlage laden
        self.client.get(reverse("briefing_liste", args=[self.zweites_boot.id]))
        BriefingAuswahl.objects.filter(boot=self.zweites_boot).delete()
        self.client.post(
            reverse("briefing_standard_laden", args=[self.zweites_boot.id]),
            data=json.dumps({"standard_id": standard.id}), content_type="application/json")

        self.assertEqual(BriefingAuswahl.objects.filter(boot=self.zweites_boot).count(),
                         standard.eintraege.count())

    def test_default_vorlage_befuellt_neues_boot(self):
        from toern.models import BriefingAuswahl, BriefingStandard
        self.client.get(reverse("briefing_liste", args=[self.boot.id]))
        eine = BriefingAuswahl.objects.filter(boot=self.boot).first()
        self.client.post(reverse("briefing_toggle", args=[self.boot.id, eine.id]))
        self._vorlage_anlegen()
        standard = BriefingStandard.objects.get(user=self.skipper)
        self.client.post(reverse("briefing_standard_default", args=[standard.id]))

        # Neues Boot: bekommt die Vorlage statt der Bibliotheks-Standards
        self.client.get(reverse("briefing_liste", args=[self.zweites_boot.id]))
        self.assertEqual(BriefingAuswahl.objects.filter(boot=self.zweites_boot).count(),
                         standard.eintraege.count())

    def test_nur_eine_vorlage_ist_default(self):
        from toern.models import BriefingStandard
        self.client.get(reverse("briefing_liste", args=[self.boot.id]))
        self._vorlage_anlegen("Erste")
        self._vorlage_anlegen("Zweite")
        erste, zweite = (BriefingStandard.objects.get(name="Erste"),
                         BriefingStandard.objects.get(name="Zweite"))
        self.client.post(reverse("briefing_standard_default", args=[erste.id]))
        self.client.post(reverse("briefing_standard_default", args=[zweite.id]))
        erste.refresh_from_db(); zweite.refresh_from_db()
        self.assertFalse(erste.ist_default)
        self.assertTrue(zweite.ist_default)

    def test_fremde_vorlage_ist_nicht_erreichbar(self):
        from toern.models import BriefingStandard
        self.client.get(reverse("briefing_liste", args=[self.boot.id]))
        self._vorlage_anlegen()
        standard = BriefingStandard.objects.get(user=self.skipper)

        self.client.force_login(_user("fremd@example.test"))
        r = self.client.post(reverse("briefing_standard_loeschen", args=[standard.id]))
        self.assertEqual(r.status_code, 404)


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
