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
    
    def __str__(self):
        return f"{self.name} ({self.menge}) - {self.boot.name} / {self.toern.titel}"

class Mitbringer(models.Model):
    gegenstand = models.ForeignKey(Gegenstand, on_delete=models.CASCADE, related_name="mitbringer")
    participation = models.ForeignKey(Teilnahme, on_delete=models.CASCADE)
    menge = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.participation.user.username} bringt {self.menge}x {self.gegenstand.name} mit"

# Mahlzeitenplanung pro Boot/Törn
class Mahlzeit(models.Model):
    TYP_CHOICES = [
        ("fruehstueck", "Frühstück"),
        ("mittag", "Mittagessen"),
        ("abend", "Abendessen"),
        ("essen_gehen", "Essen gehen"),
        ("snack", "Snack"),
    ]

    boot = models.ForeignKey(Boot, on_delete=models.CASCADE, related_name="mahlzeiten")
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="mahlzeiten")
    datum = models.DateField()
    typ = models.CharField(max_length=20, choices=TYP_CHOICES)
    name = models.CharField(max_length=200)
    kochverantwortlich = models.ForeignKey(
        Teilnahme, null=True, blank=True, on_delete=models.SET_NULL, related_name="mahlzeiten"
    )

    class Meta:
        ordering = ["datum", "typ"]

    def __str__(self):
        return f"{self.get_typ_display()} am {self.datum}: {self.name}"


# Tagesplan: Tagesthema
class Tagesthema(models.Model):
    boot = models.ForeignKey(Boot, on_delete=models.CASCADE, related_name='tagesthemen')
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name='tagesthemen')
    datum = models.DateField()
    thema = models.CharField(max_length=300, blank=True)

    class Meta:
        unique_together = ('boot', 'toern', 'datum')


# Tagesplan: Aufgaben pro Tag
class Tagesaufgabe(models.Model):
    TYP_CHOICES = [
        ('abwasch', 'Abwasch'),
        ('navigation', 'Navigation'),
        ('abfahrtsprotokoll', 'Abfahrtsprotokoll'),
        ('einkauf', 'Einkauf / Proviant'),
        ('hafenwache', 'Hafenwache'),
        ('reinigung', 'Reinigung / Aufräumen'),
        ('sonstiges', 'Sonstiges'),
    ]

    boot = models.ForeignKey(Boot, on_delete=models.CASCADE, related_name='tagesaufgaben')
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name='tagesaufgaben')
    datum = models.DateField()
    typ = models.CharField(max_length=30, choices=TYP_CHOICES, default='abwasch')
    beschreibung = models.CharField(max_length=200, blank=True)
    verantwortlich = models.ForeignKey(
        Teilnahme, null=True, blank=True, on_delete=models.SET_NULL, related_name='aufgaben'
    )

    class Meta:
        ordering = ['datum', 'typ']


# Tagesplan: Impulse pro Tag
class Tagesimpuls(models.Model):
    SLOT_CHOICES = [
        ('vormittag', 'Vormittag'),
        ('nachmittag', 'Nachmittag'),
    ]

    boot = models.ForeignKey(Boot, on_delete=models.CASCADE, related_name='tagesimpulse')
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name='tagesimpulse')
    datum = models.DateField()
    slot = models.CharField(max_length=20, choices=SLOT_CHOICES)
    thema = models.CharField(max_length=200)
    verantwortlich = models.ForeignKey(
        Teilnahme, null=True, blank=True, on_delete=models.SET_NULL, related_name='impulse'
    )

    class Meta:
        ordering = ['datum', 'slot']
        unique_together = ('boot', 'toern', 'datum', 'slot')


# Tagesplan: Bearbeitungsrechte für Crew-Mitglieder
class TagesplanBearbeitungsrecht(models.Model):
    boot = models.ForeignKey(Boot, on_delete=models.CASCADE, related_name='tagesplan_rechte')
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name='tagesplan_rechte')
    teilnahme = models.ForeignKey(Teilnahme, on_delete=models.CASCADE, related_name='tagesplan_rechte')

    class Meta:
        unique_together = ('boot', 'toern', 'teilnahme')


# Persönliche Packliste
class PersönlicherGegenstand(models.Model):
    participation = models.ForeignKey(Teilnahme, on_delete=models.CASCADE, related_name="persoenliche_packliste")
    name = models.CharField(max_length=200)
    menge = models.PositiveIntegerField(default=1)
    erledigt = models.BooleanField(default=False)
    ist_vom_boot = models.BooleanField(default=False)

    def __str__(self):        
        return f"Von {self.participation.user.username}: {self.name} ({self.menge})  - {'vom Boot' if self.ist_vom_boot else 'persönlich'}"