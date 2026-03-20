from django.db import models
from toern.models import Teilnahme, Boot, Toern

class Ausgabe(models.Model):
    boot = models.ForeignKey(Boot, on_delete=models.CASCADE, related_name="ausgaben")
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="ausgaben")
    beschreibung = models.CharField(max_length=200)
    betrag = models.DecimalField(max_digits=8, decimal_places=2)
    bezahlt_von = models.ForeignKey(Teilnahme, on_delete=models.CASCADE, related_name="bezahlt_ausgaben")
    beteiligt = models.ManyToManyField(Teilnahme, related_name="beteiligte_ausgaben")
    created_at = models.DateTimeField(auto_now_add=True)