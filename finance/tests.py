"""Tests für die Bootskasse (Ausgabe bearbeiten) und den Skipper-Topf (Belege/Abrechnung)."""
import io
import tempfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from toern.models import Toern, Teilnahme
from .models import Ausgabe, TopfAusgabe, TopfBeleg
from .utils import rate_kategorie

User = get_user_model()


def _user(email):
    return User.objects.create(email=email, username=email, email_verified=True)


def _bild_upload(name="beleg.png"):
    """Kleines gültiges PNG als Upload (wird vom ProcessedImageField zu JPEG verarbeitet)."""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), (200, 120, 80)).save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


class AusgabeBearbeitenTests(TestCase):
    def setUp(self):
        self.anbieter = _user("anbieter@test.de")
        self.zahler_user = _user("zahler@test.de")
        self.crew_user = _user("crew@test.de")
        self.fremder = _user("fremd@test.de")

        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)
        self.zahler = Teilnahme.objects.create(
            toern=self.toern, user=self.zahler_user, status="bestaetigt", rolle="crew", boot=self.boot
        )
        self.crew = Teilnahme.objects.create(
            toern=self.toern, user=self.crew_user, status="bestaetigt", rolle="crew", boot=self.boot
        )

        self.ausgabe = Ausgabe.objects.create(
            boot=self.boot, toern=self.toern,
            beschreibung="Einkauf Hafen", betrag=Decimal("30.00"),
            bezahlt_von=self.zahler, erstellt_von=self.zahler_user,
        )
        self.ausgabe.beteiligt.set([self.zahler, self.crew])

    def _bearbeiten(self, user, **overrides):
        self.client.force_login(user)
        data = {
            "beschreibung": "Einkauf Hafen + Eis",
            "betrag": "45,50",
            "bezahlt_von": self.crew.id,
            "beteiligt": [self.crew.id],
        }
        data.update(overrides)
        return self.client.post(reverse("ausgabe_bearbeiten", args=[self.ausgabe.id]), data)

    def test_zahler_darf_bearbeiten(self):
        resp = self._bearbeiten(self.zahler_user)
        self.assertEqual(resp.status_code, 302)
        self.ausgabe.refresh_from_db()
        self.assertEqual(self.ausgabe.beschreibung, "Einkauf Hafen + Eis")
        self.assertEqual(self.ausgabe.betrag, Decimal("45.50"))
        self.assertEqual(self.ausgabe.bezahlt_von, self.crew)
        self.assertEqual(list(self.ausgabe.beteiligt.all()), [self.crew])

    def test_anbieter_darf_bearbeiten(self):
        resp = self._bearbeiten(self.anbieter)
        self.assertEqual(resp.status_code, 302)
        self.ausgabe.refresh_from_db()
        self.assertEqual(self.ausgabe.beschreibung, "Einkauf Hafen + Eis")

    def test_fremder_darf_nicht_bearbeiten(self):
        resp = self._bearbeiten(self.fremder)
        self.assertEqual(resp.status_code, 403)
        self.ausgabe.refresh_from_db()
        self.assertEqual(self.ausgabe.beschreibung, "Einkauf Hafen")

    def test_ungueltiger_betrag_aendert_nichts(self):
        self._bearbeiten(self.zahler_user, betrag="quatsch")
        self.ausgabe.refresh_from_db()
        self.assertEqual(self.ausgabe.betrag, Decimal("30.00"))


class RateKategorieTests(TestCase):
    def test_stichworte_treffen(self):
        self.assertEqual(rate_kategorie("Diesel getankt fürs Schiff"), "treibstoff")
        self.assertEqual(rate_kategorie("Vignette Slowenien"), "anreise")
        self.assertEqual(rate_kategorie("Liegeplatz Marina Kornati"), "hafen")
        self.assertEqual(rate_kategorie("Endreinigung Charter"), "charter")
        self.assertEqual(rate_kategorie("Essen im Restaurant Konoba"), "verpflegung")
        self.assertEqual(rate_kategorie("Skipper-Haftpflicht Versicherung"), "versicherung")
        self.assertEqual(rate_kategorie("Crew T-Shirts"), "crew")

    def test_kein_treffer_ist_sonstiges(self):
        self.assertEqual(rate_kategorie("Irgendwas Undefinierbares"), "sonstiges")


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class TopfBelegAbrechnungTests(TestCase):
    def setUp(self):
        self.anbieter = _user("anbieter@test.de")
        self.skipper_user = _user("skipper@test.de")
        self.fremder = _user("fremd@test.de")

        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Kroatien-Törn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Adria", preis_pro_person=800, status="ZUTEILUNG_FIXIERT",
            skipper_budget=Decimal("1000.00"),
        )
        self.boot = Boot.objects.create(name="Bavaria", typ="Yacht", toern=self.toern)
        self.skipper = Teilnahme.objects.create(
            toern=self.toern, user=self.skipper_user, status="bestaetigt",
            rolle="skipper", boot=self.boot,
        )

    def _erstellen_url(self):
        return reverse("topf_ausgabe_erstellen", args=[self.toern.id])

    def test_erstellen_mit_beleg_und_autokategorie(self):
        self.client.force_login(self.skipper_user)
        resp = self.client.post(self._erstellen_url(), {
            "beschreibung": "Diesel getankt",
            "betrag": "80,00",
            "kategorie": "",  # → Auto-Erkennung
            "belege": [_bild_upload("q1.png"), _bild_upload("q2.png")],
        })
        self.assertEqual(resp.status_code, 302)
        ausgabe = TopfAusgabe.objects.get()
        self.assertEqual(ausgabe.kategorie, "treibstoff")
        self.assertEqual(ausgabe.betrag, Decimal("80.00"))
        self.assertEqual(ausgabe.belege.count(), 2)

    def test_explizite_kategorie_gewinnt(self):
        self.client.force_login(self.skipper_user)
        self.client.post(self._erstellen_url(), {
            "beschreibung": "Diesel getankt", "betrag": "80,00", "kategorie": "sonstiges",
        })
        self.assertEqual(TopfAusgabe.objects.get().kategorie, "sonstiges")

    def test_fremder_darf_nicht_erstellen(self):
        self.client.force_login(self.fremder)
        resp = self.client.post(self._erstellen_url(), {
            "beschreibung": "X", "betrag": "10,00",
        })
        self.assertEqual(resp.status_code, 403)
        self.assertFalse(TopfAusgabe.objects.exists())

    def _make_ausgabe(self, **kw):
        defaults = dict(
            toern=self.toern, erstellt_von=self.skipper_user,
            beschreibung="Testausgabe", betrag=Decimal("50.00"), kategorie="sonstiges",
        )
        defaults.update(kw)
        return TopfAusgabe.objects.create(**defaults)

    def test_bearbeiten_aendert_kategorie(self):
        ausgabe = self._make_ausgabe()
        self.client.force_login(self.skipper_user)
        resp = self.client.post(reverse("topf_ausgabe_bearbeiten", args=[ausgabe.id]), {
            "beschreibung": "Neue Beschreibung", "betrag": "60,00", "kategorie": "hafen",
        })
        self.assertEqual(resp.status_code, 302)
        ausgabe.refresh_from_db()
        self.assertEqual(ausgabe.kategorie, "hafen")
        self.assertEqual(ausgabe.betrag, Decimal("60.00"))

    def test_beleg_hinzufuegen_und_loeschen(self):
        ausgabe = self._make_ausgabe()
        self.client.force_login(self.skipper_user)
        self.client.post(reverse("topf_beleg_add", args=[ausgabe.id]), {
            "belege": [_bild_upload()],
        })
        self.assertEqual(ausgabe.belege.count(), 1)
        beleg = ausgabe.belege.get()
        resp = self.client.post(reverse("topf_beleg_loeschen", args=[beleg.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ausgabe.belege.count(), 0)

    def test_pdf_export(self):
        a = self._make_ausgabe(kategorie="treibstoff", beschreibung="Diesel")
        TopfBeleg.objects.create(ausgabe=a, bild=_bild_upload(), hochgeladen_von=self.skipper_user)
        self.client.force_login(self.skipper_user)
        resp = self.client.get(reverse("topf_belege_pdf", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertGreater(len(resp.getvalue()), 500)

    def test_xlsx_export(self):
        self._make_ausgabe(kategorie="hafen", beschreibung="Liegeplatz", betrag=Decimal("120.00"))
        self.client.force_login(self.skipper_user)
        resp = self.client.get(reverse("topf_abrechnung_xlsx", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertIn("spreadsheetml", resp["Content-Type"])
        self.assertGreater(len(resp.getvalue()), 500)

    def test_export_fremder_verboten(self):
        self.client.force_login(self.fremder)
        self.assertEqual(self.client.get(reverse("topf_belege_pdf", args=[self.toern.id])).status_code, 403)
        self.assertEqual(self.client.get(reverse("topf_abrechnung_xlsx", args=[self.toern.id])).status_code, 403)
