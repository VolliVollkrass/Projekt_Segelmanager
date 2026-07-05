"""Tests für die Auto-Zuteilung: Seemeilen-Erfahrung, Konflikt-Robustheit,
Boot-Fixierung (📌), Berechtigungen.

Szenario-Basis: 3 Boote à 10 Betten, 30 Personen (3 Skipper fest je Boot,
27 Crew), 7 Personen schließen Person X aus.
"""
import json
from datetime import timedelta, date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import ManuellerSeemeilenEintrag
from boote.models import Boot, Kabine
from utils.seemeilen import stufe_aus_meilen, erfahrungs_stufe, seemeilen_map
from .models import Toern, Teilnahme, CrewPraeferenz, KabinenWunsch

User = get_user_model()

MEILEN = [0, 0, 0, 0, 50, 100, 150, 200, 250, 300, 400, 500, 600, 700,
          800, 1000, 1200, 1500, 1800, 2000, 2500, 3000, 3500, 4000, 4500, 5000, 5000]


class AutoAssignBase(TestCase):

    def _user(self, email, meilen=0):
        u = User.objects.create(email=email, username=email, email_verified=True)
        if meilen:
            ManuellerSeemeilenEintrag.objects.create(
                user=u, beschreibung="Vorerfahrung", meilen=meilen, datum=date(2024, 6, 1)
            )
        return u

    def _setup(self, x_zuerst=True):
        gruppe, _ = Group.objects.get_or_create(name="Anbieter")
        self.anbieter = self._user("anbieter@test.de")
        self.anbieter.groups.add(gruppe)

        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ANMELDUNG_GESCHLOSSEN",
        )
        self.boote = []
        for i in range(3):
            b = Boot.objects.create(name=f"Boot {i+1}", typ="Bavaria 46", toern=self.toern)
            for k in range(5):
                Kabine.objects.create(boot=b, name=f"K{k+1}", betten=2)
            self.boote.append(b)

        self.skipper = []
        for i, b in enumerate(self.boote):
            s = self._user(f"skipper{i+1}@test.de", meilen=8000)
            Teilnahme.objects.create(
                toern=self.toern, user=s, rolle="skipper", status="bestaetigt",
                boot=b, seglerische_erfahrung="5",
            )
            self.skipper.append(s)

        self.crew = []

        def add_crew(idx, email):
            u = self._user(email, meilen=MEILEN[idx])
            Teilnahme.objects.create(
                toern=self.toern, user=u, rolle="crew", status="bestaetigt",
                seglerische_erfahrung="1",  # Erfahrung soll aus den Seemeilen kommen
            )
            self.crew.append(u)
            return u

        if x_zuerst:
            self.x = add_crew(13, "problem@test.de")
        self.ausschliesser = []
        for j in range(26):
            u = add_crew(j if j < 13 else j + 1, f"crew{j+1}@test.de")
            if len(self.ausschliesser) < 7:
                self.ausschliesser.append(u)
        if not x_zuerst:
            self.x = add_crew(13, "problem@test.de")

        for a in self.ausschliesser:
            CrewPraeferenz.objects.create(
                toern=self.toern, from_user=a, to_user=self.x, typ="exclude"
            )

    def _run(self, payload=None, als=None):
        self.client.force_login(als or self.skipper[0])
        return self.client.post(
            reverse("auto_assign", args=[self.toern.id]),
            data=json.dumps(payload or {"experience_mode": "mixed", "age_mode": "ignore",
                                        "gender_mode": "ignore", "balance": True}),
            content_type="application/json",
        )

    def _boot_von(self, user):
        return Teilnahme.objects.get(toern=self.toern, user=user).boot

    def _keine_ausschluss_verletzung(self):
        x_boot = self._boot_von(self.x)
        for a in self.ausschliesser:
            self.assertNotEqual(self._boot_von(a), x_boot,
                                f"{a.email} ist mit X auf {x_boot}")


class SeemeilenErfahrungTests(TestCase):
    def test_stufen_grenzen(self):
        self.assertEqual(stufe_aus_meilen(0), 1)
        self.assertEqual(stufe_aus_meilen(99), 1)
        self.assertEqual(stufe_aus_meilen(100), 2)
        self.assertEqual(stufe_aus_meilen(499), 2)
        self.assertEqual(stufe_aus_meilen(500), 3)
        self.assertEqual(stufe_aus_meilen(1500), 4)
        self.assertEqual(stufe_aus_meilen(3000), 5)

    def test_seemeilen_ueberstimmen_tiefstapeln(self):
        self.assertEqual(erfahrungs_stufe(4000, "1"), 5)

    def test_selbsteinschaetzung_zaehlt_ohne_meilen(self):
        self.assertEqual(erfahrungs_stufe(0, "4"), 4)
        self.assertEqual(erfahrungs_stufe(0, None), 1)
        self.assertEqual(erfahrungs_stufe(0, "quatsch"), 1)

    def test_seemeilen_map_summiert_toern_und_logbuch(self):
        u = User.objects.create(email="sm@test.de", username="sm@test.de", email_verified=True)
        anbieter = User.objects.create(email="a@test.de", username="a@test.de", email_verified=True)
        start = timezone.now() - timedelta(days=60)
        alt_toern = Toern.objects.create(
            titel="Alter Törn", anbieter=anbieter, startdatum=start,
            enddatum=start + timedelta(days=7), revier="Ostsee",
            preis_pro_person=500, status="ABGESCHLOSSEN",
        )
        boot = Boot.objects.create(name="Altboot", typ="Yacht", toern=alt_toern, skipper_meilen=200)
        Teilnahme.objects.create(toern=alt_toern, user=u, rolle="crew",
                                 status="bestaetigt", boot=boot, individuelle_meilen=250)
        ManuellerSeemeilenEintrag.objects.create(
            user=u, beschreibung="Charter", meilen=300, datum=date(2023, 8, 1)
        )
        self.assertEqual(seemeilen_map([u.id])[u.id], 550)


class AutoAssignKernTests(AutoAssignBase):

    def test_x_zuletzt_wird_trotzdem_zugeteilt(self):
        """Der alte Greedy ließ X unzugeteilt, wenn X sich zuletzt anmeldete."""
        self._setup(x_zuerst=False)
        resp = self._run()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["unassigned"], [])
        self.assertIsNotNone(self._boot_von(self.x))
        self._keine_ausschluss_verletzung()

    def test_erfahrung_mixed_verteilt_gleichmaessig(self):
        """Boots-Durchschnitt der (Seemeilen-)Erfahrung nahe am Gesamtschnitt."""
        self._setup()
        self._run()
        alle = []
        boot_means = []
        for b in self.boote:
            ts = Teilnahme.objects.filter(toern=self.toern, boot=b).select_related("user")
            meilen = seemeilen_map([t.user_id for t in ts])
            stufen = [erfahrungs_stufe(meilen[t.user_id], t.seglerische_erfahrung) for t in ts]
            alle.extend(stufen)
            boot_means.append(sum(stufen) / len(stufen))
        global_mean = sum(alle) / len(alle)
        for m in boot_means:
            self.assertLess(abs(m - global_mean), 0.5,
                            f"Bootsschnitt {m:.2f} weicht zu stark von {global_mean:.2f} ab")

    def test_boote_gleichmaessig_gefuellt(self):
        self._setup()
        self._run()
        groessen = [Teilnahme.objects.filter(toern=self.toern, boot=b).count() for b in self.boote]
        self.assertEqual(sorted(groessen), [10, 10, 10])

    def test_alle_haben_kabinen(self):
        self._setup()
        self._run()
        self.assertEqual(
            Teilnahme.objects.filter(toern=self.toern, boot__isnull=False, kabine__isnull=True).count(), 0
        )

    def test_kabinenpaar_bleibt_zusammen(self):
        self._setup()
        a, b = self.crew[10], self.crew[20]
        KabinenWunsch.objects.create(toern=self.toern, from_user=a, to_user=b, status="accepted")
        self._run()
        ta = Teilnahme.objects.get(toern=self.toern, user=a)
        tb = Teilnahme.objects.get(toern=self.toern, user=b)
        self.assertEqual(ta.boot, tb.boot)
        self.assertEqual(ta.kabine, tb.kabine)


class AutoAssignRechteTests(AutoAssignBase):

    def test_crew_darf_nicht(self):
        self._setup()
        resp = self._run(als=self.crew[0])
        self.assertEqual(resp.status_code, 403)

    def test_anbieter_darf(self):
        self._setup()
        resp = self._run(als=self.anbieter)
        self.assertEqual(resp.status_code, 200)

    def test_fixierter_toern_blockiert(self):
        self._setup()
        self.toern.status = "ZUTEILUNG_FIXIERT"
        self.toern.save()
        resp = self._run()
        self.assertEqual(resp.status_code, 400)


class BootFixierungTests(AutoAssignBase):

    def _pin(self, user, boot):
        t = Teilnahme.objects.get(toern=self.toern, user=user)
        t.boot = boot
        t.boot_fixiert = True
        t.save()
        return t

    def test_pin_haelt_person_auf_boot(self):
        self._setup()
        gepinnt = self.crew[5]
        self._pin(gepinnt, self.boote[1])
        self._run()
        self.assertEqual(self._boot_von(gepinnt), self.boote[1])

    def test_ausschluss_meidet_boot_der_fixierten_person(self):
        """X gepinnt → alle 7 Ausschließer landen auf anderen Booten."""
        self._setup()
        self._pin(self.x, self.boote[1])
        resp = self._run()
        self.assertEqual(resp.json()["unassigned"], [])
        self.assertEqual(self._boot_von(self.x), self.boote[1])
        self._keine_ausschluss_verletzung()

    def test_paar_folgt_pin(self):
        self._setup()
        a, b = self.crew[10], self.crew[20]
        KabinenWunsch.objects.create(toern=self.toern, from_user=a, to_user=b, status="accepted")
        self._pin(a, self.boote[2])
        self._run()
        self.assertEqual(self._boot_von(a), self.boote[2])
        self.assertEqual(self._boot_von(b), self.boote[2])

    def test_paar_verschieden_fixiert_wird_getrennt_mit_warnung(self):
        self._setup()
        a, b = self.crew[10], self.crew[20]
        KabinenWunsch.objects.create(toern=self.toern, from_user=a, to_user=b, status="accepted")
        self._pin(a, self.boote[0])
        self._pin(b, self.boote[2])
        resp = self._run()
        self.assertEqual(self._boot_von(a), self.boote[0])
        self.assertEqual(self._boot_von(b), self.boote[2])
        self.assertTrue(any("getrennt" in w for w in resp.json()["warnings"]))

    def test_fixierungs_konflikt_warnung(self):
        """Zwei gegeneinander Ausgeschlossene bewusst aufs selbe Boot gepinnt → Warnung, bleiben."""
        self._setup()
        self._pin(self.x, self.boote[1])
        self._pin(self.ausschliesser[0], self.boote[1])
        resp = self._run()
        self.assertEqual(self._boot_von(self.x), self.boote[1])
        self.assertEqual(self._boot_von(self.ausschliesser[0]), self.boote[1])
        self.assertTrue(any("Fixierungs-Konflikt" in w for w in resp.json()["warnings"]))

    def test_reset_behaelt_fixierte(self):
        self._setup()
        gepinnt = self.crew[5]
        self._pin(gepinnt, self.boote[1])
        self._run()
        self.client.force_login(self.skipper[0])
        self.client.post(reverse("reset_zuteilung", args=[self.toern.id]))
        self.assertEqual(self._boot_von(gepinnt), self.boote[1])
        self.assertIsNone(self._boot_von(self.crew[6]))

    def test_pin_endpoint_toggle_und_rechte(self):
        self._setup()
        t = Teilnahme.objects.get(toern=self.toern, user=self.crew[5])

        # Ohne Boot → 400
        self.client.force_login(self.skipper[0])
        url = reverse("teilnahme_boot_fixieren", args=[self.toern.id, self.crew[5].id])
        self.assertEqual(self.client.post(url).status_code, 400)

        # Mit Boot: Toggle an
        t.boot = self.boote[0]
        t.save()
        resp = self.client.post(url, data=json.dumps({"fixiert": True}),
                                content_type="application/json")
        self.assertEqual(resp.status_code, 200)
        t.refresh_from_db()
        self.assertTrue(t.boot_fixiert)

        # Normale Crew darf nicht
        self.client.force_login(self.crew[0])
        self.assertEqual(self.client.post(url).status_code, 403)
