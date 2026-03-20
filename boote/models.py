from django.db import models
from utils.image_optimizer import optimize_image
from utils.file_cleanup import delete_file

class Charterunternehmen(models.Model):
    name = models.CharField(max_length=100)
    internetseite = models.URLField(blank=True)
    email = models.EmailField(blank=True)
    telefonnummer = models.CharField(max_length=20, blank=True)
    adresse = models.TextField(blank=True)

    def __str__(self):
        return f"{self.name} - {self.internetseite}"

class Boot(models.Model):
    name = models.CharField(max_length=100)
    typ = models.CharField(max_length=100)
    charterunternehmen = models.ForeignKey(Charterunternehmen, on_delete=models.SET_NULL, null=True, related_name="boote")
    Hafen = models.CharField(max_length=100, blank=True)
    Hafen_googlemaps = models.CharField(max_length=100, blank=True)  # für Google Maps Suche
    baujahr = models.PositiveIntegerField(blank=True, null=True)
    laenge = models.FloatField(blank=True, null=True)
    tiefe = models.FloatField(blank=True, null=True)
    preis = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    bild_boot = models.ImageField(upload_to='boote/bilder/', blank=True, null=True)

    def save(self, *args, **kwargs):

        try:
            old = Boot.objects.get(pk=self.pk)
        except Boot.DoesNotExist:
            old = None

        if old:
            if old.bild_boot != self.bild_boot:
                delete_file(old.bild_boot)

        if self.bild_boot:
            optimized = optimize_image(self.bild_boot)

            self.bild_boot.save(
                self.bild_boot.name,
                optimized,
                save=False
            )

        super().save(*args, **kwargs)
    def __str__(self):
        return self.name

class Kabine(models.Model):
    boot = models.ForeignKey(Boot, on_delete=models.CASCADE, related_name="kabinen")
    name = models.CharField(max_length=50)
    betten = models.PositiveIntegerField(default=2)

    def __str__(self):
        return f"{self.boot.name} - {self.name}"