from django.conf import settings
from django.db import models

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
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="topf_ausgaben")
    erstellt_von = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="topf_ausgaben",
    )
    beschreibung = models.CharField(max_length=200)
    betrag = models.DecimalField(max_digits=8, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.beschreibung} ({self.betrag} €)"
