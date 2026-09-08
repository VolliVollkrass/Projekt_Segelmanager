from django.conf import settings
from django.db import models
from django.db.models import Case, When
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFit


class BriefingBaustein(models.Model):
    """Ein Baustein im wachsenden Erfahrungsbuch für Skipper-Briefings.

    Global geteilt (wie das Segelkochbuch): jeder Skipper/Co-Skipper/Anbieter
    kann Bausteine beitragen und jeden bestehenden Baustein direkt verbessern
    (kollaboratives Bearbeiten). Törns wählen daraus per BriefingAuswahl
    (toern/models.py) unabhängig aus, was tatsächlich verwendet wird.
    """

    KATEGORIE_CHOICES = [
        ("kommunikation", "Kommunikation & Kommando"),
        ("orientierung", "Orientierung an Bord"),
        ("sicherheit", "Sicherheit"),
        ("leinen", "Leinen & Knoten"),
        ("ablegen", "Ablegen"),
        ("anlegen", "Anlegen"),
        ("segeln", "Unter Segeln"),
        ("bordalltag", "Leben an Bord"),
        ("sonstiges", "Sonstiges"),
    ]

    titel = models.CharField(max_length=200)
    kategorie = models.CharField(max_length=20, choices=KATEGORIE_CHOICES, default="sonstiges")
    text = models.TextField()
    bild = ProcessedImageField(
        upload_to="briefing/",
        processors=[ResizeToFit(1200, 1200)],
        format="JPEG",
        options={"quality": 85},
        blank=True,
        null=True,
    )
    BILD_POSITION_CHOICES = [
        ("unten", "Unter dem Text"),
        ("oben", "Über dem Text"),
        ("links", "Links neben dem Text"),
        ("rechts", "Rechts neben dem Text"),
    ]
    bild_position = models.CharField(
        max_length=10, choices=BILD_POSITION_CHOICES, default="unten",
        help_text="Wo das Bild relativ zum Text steht — im PDF und in der Leseansicht",
    )
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="briefing_bausteine",
    )
    zuletzt_bearbeitet_von = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="+",
    )
    ist_standard = models.BooleanField(
        default=False,
        help_text="Wird bei neuen Törns automatisch ins Briefing übernommen",
    )
    reihenfolge = models.PositiveSmallIntegerField(default=0)
    erstellt_am = models.DateTimeField(auto_now_add=True)
    aktualisiert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kategorie", "reihenfolge", "id"]
        verbose_name = "Briefing-Baustein"
        verbose_name_plural = "Briefing-Bausteine"

    def __str__(self):
        return self.titel


def kategorie_sortierung():
    """Case/When-Ausdruck für QuerySet.order_by(): sortiert nach der fachlichen
    Reihenfolge aus BriefingBaustein.KATEGORIE_CHOICES (Kommunikation zuerst,
    Sonstiges zuletzt) statt alphabetisch nach dem Kategorie-Code."""
    return Case(*[
        When(kategorie=code, then=i)
        for i, (code, _) in enumerate(BriefingBaustein.KATEGORIE_CHOICES)
    ])
