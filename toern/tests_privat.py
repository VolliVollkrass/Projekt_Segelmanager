"""Tests für private Törns (nur über Einladungslink erreichbar)."""
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Toern, Teilnahme

User = get_user_model()


def _user(email):
    return User.objects.create(email=email, username=email, email_verified=True)


def _toern(anbieter, **kwargs):
    start = timezone.now() + timedelta(days=30)
    defaults = dict(
        titel="Testtörn",
        anbieter=anbieter,
        startdatum=start,
        enddatum=start + timedelta(days=7),
        revier="Ostsee",
        preis_pro_person=500,
        status="ANMELDUNG_OFFEN",
    )
    defaults.update(kwargs)
    return Toern.objects.create(**defaults)


class PrivaterToernTests(TestCase):
    def setUp(self):
        self.anbieter_gruppe, _ = Group.objects.get_or_create(name="Anbieter")
        self.anbieter = _user("anbieter@test.de")
        self.anbieter.groups.add(self.anbieter_gruppe)
        self.crew = _user("crew@test.de")
        self.fremder = _user("fremd@test.de")

        self.privat = _toern(self.anbieter, titel="Geheimer Törn", ist_privat=True)
        self.oeffentlich = _toern(self.anbieter, titel="Offener Törn")

        Teilnahme.objects.create(toern=self.privat, user=self.crew, status="bestaetigt")

        self.detail_url = reverse("toern_detail", args=[self.privat.pk])

    def test_oeffentlicher_toern_anonym_erreichbar(self):
        resp = self.client.get(reverse("toern_detail", args=[self.oeffentlich.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_privat_anonym_ohne_key_404(self):
        self.assertEqual(self.client.get(self.detail_url).status_code, 404)

    def test_privat_mit_falschem_key_404(self):
        resp = self.client.get(self.detail_url, {"key": str(uuid.uuid4())})
        self.assertEqual(resp.status_code, 404)

    def test_privat_mit_key_erreichbar_und_session_merkt_sich(self):
        resp = self.client.get(self.detail_url, {"key": str(self.privat.privat_token)})
        self.assertEqual(resp.status_code, 200)
        # Folgeaufruf ohne Key funktioniert dank Session
        self.assertEqual(self.client.get(self.detail_url).status_code, 200)
        # Anmeldeseite ebenfalls erreichbar
        anmeldung = self.client.get(reverse("toern_anmeldung", args=[self.privat.pk]))
        self.assertEqual(anmeldung.status_code, 200)

    def test_privat_anbieter_ohne_key_erreichbar(self):
        self.client.force_login(self.anbieter)
        self.assertEqual(self.client.get(self.detail_url).status_code, 200)

    def test_privat_teilnehmer_ohne_key_erreichbar(self):
        self.client.force_login(self.crew)
        self.assertEqual(self.client.get(self.detail_url).status_code, 200)

    def test_privat_fremder_user_404(self):
        self.client.force_login(self.fremder)
        self.assertEqual(self.client.get(self.detail_url).status_code, 404)

    def test_privat_anmeldung_ohne_key_404(self):
        self.assertEqual(
            self.client.get(reverse("toern_anmeldung", args=[self.privat.pk])).status_code, 404
        )

    def test_startseite_versteckt_private(self):
        resp = self.client.get("/")
        self.assertNotContains(resp, "Geheimer Törn")
        self.assertContains(resp, "Offener Törn")

    def test_startseite_zeigt_private_dem_anbieter(self):
        self.client.force_login(self.anbieter)
        resp = self.client.get("/")
        self.assertContains(resp, "Geheimer Törn")

    def test_startseite_zeigt_private_dem_teilnehmer(self):
        self.client.force_login(self.crew)
        resp = self.client.get("/")
        self.assertContains(resp, "Geheimer Törn")

    def test_toggle_nur_eigener_anbieter(self):
        anderer = _user("anderer@test.de")
        anderer.groups.add(self.anbieter_gruppe)
        self.client.force_login(anderer)
        resp = self.client.post(reverse("toern_privat_toggle", args=[self.privat.pk]))
        self.assertEqual(resp.status_code, 403)

    def test_toggle_schaltet_um(self):
        self.client.force_login(self.anbieter)
        self.client.post(reverse("toern_privat_toggle", args=[self.privat.pk]))
        self.privat.refresh_from_db()
        self.assertFalse(self.privat.ist_privat)
