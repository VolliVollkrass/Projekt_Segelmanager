"""Tests: Einkaufslisten-Generierung skaliert Rezepte korrekt auf die Boots-Crew."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from boote.models import Boot
from logistik.models import Mahlzeit, EinkaufslistenEintrag
from rezepte.models import Rezept, RezeptZutat
from utils.rezept_skalierung import summiere_mengen
from .models import Toern, Teilnahme

User = get_user_model()


def _user(email):
    return User.objects.create(email=email, username=email, email_verified=True)


class EinkaufslisteSkalierungTests(TestCase):
    def setUp(self):
        self.anbieter = _user("anbieter@test.de")
        start = timezone.now() + timedelta(days=30)
        self.toern = Toern.objects.create(
            titel="Testtörn", anbieter=self.anbieter,
            startdatum=start, enddatum=start + timedelta(days=7),
            revier="Ostsee", preis_pro_person=500, status="ZUTEILUNG_FIXIERT",
        )
        self.boot = Boot.objects.create(name="Testboot", typ="Yacht", toern=self.toern)

        # 10 bestätigte Personen auf dem Boot
        self.crew = []
        for i in range(10):
            u = _user(f"crew{i}@test.de")
            self.crew.append(Teilnahme.objects.create(
                toern=self.toern, user=u, status="bestaetigt", rolle="crew", boot=self.boot
            ))

        # Rezept für 4 Portionen
        self.rezept = Rezept.objects.create(name="Nudeln", autor=self.anbieter, portionen=4)
        RezeptZutat.objects.create(rezept=self.rezept, name="Farfalle", menge="250 g", order=1)
        RezeptZutat.objects.create(rezept=self.rezept, name="Wassermelone", menge="ca. 1 kg", order=2)
        RezeptZutat.objects.create(rezept=self.rezept, name="Minze", menge="½ Bund", order=3)
        RezeptZutat.objects.create(rezept=self.rezept, name="Pfeffer", menge="nach Belieben", order=4)

        self.datum = (start + timedelta(days=1)).date()

    def _generieren(self):
        self.client.force_login(self.crew[0].user)
        return self.client.post(
            reverse("einkaufsliste_generieren", args=[self.toern.id, self.boot.id])
        )

    def _menge(self, zutat_name):
        return EinkaufslistenEintrag.objects.get(
            boot=self.boot, toern=self.toern, name__iexact=zutat_name
        ).menge

    def test_rezept_fuer_4_wird_auf_10_personen_skaliert(self):
        Mahlzeit.objects.create(
            boot=self.boot, toern=self.toern, datum=self.datum,
            typ="abend", name="Nudeln", rezept=self.rezept,
        )
        resp = self._generieren()
        self.assertEqual(resp.status_code, 200)
        # Faktor 10/4 = 2,5
        self.assertEqual(self._menge("Farfalle"), "625 g")
        self.assertEqual(self._menge("Wassermelone"), "ca. 2,5 kg")
        self.assertEqual(self._menge("Minze"), "1,2 Bund")
        self.assertEqual(self._menge("Pfeffer"), "nach Belieben")

    def test_gleiche_zutat_aus_zwei_mahlzeiten_wird_summiert(self):
        for tag in (1, 2):
            Mahlzeit.objects.create(
                boot=self.boot, toern=self.toern,
                datum=(self.toern.startdatum + timedelta(days=tag)).date(),
                typ="abend", name="Nudeln", rezept=self.rezept,
            )
        self._generieren()
        # 2 × 625 g = 1250 g; 2 × ca. 2,5 kg = ca. 5 kg
        self.assertEqual(self._menge("Farfalle"), "1250 g")
        self.assertEqual(self._menge("Wassermelone"), "ca. 5 kg")

    def test_wasser_standard_artikel_nach_crew(self):
        self._generieren()
        self.assertEqual(self._menge("Wasser"), "50 Liter")


class SummiereMengenTests(TestCase):
    def test_summiert_pro_einheit(self):
        self.assertEqual(summiere_mengen(["250 g", "500 g"]), "750 g")

    def test_ca_wird_uebernommen(self):
        self.assertEqual(summiere_mengen(["ca. 1,5 kg", "1 kg"]), "ca. 2,5 kg")

    def test_brueche_werden_summiert(self):
        self.assertEqual(summiere_mengen(["½ Bund", "½ Bund"]), "1 Bund")

    def test_nicht_parsebares_bleibt_erhalten(self):
        self.assertEqual(summiere_mengen(["nach Belieben", "200 ml"]), "200 ml + nach Belieben")

    def test_verschiedene_einheiten_getrennt(self):
        self.assertEqual(summiere_mengen(["2 EL", "200 ml"]), "2 EL + 200 ml")
