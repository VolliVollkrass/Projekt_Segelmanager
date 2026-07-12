"""Tests für das Schadensprotokoll (CRUD, Zugriff, Status, Bilder, PDF)."""
from datetime import timedelta
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from PIL import Image

from boote.models import Boot
from .models import Schadensbild, Schadensmeldung, Teilnahme, Toern

import shutil
import tempfile

User = get_user_model()
MEDIA = tempfile.mkdtemp()


def _user(email):
    return User.objects.create(email=email, username=email, first_name=email.split("@")[0], email_verified=True)


def _bild(name="foto.jpg", groesse=(2000, 1500)):
    """Ein großes Test-JPEG, damit die Verkleinerung greift."""
    buf = BytesIO()
    Image.new("RGB", groesse, (120, 140, 160)).save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@override_settings(MEDIA_ROOT=MEDIA)
class SchadenTestBase(TestCase):
    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(MEDIA, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.anbieter = _user("anbieter@test.de")
        self.skipper = _user("skipper@test.de")
        self.crew = _user("crew@test.de")
        self.crew2 = _user("crew2@test.de")
        self.fremder = _user("fremder@test.de")

        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter, startdatum=start,
            enddatum=start + timedelta(days=7), revier="Ostsee",
            preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Adria 2", typ="Bavaria 46", toern=self.toern)
        self.anderes_boot = Boot.objects.create(name="Adria 3", typ="Bavaria 46", toern=self.toern)
        Teilnahme.objects.create(toern=self.toern, user=self.skipper, status="bestaetigt", rolle="skipper", boot=self.boot)
        Teilnahme.objects.create(toern=self.toern, user=self.crew, status="bestaetigt", rolle="crew", boot=self.boot)
        Teilnahme.objects.create(toern=self.toern, user=self.crew2, status="bestaetigt", rolle="crew", boot=self.boot)
        # Fremder ist auf einem anderen Boot desselben Törns
        Teilnahme.objects.create(toern=self.toern, user=self.fremder, status="bestaetigt", rolle="crew", boot=self.anderes_boot)


class SchadenAnlegenTests(SchadenTestBase):
    def test_crew_kann_schaden_mit_foto_anlegen(self):
        self.client.force_login(self.crew)
        resp = self.client.post(reverse("schaden_neu", args=[self.boot.id]), {
            "titel": "Winsch blockiert", "ort": "Steuerbord-Cockpit",
            "schweregrad": 4, "beschreibung": "Dreht nicht.", "status": "offen",
            "bilder": [_bild()],
        })
        self.assertEqual(resp.status_code, 302)
        s = Schadensmeldung.objects.get(titel="Winsch blockiert")
        self.assertEqual(s.boot, self.boot)
        self.assertEqual(s.toern, self.toern)
        self.assertEqual(s.erstellt_von, self.crew)
        self.assertEqual(s.bilder.count(), 1)
        # Foto wurde verkleinert (max 1200px) und als .jpg gespeichert
        self.assertTrue(s.bilder.first().bild.name.endswith(".jpg"))
        with Image.open(s.bilder.first().bild.path) as im:
            self.assertLessEqual(max(im.size), 1200)

    def test_max_5_bilder_serverseitig(self):
        self.client.force_login(self.skipper)
        self.client.post(reverse("schaden_neu", args=[self.boot.id]), {
            "titel": "Viele Fotos", "ort": "Deck", "schweregrad": 2, "status": "offen",
            "bilder": [_bild(f"f{i}.jpg") for i in range(7)],
        })
        s = Schadensmeldung.objects.get(titel="Viele Fotos")
        self.assertEqual(s.bilder.count(), 5)

    def test_pflichtfelder(self):
        self.client.force_login(self.crew)
        resp = self.client.post(reverse("schaden_neu", args=[self.boot.id]), {
            "titel": "", "ort": "", "schweregrad": 3, "status": "offen",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Schadensmeldung.objects.exists())

    def test_fremder_kein_zugriff(self):
        self.client.force_login(self.fremder)
        resp = self.client.get(reverse("schaden_neu", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 403)


class SchadenBearbeitenLoeschenTests(SchadenTestBase):
    def _schaden(self, autor):
        return Schadensmeldung.objects.create(
            boot=self.boot, toern=self.toern, titel="X", ort="Y",
            schweregrad=3, status="offen", erstellt_von=autor,
        )

    def test_fremde_crew_darf_bearbeiten(self):
        s = self._schaden(self.crew)
        self.client.force_login(self.crew2)
        resp = self.client.post(reverse("schaden_bearbeiten", args=[s.id]), {
            "titel": "Geändert", "ort": "Y", "schweregrad": 5, "status": "behoben",
        })
        self.assertEqual(resp.status_code, 302)
        s.refresh_from_db()
        self.assertEqual(s.titel, "Geändert")
        self.assertEqual(s.geaendert_von, self.crew2)

    def test_crew_darf_fremden_eintrag_nicht_loeschen(self):
        s = self._schaden(self.crew)
        self.client.force_login(self.crew2)
        resp = self.client.post(reverse("schaden_loeschen", args=[s.id]))
        self.assertEqual(resp.status_code, 403)
        self.assertTrue(Schadensmeldung.objects.filter(id=s.id).exists())

    def test_autor_darf_eigenen_loeschen(self):
        s = self._schaden(self.crew)
        self.client.force_login(self.crew)
        resp = self.client.post(reverse("schaden_loeschen", args=[s.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Schadensmeldung.objects.filter(id=s.id).exists())

    def test_skipper_darf_fremden_loeschen(self):
        s = self._schaden(self.crew)
        self.client.force_login(self.skipper)
        resp = self.client.post(reverse("schaden_loeschen", args=[s.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(Schadensmeldung.objects.filter(id=s.id).exists())

    def test_status_umschalten(self):
        s = self._schaden(self.crew)
        self.client.force_login(self.crew2)
        resp = self.client.post(reverse("schaden_status", args=[s.id]), {"status": "gemeldet"})
        self.assertEqual(resp.status_code, 200)
        s.refresh_from_db()
        self.assertEqual(s.status, "gemeldet")
        self.assertEqual(s.geaendert_von, self.crew2)
        self.assertEqual(resp.json()["farbe"], "badge-info")

    def test_status_ungueltig(self):
        s = self._schaden(self.crew)
        self.client.force_login(self.crew)
        resp = self.client.post(reverse("schaden_status", args=[s.id]), {"status": "quatsch"})
        self.assertEqual(resp.status_code, 400)

    def test_bild_loeschen(self):
        s = self._schaden(self.crew)
        b = Schadensbild.objects.create(meldung=s, bild=_bild())
        self.client.force_login(self.crew2)
        resp = self.client.post(reverse("schaden_bild_loeschen", args=[b.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Schadensbild.objects.filter(id=b.id).exists())


class SchadenPdfTests(SchadenTestBase):
    def _schaden(self):
        s = Schadensmeldung.objects.create(
            boot=self.boot, toern=self.toern, titel="Riss im Segel", ort="Großsegel",
            schweregrad=5, status="gemeldet", erstellt_von=self.crew,
        )
        Schadensbild.objects.create(meldung=s, bild=_bild())
        return s

    def test_gesamt_pdf(self):
        self._schaden()
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("schaden_gesamt_pdf", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "application/pdf")
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_gesamt_pdf_leer_geht_trotzdem(self):
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("schaden_gesamt_pdf", args=[self.boot.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_einzel_pdf(self):
        s = self._schaden()
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("schaden_einzel_pdf", args=[s.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.content.startswith(b"%PDF"))

    def test_pdf_fremder_403(self):
        s = self._schaden()
        self.client.force_login(self.fremder)
        self.assertEqual(self.client.get(reverse("schaden_gesamt_pdf", args=[self.boot.id])).status_code, 403)
        self.assertEqual(self.client.get(reverse("schaden_einzel_pdf", args=[s.id])).status_code, 403)


class SchadenTabTests(SchadenTestBase):
    def test_tab_und_liste_sichtbar(self):
        Schadensmeldung.objects.create(
            boot=self.boot, toern=self.toern, titel="Testschaden", ort="Bug",
            schweregrad=3, status="offen", erstellt_von=self.crew,
        )
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("boot_dashboard", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-tab="schaden"')
        self.assertContains(resp, "Testschaden")


class CharterbasisFeldTests(SchadenTestBase):
    def test_skipper_kann_charterbasis_email_setzen(self):
        self.client.force_login(self.skipper)
        resp = self.client.post(reverse("boot_update", args=[self.boot.id]), {
            "name": self.boot.name, "typ": self.boot.typ,
            "charterbasis_name": "Pitter", "charterbasis_email": "charter@basis.de",
            "kabine_set-TOTAL_FORMS": "0", "kabine_set-INITIAL_FORMS": "0",
            "kabine_set-MIN_NUM_FORMS": "0", "kabine_set-MAX_NUM_FORMS": "1000",
        })
        self.assertIn(resp.status_code, (302, 200))
        self.boot.refresh_from_db()
        self.assertEqual(self.boot.charterbasis_email, "charter@basis.de")
        self.assertEqual(self.boot.charterbasis_name, "Pitter")
