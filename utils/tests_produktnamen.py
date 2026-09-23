"""Tests für den Dubletten-Abgleich — Prüffälle aus einer echten Törn-Einkaufsliste."""
from django.test import SimpleTestCase

from utils.produktnamen import (
    anzeigename, normalisiere_produktname, ohne_zusatz, varianten_hinweis,
)


def gleich(a, b):
    return normalisiere_produktname(a) == normalisiere_produktname(b)


class ZusammenfuehrenTests(SimpleTestCase):
    """Diese Paare SOLLEN zusammengeführt werden."""

    def test_klammerzusatz_wird_ignoriert(self):
        self.assertTrue(gleich("Kartoffeln", "Kartoffeln (klein gewürfelt)"))
        self.assertTrue(gleich("Zwiebel", "Zwiebel (klein gewürfelt)"))
        self.assertTrue(gleich("Tellerlinsen", "Tellerlinsen (braun)"))

    def test_plural_und_singular(self):
        self.assertTrue(gleich("Kartoffel", "Kartoffeln"))
        self.assertTrue(gleich("Banane", "Bananen"))
        self.assertTrue(gleich("Tomate", "Tomaten"))
        self.assertTrue(gleich("Karotte", "Karotten"))

    def test_gross_klein_und_leerzeichen(self):
        self.assertTrue(gleich("Butter", "butter"))
        self.assertTrue(gleich("Salami", " Salami "))
        self.assertTrue(gleich("Toast  brot", "Toast brot"))

    def test_umlaut_schreibweisen(self):
        self.assertTrue(gleich("Möhre", "Mohre"))
        self.assertTrue(gleich("Käse", "Kase"))

    def test_einwort_alternativen_werden_auf_die_erste_gekuerzt(self):
        self.assertTrue(gleich("Gouda/Emmentaler", "Gouda"))
        self.assertTrue(gleich("Prosciutto oder Kochschinken", "Prosciutto"))


class NichtZusammenfuehrenTests(SimpleTestCase):
    """Diese Paare dürfen NICHT zusammengeführt werden — hier ist ein Fehler teuer."""

    def test_verschiedene_produkte_bleiben_getrennt(self):
        self.assertFalse(gleich("Salz", "Pfeffer"))
        self.assertFalse(gleich("Tomate", "Kirschtomaten"))
        self.assertFalse(gleich("Brot", "Toastbrot"))
        self.assertFalse(gleich("Apfel", "Apfelsaft"))
        self.assertFalse(gleich("Butter", "Buttermilch"))

    def test_mehrwort_alternativen_werden_nicht_gekuerzt(self):
        """„gekochter oder roher Schinken" — die erste Alternative ist ein
        Adjektiv; Kürzen ergäbe „gekochter" und damit Unsinn."""
        self.assertEqual(
            normalisiere_produktname("gekochter oder roher Schinken"),
            "gekochter oder roher schinke",
        )
        self.assertFalse(gleich("gekochter oder roher Schinken", "gekochter"))

    def test_zwei_zutaten_in_einer_zeile_bleiben_eigenstaendig(self):
        self.assertFalse(gleich("Salz", "Salz und Pfeffer"))

    def test_synonyme_bleiben_der_ki_stufe_ueberlassen(self):
        """Bewusst KEIN Treffer: solche Fälle schlägt später die KI vor,
        bestätigt werden sie vom Menschen."""
        self.assertFalse(gleich("Karotten", "Möhre"))
        self.assertFalse(gleich("Toast", "Toastbrot"))
        self.assertFalse(gleich("Käse", "Gouda"))

    def test_kurze_woerter_verlieren_kein_n(self):
        self.assertEqual(normalisiere_produktname("Huhn"), "huhn")
        self.assertFalse(gleich("Huhn", "Huh"))


class OhneZusatzTests(SimpleTestCase):
    def test_klammern_raus(self):
        self.assertEqual(
            ohne_zusatz("Olivenöl (nur falls der Speck sehr mager ist)"), "Olivenöl"
        )
        self.assertEqual(
            ohne_zusatz("Speckwürfel (alternativ Pancetta oder roher Schinken in Streifen)"),
            "Speckwürfel",
        )

    def test_schreibweise_bleibt_erhalten(self):
        self.assertEqual(ohne_zusatz("Kartoffeln (klein gewürfelt)"), "Kartoffeln")

    def test_leerer_name(self):
        self.assertEqual(ohne_zusatz(""), "")
        self.assertEqual(ohne_zusatz(None), "")
        self.assertEqual(normalisiere_produktname(None), "")


class AnzeigeTests(SimpleTestCase):
    def test_kuerzester_name_gewinnt(self):
        self.assertEqual(
            anzeigename(["Kartoffeln (klein gewürfelt)", "Kartoffeln"]), "Kartoffeln"
        )

    def test_reihenfolge_entscheidet_bei_gleichstand(self):
        self.assertEqual(anzeigename(["Gurke", "Gurkn"]), "Gurke")

    def test_verworfene_schreibweisen_bleiben_sichtbar(self):
        hinweis = varianten_hinweis(
            ["Kartoffeln", "Kartoffeln (klein gewürfelt)"], "Kartoffeln"
        )
        self.assertEqual(hinweis, "auch: Kartoffeln (klein gewürfelt)")

    def test_ohne_varianten_kein_hinweis(self):
        self.assertEqual(varianten_hinweis(["Kartoffeln"], "Kartoffeln"), "")
