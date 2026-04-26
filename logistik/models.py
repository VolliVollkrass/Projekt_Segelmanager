from django.db import models
from toern.models import Teilnahme, Boot, Toern

# Einkaufsliste pro Boot/Törn
class Einkaufspunkt(models.Model):
    boot = models.ForeignKey(Boot, on_delete=models.CASCADE, related_name="einkaufsliste")
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="einkaufsliste")
    name = models.CharField(max_length=200)
    menge = models.CharField(max_length=50, blank=True)
    verantwortlich = models.ForeignKey(Teilnahme, null=True, blank=True, on_delete=models.SET_NULL)
    erledigt = models.BooleanField(default=False)

# Boot-Gemeinschafts-Packliste
class Gegenstand(models.Model):
    boot = models.ForeignKey(Boot, on_delete=models.CASCADE, related_name="gegenstaende")
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="gegenstaende")
    name = models.CharField(max_length=200)
    menge = models.PositiveIntegerField(default=1)

class Mitbringer(models.Model):
    gegenstand = models.ForeignKey(Gegenstand, on_delete=models.CASCADE, related_name="mitbringer")
    participation = models.ForeignKey(Teilnahme, on_delete=models.CASCADE)
    menge = models.PositiveIntegerField(default=1)

# Persönliche Packliste
class PersönlicherGegenstand(models.Model):
    participation = models.ForeignKey(Teilnahme, on_delete=models.CASCADE, related_name="persoenliche_packliste")
    name = models.CharField(max_length=200)
    menge = models.PositiveIntegerField(default=1)
    erledigt = models.BooleanField(default=False)
    ist_vom_boot = models.BooleanField(default=False)