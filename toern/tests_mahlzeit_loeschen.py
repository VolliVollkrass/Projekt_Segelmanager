"""Tests: Mahlzeit aus dem Tagesplan löschen.

Der Knopf lag früher hinter einer engeren Rechteprüfung als das Anlegen —
Crew mit Tagesplan-Bearbeitungsrecht konnte eine Mahlzeit eintragen, aber
nicht wieder entfernen, und der Fehlschlag war im Browser nicht zu sehen.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from logistik.models import Mahlzeit, TagesplanBearbeitungsrecht
from .models import Teilnahme, Toern

User = get_user_model()


def _user(email, **extra):
    return User.objects.create(email=email, username=email, email_verified=True, **extra)


class MahlzeitLoeschenTests(TestCase):
    def setUp(self):
        self.anbieter = _user("mz-anbieter@test.de")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)

        self.skipper = _user("mz-skipper@test.de")
        self.t_skipper = Teilnahme.objects.create(
            toern=self.toern, user=self.skipper, status="bestaetigt",
            rolle="skipper", boot=self.boot,
        )
        self.coskipper = _user("mz-co@test.de")
        Teilnahme.objects.create(
            toern=self.toern, user=self.coskipper, status="bestaetigt",
            rolle="coskipper", boot=self.boot,
        )
        self.crew = _user("mz-crew@test.de")
        self.t_crew = Teilnahme.objects.create(
            toern=self.toern, user=self.crew, status="bestaetigt",
            rolle="crew", boot=self.boot,
        )
        self.fremder = _user("mz-fremd@test.de")
        self.datum = (start + timedelta(days=1)).date()

    def _mahlzeit(self):
        return Mahlzeit.objects.create(
            boot=self.boot, toern=self.toern, datum=self.datum,
            typ="abend", name="Nudeln",
        )

    def _loeschen(self, user, mahlzeit):
        self.client.force_login(user)
        return self.client.post(reverse("delete_mahlzeit", args=[mahlzeit.id]))

    def test_skipper_darf_loeschen(self):
        m = self._mahlzeit()
        self.assertEqual(self._loeschen(self.skipper, m).status_code, 200)
        self.assertEqual(Mahlzeit.objects.count(), 0)

    def test_coskipper_darf_loeschen(self):
        m = self._mahlzeit()
        self.assertEqual(self._loeschen(self.coskipper, m).status_code, 200)
        self.assertEqual(Mahlzeit.objects.count(), 0)

    def test_anbieter_darf_loeschen(self):
        m = self._mahlzeit()
        self.assertEqual(self._loeschen(self.anbieter, m).status_code, 200)
        self.assertEqual(Mahlzeit.objects.count(), 0)

    def test_crew_mit_bearbeitungsrecht_darf_loeschen(self):
        """Der eigentliche Fehler: anlegen durfte diese Person, löschen nicht."""
        TagesplanBearbeitungsrecht.objects.create(
            boot=self.boot, toern=self.toern, teilnahme=self.t_crew,
        )
        m = self._mahlzeit()
        self.assertEqual(self._loeschen(self.crew, m).status_code, 200)
        self.assertEqual(Mahlzeit.objects.count(), 0)

    def test_crew_ohne_bearbeitungsrecht_darf_nicht(self):
        m = self._mahlzeit()
        self.assertEqual(self._loeschen(self.crew, m).status_code, 403)
        self.assertEqual(Mahlzeit.objects.count(), 1)

    def test_fremder_darf_nicht(self):
        m = self._mahlzeit()
        self.assertEqual(self._loeschen(self.fremder, m).status_code, 403)
        self.assertEqual(Mahlzeit.objects.count(), 1)

    def test_recht_gilt_nur_fuer_das_eigene_boot(self):
        """Das Bearbeitungsrecht wird pro Boot vergeben — eine Mahlzeit auf
        einem anderen Boot bleibt damit tabu."""
        boot2 = Boot.objects.create(name="Zweitboot", typ="Yacht", toern=self.toern)
        TagesplanBearbeitungsrecht.objects.create(
            boot=self.boot, toern=self.toern, teilnahme=self.t_crew,
        )
        fremde_mahlzeit = Mahlzeit.objects.create(
            boot=boot2, toern=self.toern, datum=self.datum, typ="abend", name="Pizza",
        )
        self.assertEqual(self._loeschen(self.crew, fremde_mahlzeit).status_code, 403)
        self.assertEqual(Mahlzeit.objects.filter(id=fremde_mahlzeit.id).count(), 1)

    def test_loeschen_braucht_post(self):
        m = self._mahlzeit()
        self.client.force_login(self.skipper)
        resp = self.client.get(reverse("delete_mahlzeit", args=[m.id]))
        self.assertEqual(resp.status_code, 405)
        self.assertEqual(Mahlzeit.objects.count(), 1)


class TagesplanTabTests(TestCase):
    """Der Löschknopf darf die Seite nicht auf einen anderen Tab werfen."""

    def test_loeschen_leitet_nicht_mehr_in_die_bordkueche(self):
        anbieter = _user("tab-anbieter@test.de")
        start = timezone.now() + timedelta(days=30)
        toern = Toern.objects.create(
            titel="Testtörn", anbieter=anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=toern)
        skipper = _user("tab-skipper@test.de")
        Teilnahme.objects.create(
            toern=toern, user=skipper, status="bestaetigt", rolle="skipper", boot=boot,
        )
        Mahlzeit.objects.create(
            boot=boot, toern=toern, datum=(start + timedelta(days=1)).date(),
            typ="abend", name="Nudeln",
        )

        self.client.force_login(skipper)
        html = self.client.get(reverse("boot_dashboard", args=[toern.id])).content.decode()

        anfang = html.index("function deleteMahlzeit")
        block = html[anfang:anfang + 1600]
        self.assertNotIn('?tab=bordkueche', block)
        self.assertIn("mz-row-", block)
