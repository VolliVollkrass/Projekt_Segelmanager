from django.db import models
from django.conf import settings


class Andacht(models.Model):

    TYP_CHOICES = [
        ('morgen', 'Morgenandacht'),
        ('abend', 'Abendandacht'),
    ]

    ZIELGRUPPE_CHOICES = [
        ('maritim', 'Maritime Andacht'),
        ('kinder', 'Kinder'),
        ('jugendliche', 'Jugendliche'),
        ('junge_erwachsene', 'Junge Erwachsene'),
        ('erwachsene', 'Erwachsene'),
        ('gemischt', 'Gemischt / Alle'),
    ]

    STIL_CHOICES = [
        ('', 'Kein Vorgabe'),
        ('meditativ', 'Meditativ'),
        ('erzaehlend', 'Erzählend'),
        ('liturgisch', 'Liturgisch'),
    ]

    KIRCHENJAHR_CHOICES = [
        ('', 'Keine Angabe'),
        ('advent', 'Advent'),
        ('weihnacht', 'Weihnacht'),
        ('passion', 'Passion / Fastenzeit'),
        ('ostern', 'Ostern'),
        ('pfingsten', 'Pfingsten'),
        ('normale_zeit', 'Trinitatiszeit / Normale Zeit'),
    ]

    # --- Eingabe ---
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='andachten')
    typ = models.CharField(max_length=10, choices=TYP_CHOICES)
    zielgruppe = models.CharField(max_length=20, choices=ZIELGRUPPE_CHOICES)
    dauer_minuten = models.PositiveIntegerField()
    thema = models.CharField(max_length=300)
    stichpunkte = models.TextField(blank=True)
    kontext = models.TextField(blank=True)
    bibelstelle_eingabe = models.CharField(max_length=100, blank=True)
    tageslosung_verwendet = models.BooleanField(default=False)
    kirchenjahr = models.CharField(max_length=20, choices=KIRCHENJAHR_CHOICES, blank=True)
    stil = models.CharField(max_length=20, choices=STIL_CHOICES, blank=True)
    eigener_liedwunsch = models.CharField(max_length=200, blank=True)

    # --- Optionen ---
    mit_liedern = models.BooleanField(default=True)
    mit_gespraechsimpulsen = models.BooleanField(default=True)
    mit_geschichte = models.BooleanField(default=True)
    mit_gebeten = models.BooleanField(default=True)

    # --- KI-Ergebnis ---
    titel = models.CharField(max_length=300, blank=True)
    bibelstelle = models.CharField(max_length=100, blank=True)
    bibeltext = models.TextField(blank=True)
    exegese = models.TextField(blank=True)
    einstieg = models.TextField(blank=True)
    entfaltung = models.TextField(blank=True)
    abschluss = models.TextField(blank=True)
    geschichte = models.TextField(blank=True)
    geschichte_quelle = models.CharField(max_length=300, blank=True)
    lieder_json = models.TextField(blank=True)
    gebete_json = models.TextField(blank=True)
    gespraechsimpulse_json = models.TextField(blank=True)

    erstellt_am = models.DateTimeField(auto_now_add=True)

    # --- Andachtsbuch ---
    veroeffentlicht = models.BooleanField(
        default=False,
        help_text="Im Andachtsbuch für alle eingeloggten Nutzer sichtbar"
    )
    veroeffentlicht_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-erstellt_am']
        verbose_name = 'Andacht'
        verbose_name_plural = 'Andachten'

    def __str__(self):
        return f"{self.get_typ_display()} – {self.titel or self.thema} ({self.user})"

    def lieder(self):
        import json
        try:
            return json.loads(self.lieder_json) if self.lieder_json else []
        except (json.JSONDecodeError, TypeError):
            return []

    def gebete(self):
        import json
        try:
            return json.loads(self.gebete_json) if self.gebete_json else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def gespraechsimpulse(self):
        import json
        try:
            return json.loads(self.gespraechsimpulse_json) if self.gespraechsimpulse_json else []
        except (json.JSONDecodeError, TypeError):
            return []
