from django.db import models
from django.conf import settings
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFill


class Rezept(models.Model):
    KATEGORIE_CHOICES = [
        ("fruehstueck", "Frühstück"),
        ("hauptgericht", "Hauptgericht"),
        ("snack", "Snack / Kleines"),
        ("dessert", "Dessert"),
        ("sonstiges", "Sonstiges"),
    ]

    autor             = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="rezepte")
    name              = models.CharField(max_length=200)
    kategorie         = models.CharField(max_length=30, choices=KATEGORIE_CHOICES, default="hauptgericht")
    bild              = ProcessedImageField(
                            upload_to="rezepte/",
                            processors=[ResizeToFill(800, 600)],
                            format="JPEG",
                            options={"quality": 82},
                            blank=True,
                            null=True,
                        )
    zubereitungszeit  = models.PositiveSmallIntegerField(help_text="Minuten", default=30)
    portionen         = models.PositiveSmallIntegerField(default=4)
    tipps             = models.TextField(blank=True)
    getraenk          = models.CharField(max_length=200, blank=True)
    quelle_url        = models.URLField(blank=True)
    erstellt_am       = models.DateTimeField(auto_now_add=True)
    aktualisiert_am   = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-erstellt_am"]

    def __str__(self):
        return self.name

    @property
    def stern_anzahl(self):
        return self.sterne.count()


class RezeptZutat(models.Model):
    rezept = models.ForeignKey(Rezept, on_delete=models.CASCADE, related_name="zutaten")
    name   = models.CharField(max_length=100)
    menge  = models.CharField(max_length=50, blank=True)
    order  = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return f"{self.menge} {self.name}".strip()


class RezeptSchritt(models.Model):
    rezept  = models.ForeignKey(Rezept, on_delete=models.CASCADE, related_name="schritte")
    nummer  = models.PositiveSmallIntegerField()
    text    = models.TextField()

    class Meta:
        ordering = ["nummer"]

    def __str__(self):
        return f"Schritt {self.nummer}: {self.text[:50]}"


class RezeptStern(models.Model):
    rezept = models.ForeignKey(Rezept, on_delete=models.CASCADE, related_name="sterne")
    user   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rezept_sterne")

    class Meta:
        unique_together = ("rezept", "user")
