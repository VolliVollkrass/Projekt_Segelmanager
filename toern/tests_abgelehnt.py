"""Tests: Abgelehnte Teilnehmer verlieren Zugriff und verschwinden aus den Listen."""
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


class AbgelehntTests(TestCase):
    def setUp(self):
        anbieter_gruppe, _ = Group.objects.get_or_create(name="Anbieter")
        self.anbieter = _user("anbieter@test.de")
        self.anbieter.groups.add(anbieter_gruppe)
        self.abgelehnter = _user("raus@test.de")
        self.crew = _user("crew@test.de")

        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn",
            anbieter=self.anbieter,
            startdatum=start,
            enddatum=start + timedelta(days=7),
            revier="Ostsee",
            preis_pro_person=500,
            status="ANMELDUNG_OFFEN",
        )
        self.t_abgelehnt = Teilnahme.objects.create(
            toern=self.toern, user=self.abgelehnter, status="abgelehnt", rolle="crew"
        )
        Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt", rolle="crew"
        )

    def test_abgelehnter_hat_keinen_dashboard_zugriff(self):
        self.client.force_login(self.abgelehnter)
        resp = self.client.get(reverse("crew_dashboard", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 403)

    def test_bestaetigter_hat_zugriff(self):
        self.client.force_login(self.crew)
        resp = self.client.get(reverse("crew_dashboard", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 200)

    def test_abgelehnter_toern_nicht_in_meine_toerns(self):
        self.client.force_login(self.abgelehnter)
        resp = self.client.get(reverse("crew_overview"))
        self.assertNotContains(resp, "Testtörn")

    def test_skipper_dashboard_trennt_abgelehnte(self):
        self.client.force_login(self.anbieter)
        resp = self.client.get(reverse("skipper_dashboard", args=[self.toern.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn(self.t_abgelehnt, list(resp.context["teilnahmen"]))
        self.assertIn(self.t_abgelehnt, list(resp.context["abgelehnte"]))

    def test_ablehnen_entfernt_boot_und_kabine(self):
        t = Teilnahme.objects.create(
            toern=self.toern, user=_user("neu@test.de"), status="angemeldet", rolle="crew"
        )
        self.client.force_login(self.anbieter)
        resp = self.client.post(reverse("teilnehmer_ablehnen", args=[t.id]))
        self.assertEqual(resp.status_code, 302)
        t.refresh_from_db()
        self.assertEqual(t.status, "abgelehnt")
        self.assertIsNone(t.boot)
        self.assertIsNone(t.kabine)
