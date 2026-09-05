"""Tests für die zugriffsgeschützte Medien-Auslieferung (utils.protected_media)
und den SSRF-Schutz (utils.url_guard)."""
import io
import tempfile
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from boote.models import Boot
from finance.models import TopfAusgabe, TopfBeleg
from toern.models import Toern, Teilnahme
from utils.url_guard import UnsafeUrlError, _pruefe_url

User = get_user_model()

MEDIA = tempfile.mkdtemp()


def _user(email):
    return User.objects.create(email=email, username=email, email_verified=True)


def _png(name="beleg.png"):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (40, 60), (200, 120, 80)).save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA)
class BelegMediaZugriffTests(TestCase):
    """Belege (finance) dürfen nur von Berechtigten geladen werden."""

    def setUp(self):
        self.anbieter = _user("anbieter@test.de")
        self.skipper_user = _user("skipper@test.de")
        self.uploader = _user("uploader@test.de")
        self.fremder = _user("fremd@test.de")

        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)
        Teilnahme.objects.create(
            toern=self.toern, user=self.skipper_user, status="bestaetigt",
            rolle="skipper", boot=self.boot,
        )
        ausgabe = TopfAusgabe.objects.create(
            toern=self.toern, erstellt_von=self.anbieter,
            beschreibung="Charter", betrag=100,
        )
        self.beleg = TopfBeleg.objects.create(
            ausgabe=ausgabe, bild=_png(), hochgeladen_von=self.uploader,
        )
        self.url = self.beleg.bild.url

    def test_anonym_bekommt_404(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_fremder_bekommt_404(self):
        self.client.force_login(self.fremder)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_uploader_darf(self):
        self.client.force_login(self.uploader)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_anbieter_darf(self):
        self.client.force_login(self.anbieter)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_skipper_darf(self):
        self.client.force_login(self.skipper_user)
        self.assertEqual(self.client.get(self.url).status_code, 200)


class SecurityHeaderTests(TestCase):
    def test_csp_und_permissions_policy_gesetzt(self):
        resp = self.client.get("/")
        self.assertIn("Content-Security-Policy", resp)
        self.assertIn("frame-ancestors 'none'", resp["Content-Security-Policy"])
        self.assertIn("object-src 'none'", resp["Content-Security-Policy"])
        self.assertIn("Permissions-Policy", resp)

    def test_csp_ohne_externe_cdn(self):
        """Nach der Lokalisierung von cropperjs darf kein CDN mehr erlaubt sein."""
        csp = self.client.get("/")["Content-Security-Policy"]
        self.assertNotIn("unpkg.com", csp)
        self.assertNotIn("http", csp)  # keine externen http(s)-Quellen


class LegalPageTests(TestCase):
    """Impressum und Datenschutzerklärung müssen öffentlich erreichbar sein."""

    def test_impressum_erreichbar(self):
        resp = self.client.get("/impressum/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Impressum")

    def test_datenschutz_erreichbar(self):
        resp = self.client.get("/datenschutz/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Datenschutz")

    def test_footer_verlinkt_rechtsseiten(self):
        html = self.client.get("/").content.decode()
        self.assertIn("/impressum/", html)
        self.assertIn("/datenschutz/", html)


class UrlGuardTests(TestCase):
    """SSRF-Schutz: interne/nicht-http-Ziele werden abgelehnt."""

    def test_nicht_http_schema_blockiert(self):
        for url in ("file:///etc/passwd", "ftp://example.com/x", "gopher://x"):
            with self.assertRaises(UnsafeUrlError):
                _pruefe_url(url)

    def test_localhost_blockiert(self):
        with self.assertRaises(UnsafeUrlError):
            _pruefe_url("http://127.0.0.1/admin")

    def test_metadaten_ip_blockiert(self):
        with self.assertRaises(UnsafeUrlError):
            _pruefe_url("http://169.254.169.254/latest/meta-data/")

    def test_privater_bereich_blockiert(self):
        with self.assertRaises(UnsafeUrlError):
            _pruefe_url("http://10.0.0.5/")
