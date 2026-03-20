from django.db import models
from django.conf import settings
from boote.models import Boot, Kabine
from django.db.models import Sum

from utils.image_optimizer import optimize_image
from utils.file_cleanup import delete_file

class Toern(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Entwurf"),
        ("ANMELDUNG_OFFEN", "Anmeldung offen"),
        ("ANMELDUNG_GESCHLOSSEN", "Anmeldung geschlossen"),
        ("ZUTEILUNG_VORGESCHLAGEN", "Zuweisung vorgeschlagen"),
        ("VEROEFFENTLICHT", "Veröffentlicht"),
        ("ABGESCHLOSSEN", "Abgeschlossen"),
    ]

    titel = models.CharField(max_length=200)
    startdatum = models.DateTimeField()
    enddatum = models.DateTimeField()
    revier = models.CharField(max_length=200)
    preis_pro_person = models.DecimalField(max_digits=8, decimal_places=2)
    nebenkosten = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="DRAFT")
    boote = models.ManyToManyField(Boot, related_name="toerns")
    beschreibung = models.TextField(blank=True)
    kurzbeschreibung = models.CharField(max_length=500, blank=True)
    bild_toern = models.ImageField(upload_to='toern/bilder/', blank=True, null=True)

    def save(self, *args, **kwargs):

        try:
            old = Toern.objects.get(pk=self.pk)
        except Toern.DoesNotExist:
            old = None

        if old:
            if old.bild_toern != self.bild_toern:
                delete_file(old.bild_toern)

        if self.bild_toern:
            optimized = optimize_image(self.bild_toern)

            self.bild_toern.save(
                self.bild_toern.name,
                optimized,
                save=False
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.titel} ({self.startdatum.strftime('%Y-%m-%d')} - {self.enddatum.strftime('%Y-%m-%d')})"
    
    @property
    def gesamtplaetze(self):
        """
        Berechnet die Gesamtzahl aller Betten der Boote, die diesem Törn zugeordnet sind.
        """
        return self.boote.aggregate(
            total=Sum('kabinen__betten')
        )['total'] or 0

    @property
    def freie_plaetze(self):
        """
        Berechnet die noch freien Plätze anhand der Gesamtplätze minus angemeldete Teilnehmer.
        """
        belegte_plaetze = self.teilnahmen.filter(status__in=['angemeldet', 'bestaetigt']).count()
        return max(0, self.gesamtplaetze - belegte_plaetze)
    
    @property
    def gesamtpreis(self):
        """
        Berechnet die ungefähren Gesamtkosten pro Person.
        """
        return self.preis_pro_person + self.nebenkosten

class Teilnahme(models.Model):
    ROLE_CHOICES = [
        ("skipper", "Skipper"),
        ("co_skp", "Co-Skipper"),
        ("crew", "Crew"),
        ("anbieter", "Anbieter"),
        ("admin", "Admin")
    ]

    STATUS_CHOICES = [
        ("angemeldet", "Angemeldet"),
        ("warteliste", "Warteliste"),
        ("bestaetigt", "Bestätigt"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teilnahmen")
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="teilnahmen")
    rolle = models.CharField(max_length=20, choices=ROLE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="angemeldet")
    boot = models.ForeignKey(Boot, null=True, blank=True, on_delete=models.SET_NULL, related_name="teilnahmen")
    kabine = models.ForeignKey(Kabine, null=True, blank=True, on_delete=models.SET_NULL, related_name="teilnahmen")
    wunschpartner = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="wunschpartner_teilnahmen")
    ausschlussliste = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="ausgeschlossen_teilnahmen")
    notizen = models.TextField(blank=True)  # private Notizen für Skipper/Admin
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "toern")  # nur 1 Teilnahme pro Törn

    def __str__(self):
        return f"{self.user.username} - {self.toern.titel}"