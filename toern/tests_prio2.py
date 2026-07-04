"""Tests für die Prio-2-UX-Fixes."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import TeilnahmeDetailForm
from .models import Toern, Teilnahme

User = get_user_model()


def _user(email):
    return User.objects.create(email=email, username=email, email_verified=True)


def _toern(anbieter, **kwargs):
    start = timezone.now() + timedelta(days=30)
    defaults = dict(
        titel="Testtörn", anbieter=anbieter,
        startdatum=start, enddatum=start + timedelta(days=7),
        revier="Ostsee", preis_pro_person=500, status="ANMELDUNG_OFFEN",
    )
    defaults.update(kwargs)
    return Toern.objects.create(**defaults)


class KeineUnvertraeglichkeitenTests(TestCase):
    def setUp(self):
        self.anbieter = _user("anbieter@test.de")
        self.crew = _user("crew@test.de")
        self.toern = _toern(self.anbieter)
        self.teilnahme = Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt", rolle="crew"
        )

    def test_haekchen_setzt_beide_felder(self):
        form = TeilnahmeDetailForm(
            data={"keine_unvertraeglichkeiten": "on", "seglerische_erfahrung": "1"},
            instance=self.teilnahme,
        )
        self.assertTrue(form.is_valid(), form.errors)
        teilnahme = form.save()
        self.assertEqual(teilnahme.lebensmittelunvertraeglichkeiten, "Keine")
        self.assertEqual(teilnahme.allergien, "Keine")

    def test_haekchen_initial_gesetzt_wenn_beide_keine(self):
        self.teilnahme.lebensmittelunvertraeglichkeiten = "Keine"
        self.teilnahme.allergien = "keine"
        self.teilnahme.save()
        form = TeilnahmeDetailForm(instance=self.teilnahme)
        self.assertTrue(form.initial.get("keine_unvertraeglichkeiten"))

    def test_haekchen_initial_leer_bei_angaben(self):
        self.teilnahme.lebensmittelunvertraeglichkeiten = "laktosefrei"
        self.teilnahme.save()
        form = TeilnahmeDetailForm(instance=self.teilnahme)
        self.assertFalse(form.initial.get("keine_unvertraeglichkeiten"))

    def test_freitext_bleibt_ohne_haekchen_erhalten(self):
        form = TeilnahmeDetailForm(
            data={
                "lebensmittelunvertraeglichkeiten": "glutenfrei",
                "allergien": "Bienen",
                "seglerische_erfahrung": "1",
            },
            instance=self.teilnahme,
        )
        self.assertTrue(form.is_valid(), form.errors)
        teilnahme = form.save()
        self.assertEqual(teilnahme.lebensmittelunvertraeglichkeiten, "glutenfrei")
        self.assertEqual(teilnahme.allergien, "Bienen")


class VervollstaendigenLinkTests(TestCase):
    def test_banner_zeigt_auf_toern_formular(self):
        anbieter = _user("anbieter@test.de")
        crew = _user("crew@test.de")  # frisches Profil → < 100 %
        toern = _toern(anbieter)
        Teilnahme.objects.create(toern=toern, user=crew, status="bestaetigt", rolle="crew")

        self.client.force_login(crew)
        resp = self.client.get(reverse("crew_overview"))
        self.assertContains(resp, reverse("teilnahme_daten_edit", args=[toern.id]))


class EmailDatenLinkTests(TestCase):
    """Bestätigungs- und Erinnerungsmail müssen aufs Törn-Datenformular zeigen
    (dort liegen auch die Essensunverträglichkeiten), nicht aufs Account-Profil."""

    def setUp(self):
        from django.test import RequestFactory
        self.anbieter = _user("anbieter@test.de")
        self.crew = _user("crew@test.de")
        self.toern = _toern(self.anbieter)
        self.teilnahme = Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt", rolle="crew"
        )
        self.request = RequestFactory().get("/")

    def test_bestaetigungsmail_verlinkt_toern_formular(self):
        from django.core import mail
        from .emails import mail_teilnahme_bestaetigt
        mail_teilnahme_bestaetigt(self.teilnahme, self.request)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn(f"/toern/{self.toern.id}/daten/", body)
        self.assertNotIn("account-edit", body)

    def test_erinnerungsmail_verlinkt_toern_formular(self):
        from django.core import mail
        from .emails import mail_crew_daten_erinnerung
        mail_crew_daten_erinnerung(self.crew, self.toern, ["Telefonnummer"], self.request)
        self.assertEqual(len(mail.outbox), 1)
        body = mail.outbox[0].body
        self.assertIn(f"/toern/{self.toern.id}/daten/", body)
        self.assertNotIn("account-edit", body)


class AnbieterDashboardTests(TestCase):
    def test_bearbeiten_button_vorhanden(self):
        anbieter_gruppe, _ = Group.objects.get_or_create(name="Anbieter")
        anbieter = _user("anbieter@test.de")
        anbieter.groups.add(anbieter_gruppe)
        toern = _toern(anbieter)

        self.client.force_login(anbieter)
        resp = self.client.get(reverse("anbieter_dashboard"))
        self.assertContains(resp, reverse("toern_edit", args=[toern.id]))
