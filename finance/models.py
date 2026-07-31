from django.conf import settings
from django.db import models

from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFit

from toern.models import Teilnahme, Boot, Toern


class Ausgabe(models.Model):
    """Bootskassen-Ausgabe: wird unter den Beteiligten eines Boots geteilt."""
    boot = models.ForeignKey(Boot, on_delete=models.CASCADE, related_name="ausgaben")
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="ausgaben")
    beschreibung = models.CharField(max_length=200)
    betrag = models.DecimalField(max_digits=8, decimal_places=2)
    bezahlt_von = models.ForeignKey(Teilnahme, on_delete=models.CASCADE, related_name="bezahlt_ausgaben")
    beteiligt = models.ManyToManyField(Teilnahme, related_name="beteiligte_ausgaben")
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="erfasste_ausgaben",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.beschreibung} ({self.betrag} €)"


class TopfAusgabe(models.Model):
    """Ausgabe aus dem Skipper-Topf (Budget des Anbieters für den ganzen Törn)."""

    # Buchhalterische Kategorien — Reihenfolge = Sortierung in PDF & Excel.
    KATEGORIE_VERSICHERUNG = "versicherung"
    KATEGORIE_ANREISE = "anreise"
    KATEGORIE_TREIBSTOFF = "treibstoff"
    KATEGORIE_HAFEN = "hafen"
    KATEGORIE_CHARTER = "charter"
    KATEGORIE_VERPFLEGUNG = "verpflegung"
    KATEGORIE_CREW = "crew"
    KATEGORIE_AUSRUESTUNG = "ausruestung"
    KATEGORIE_SONSTIGES = "sonstiges"

    KATEGORIE_CHOICES = [
        (KATEGORIE_VERSICHERUNG, "Skipper-Versicherungen"),
        (KATEGORIE_ANREISE, "Anreise & Unterkunft"),
        (KATEGORIE_TREIBSTOFF, "Bootstreibstoff"),
        (KATEGORIE_HAFEN, "Hafen, Liegeplatz & Abgaben"),
        (KATEGORIE_CHARTER, "Charter-Nebenkosten"),
        (KATEGORIE_VERPFLEGUNG, "Verpflegung"),
        (KATEGORIE_CREW, "Crew-Ausstattung"),
        (KATEGORIE_AUSRUESTUNG, "Ausrüstung, Material & Reparatur"),
        (KATEGORIE_SONSTIGES, "Sonstiges"),
    ]

    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="topf_ausgaben")
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="topf_ausgaben",
    )
    beschreibung = models.CharField(max_length=200)
    betrag = models.DecimalField(max_digits=8, decimal_places=2)
    kategorie = models.CharField(
        max_length=20, choices=KATEGORIE_CHOICES, default=KATEGORIE_SONSTIGES
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.beschreibung} ({self.betrag} €)"


def beleg_upload_to(instance, filename):
    return f"belege/topf/{instance.ausgabe.toern_id}/{filename}"


class TopfBeleg(models.Model):
    """Quittungs-/Belegfoto zu einer Topf-Ausgabe. Mehrere pro Ausgabe möglich
    (lange Kassenzettel → mehrere Aufnahmen)."""
    ausgabe = models.ForeignKey(
        TopfAusgabe, on_delete=models.CASCADE, related_name="belege"
    )
    bild = ProcessedImageField(
        upload_to=beleg_upload_to,
        processors=[ResizeToFit(1600, 1600)],
        format="JPEG",
        options={"quality": 80},
    )
    hochgeladen_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="hochgeladene_belege",
    )
    order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"Beleg zu {self.ausgabe_id}"
