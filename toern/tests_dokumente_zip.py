"""Tests für den gebündelten Dokumenten-Download (ZIP) und den Schutz der Crewliste."""
import re
import zipfile
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from .models import Toern, Teilnahme

User = get_user_model()


def _user(email, **extra):
    return User.objects.create(email=email, username=email, email_verified=True, **extra)


class DokumenteZipTestBase(TestCase):
    def setUp(self):
        anbieter_gruppe, _ = Group.objects.get_or_create(name="Anbieter")
        self.anbieter = _user("zip-anbieter@test.de")
        self.anbieter.groups.add(anbieter_gruppe)
        self.skipper = _user("zip-skipper@test.de", first_name="Svea", last_name="Segler")
        self.crew = _user("zip-crew@test.de", first_name="Jan", last_name="Maat")
        self.fremder = _user("zip-fremd@test.de")

        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Törn mit Ümläuten", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(
            name="SY Dalmatinka", typ="Bavaria 46", toern=self.toern,
            funkrufzeichen="DGXY2", mmsi="211234560",
        )
        self.boot2 = Boot.objects.create(name="SY Jadran", typ="Sun Odyssey", toern=self.toern)
        Teilnahme.objects.create(
            toern=self.toern, user=self.skipper, status="bestaetigt",
            rolle="skipper", boot=self.boot,
        )
        Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt",
            rolle="crew", boot=self.boot,
        )

    def _zip(self, url_name, *args, user=None):
        self.client.force_login(user or self.skipper)
        resp = self.client.get(reverse(url_name, args=args))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/zip")
        return zipfile.ZipFile(BytesIO(resp.getvalue()))


class BootDokumenteZipTests(DokumenteZipTestBase):
    def test_zip_enthaelt_alle_dokumente_des_bootes(self):
        zf = self._zip("boot_dokumente_zip", self.boot.id)
        namen = zf.namelist()

        for erwartet in [
            "Mayday-Plakat.pdf",
            "Notfall-Sofortmassnahmen.pdf",
            "Checkliste-1-Charteruebernahme.pdf",
            "Checkliste-2-Bevor-wir-ablegen.pdf",
            "Checkliste-3-Nach-dem-Anlegen.pdf",
            "Checkliste-4-Rueckgabe.pdf",
            "Crewliste.pdf",
            "Teilnehmerliste.pdf",
            "Tagesplan.pdf",
        ]:
            self.assertIn(erwartet, namen)

    def test_enthaltene_dateien_sind_echte_pdfs(self):
        zf = self._zip("boot_dokumente_zip", self.boot.id)
        for name in zf.namelist():
            if name.endswith(".pdf"):
                self.assertTrue(zf.read(name).startswith(b"%PDF"), f"{name} ist kein PDF")

    def test_dateiname_ohne_umlaute_und_leerzeichen(self):
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("boot_dokumente_zip", args=[self.boot.id]))
        disposition = resp["Content-Disposition"]
        self.assertIn("SY-Dalmatinka", disposition)
        self.assertNotIn(" ", disposition.split("filename=")[1])

    def test_anbieter_darf_herunterladen(self):
        zf = self._zip("boot_dokumente_zip", self.boot.id, user=self.anbieter)
        self.assertIn("Mayday-Plakat.pdf", zf.namelist())

    def test_crew_darf_nicht_herunterladen(self):
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("boot_dokumente_zip", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 403)

    def test_fremder_darf_nicht_herunterladen(self):
        self.client.force_login(self.fremder)
        resp = self.client.get(reverse("boot_dokumente_zip", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 403)


class ToernDokumenteZipTests(DokumenteZipTestBase):
    def test_gesamt_zip_hat_einen_ordner_pro_boot(self):
        zf = self._zip("toern_dokumente_zip", self.toern.id)
        namen = zf.namelist()

        self.assertIn("SY-Dalmatinka/Mayday-Plakat.pdf", namen)
        self.assertIn("SY-Jadran/Mayday-Plakat.pdf", namen)

    def test_teilnehmerliste_liegt_nur_einmal_oben(self):
        zf = self._zip("toern_dokumente_zip", self.toern.id)
        teilnehmerlisten = [n for n in zf.namelist() if n.endswith("Teilnehmerliste.pdf")]
        self.assertEqual(teilnehmerlisten, ["Teilnehmerliste.pdf"])

    def test_crew_darf_nicht_herunterladen(self):
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("toern_dokumente_zip", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 403)


class CrewlistePdfRechteTests(DokumenteZipTestBase):
    """Die Crewliste enthält Pass- und Ausweisdaten — sie war bis dahin
    komplett ungeschützt abrufbar."""

    def test_anonym_wird_zum_login_geschickt(self):
        resp = self.client.get(reverse("crewlist_pdf", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/login", resp["Location"])

    def test_skipper_darf(self):
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("crewlist_pdf", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_anbieter_darf(self):
        self.client.force_login(self.anbieter)
        self.assertEqual(
            self.client.get(reverse("crewlist_pdf", args=[self.boot.id])).status_code, 200
        )

    def test_crew_darf_nicht(self):
        self.client.force_login(self.crew)
        self.assertEqual(
            self.client.get(reverse("crewlist_pdf", args=[self.boot.id])).status_code, 403
        )

    def test_fremder_darf_nicht(self):
        self.client.force_login(self.fremder)
        self.assertEqual(
            self.client.get(reverse("crewlist_pdf", args=[self.boot.id])).status_code, 403
        )


class TeilnehmerlisteSeitenTests(DokumenteZipTestBase):
    """Deckseite mit Essgewohnheiten, danach je ein Boot pro Seite."""

    def _seitenzahl(self, pdf_bytes):
        """Seitenanzahl aus dem Seitenbaum des PDFs — ohne extra Bibliothek."""
        treffer = re.findall(rb"/Count\s+(\d+)", pdf_bytes)
        self.assertTrue(treffer, "Kein Seitenbaum im PDF gefunden")
        return max(int(t) for t in treffer)

    def _teilnehmerliste(self):
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("teilnehmerliste_pdf", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 200)
        return resp.content

    def test_ein_boot_ergibt_deckseite_plus_eine_seite(self):
        self.assertEqual(self._seitenzahl(self._teilnehmerliste()), 2)

    def test_jedes_weitere_boot_bekommt_eine_eigene_seite(self):
        Teilnahme.objects.create(
            toern=self.toern, user=_user("zip-crew2@test.de", first_name="Kim"),
            status="bestaetigt", rolle="crew", boot=self.boot2,
        )
        self.assertEqual(self._seitenzahl(self._teilnehmerliste()), 3)

    def test_crew_ohne_boot_bekommt_auch_eine_eigene_seite(self):
        Teilnahme.objects.create(
            toern=self.toern, user=_user("zip-ohneboot@test.de", first_name="Nora"),
            status="angemeldet", rolle="crew", boot=None,
        )
        self.assertEqual(self._seitenzahl(self._teilnehmerliste()), 3)


class DeckblattDatenTests(DokumenteZipTestBase):
    """Die Inhalte des Deckblatts — geprüft an den Hilfsfunktionen, weil der
    Text im fertigen PDF komprimiert und damit nicht durchsuchbar ist."""

    def _teilnahmen(self):
        return list(
            Teilnahme.objects.filter(
                toern=self.toern, status__in=["angemeldet", "bestaetigt"]
            ).select_related("user", "boot")
        )

    def test_essgewohnheiten_werden_je_boot_gezaehlt(self):
        from .views import deckblatt_ess_pro_boot

        for t in self._teilnahmen():
            t.essgewohnheiten = "vegan" if t.user_id == self.crew.id else "alles"
            t.save()
        # Zweites Boot mit zwei Vegetariern
        for i in range(2):
            u = _user(f"zip-veg{i}@test.de", first_name=f"Veggie{i}")
            Teilnahme.objects.create(
                toern=self.toern, user=u, status="bestaetigt", rolle="crew",
                boot=self.boot2, essgewohnheiten="vegetarisch",
            )

        pro_boot = dict(deckblatt_ess_pro_boot(self._teilnahmen()))
        self.assertEqual(pro_boot["SY Dalmatinka"]["alles"], 1)
        self.assertEqual(pro_boot["SY Dalmatinka"]["vegan"], 1)
        self.assertEqual(pro_boot["SY Jadran"]["vegetarisch"], 2)
        self.assertEqual(sum(pro_boot["SY Jadran"].values()), 2)

    def test_boote_alphabetisch_ohne_boot_zuletzt(self):
        from .views import deckblatt_ess_pro_boot

        u = _user("zip-ohneboot@test.de", first_name="Nora")
        Teilnahme.objects.create(
            toern=self.toern, user=u, status="angemeldet", rolle="crew", boot=None,
        )
        Teilnahme.objects.create(
            toern=self.toern, user=_user("zip-jadran@test.de", first_name="Ida"),
            status="bestaetigt", rolle="crew", boot=self.boot2,
        )

        namen = [name for name, _ in deckblatt_ess_pro_boot(self._teilnahmen())]
        self.assertEqual(namen, ["SY Dalmatinka", "SY Jadran", "ohne Boot"])

    def test_fehlende_angabe_zaehlt_als_keine_angabe(self):
        from .views import deckblatt_ess_pro_boot

        for t in self._teilnahmen():
            t.essgewohnheiten = ""
            t.save()

        pro_boot = dict(deckblatt_ess_pro_boot(self._teilnahmen()))
        self.assertEqual(pro_boot["SY Dalmatinka"][""], 2)

    def test_geburtstage_nur_im_toern_zeitraum_und_chronologisch(self):
        from .views import deckblatt_geburtstage

        start = self.toern.startdatum.date()
        # Im Zeitraum: zweiter Tag …
        self.crew.geburtsdatum = (start + timedelta(days=2)).replace(year=1990)
        self.crew.save()
        # … und erster Tag (soll vorne stehen)
        self.skipper.geburtsdatum = start.replace(year=1985)
        self.skipper.save()
        # Außerhalb: ein halbes Jahr später
        ausserhalb = _user("zip-spaet@test.de", first_name="Tim", last_name="Spät")
        ausserhalb.geburtsdatum = (start + timedelta(days=180)).replace(year=1992)
        ausserhalb.save()
        Teilnahme.objects.create(
            toern=self.toern, user=ausserhalb, status="bestaetigt",
            rolle="crew", boot=self.boot,
        )

        geburtstage = deckblatt_geburtstage(self.toern, self._teilnahmen())
        self.assertEqual([g[0] for g in geburtstage], ["Svea Segler", "Jan Maat"])

    def test_29_februar_faellt_nicht_auf_die_nase(self):
        from .views import hat_geburtstag_im_toern
        from datetime import date

        self.assertIsInstance(
            hat_geburtstag_im_toern(self.toern, date(1992, 2, 29)), bool
        )

    def test_offene_angaben_zaehlen_fehlende_felder(self):
        from .views import deckblatt_offene_angaben

        # Skipper vollständig, Crew unvollständig
        self.skipper.telefonnummer = "+49 170 1234567"
        self.skipper.save()
        for t in self._teilnahmen():
            t.notfallkontakt_name = "Kontakt" if t.user_id == self.skipper.id else ""
            t.essgewohnheiten = "alles" if t.user_id == self.skipper.id else ""
            t.save()

        offen = dict(deckblatt_offene_angaben(self._teilnahmen()))
        self.assertEqual(offen["Notfallkontakt"], 1)
        self.assertEqual(offen["Telefonnummer"], 1)
        self.assertEqual(offen["Essgewohnheiten"], 1)

    def test_vollstaendige_angaben_ergeben_keine_meldung(self):
        from .views import deckblatt_offene_angaben

        for nutzer in (self.skipper, self.crew):
            nutzer.telefonnummer = "+49 170 1234567"
            nutzer.save()
        for t in self._teilnahmen():
            t.notfallkontakt_name = "Kontakt"
            t.essgewohnheiten = "alles"
            t.save()

        self.assertEqual(deckblatt_offene_angaben(self._teilnahmen()), [])

    def test_deckblatt_bleibt_bei_normaler_crew_auf_einer_seite(self):
        t = Teilnahme.objects.get(toern=self.toern, user=self.crew)
        t.allergien = "Nüsse"
        t.save()
        self.crew.geburtsdatum = self.toern.startdatum.date().replace(year=1990)
        self.crew.save()

        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("teilnehmerliste_pdf", args=[self.toern.id]))
        treffer = re.findall(rb"/Count\s+(\d+)", resp.content)
        # Deckblatt + ein Boot mit Crew
        self.assertEqual(max(int(x) for x in treffer), 2)
