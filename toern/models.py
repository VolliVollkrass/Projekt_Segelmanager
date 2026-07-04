from django.db import models

from django.conf import settings
from boote.models import Boot, Kabine
from django.db.models import Sum
from django.utils import timezone

import os
import uuid

from utils.image_optimizer import optimize_image
from utils.file_cleanup import delete_file

class Toern(models.Model):
    STATUS_CHOICES = [
        ("DRAFT", "Entwurf"),
        ("ANMELDUNG_OFFEN", "Anmeldung offen"),
        ("ANMELDUNG_GESCHLOSSEN", "Anmeldung geschlossen"),
        ("ZUTEILUNG_VORGESCHLAGEN", "Zuweisung vorgeschlagen"),
        ("ZUTEILUNG_FIXIERT", "Zuteilung abgeschlossen"),
        ("ABGESCHLOSSEN", "Abgeschlossen"),
    ]

    titel = models.CharField(max_length=200)
    anbieter = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="angebotene_toerns"
    )
    startdatum = models.DateTimeField()
    enddatum = models.DateTimeField()
    anmeldeschluss = models.DateTimeField(null=True, blank=True)
    revier = models.CharField(max_length=200)
    preis_pro_person = models.DecimalField(max_digits=8, decimal_places=2)
    nebenkosten = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="DRAFT")
    beschreibung = models.TextField(blank=True)
    kurzbeschreibung = models.CharField(max_length=500, blank=True)
    bild_toern = models.ImageField(upload_to='toern/bilder/', blank=True, null=True)
    foto_upload_link = models.URLField(blank=True)
    foto_download_link = models.URLField(blank=True)
    logbuch_pdf = models.FileField(upload_to='toern/logbuch/', blank=True, null=True)
    tagesimpulse_aktiv = models.BooleanField(default=True, verbose_name="Tagesthema & Impulse aktiv")

    PACKLISTE_REVIER_CHOICES = [
        ('warm', 'Warm (Mittelmeer)'),
        ('kalt', 'Kalt (Nordsee)'),
    ]
    packliste_revier_typ = models.CharField(
        max_length=10,
        choices=PACKLISTE_REVIER_CHOICES,
        default='warm',
        verbose_name="Segelgebiet Packliste",
    )

    ist_privat = models.BooleanField(
        default=False,
        verbose_name="Privater Törn",
        help_text="Nur über den geheimen Einladungslink erreichbar, nicht öffentlich gelistet",
    )
    privat_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    skipper_budget = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        default=0,
        verbose_name="Skipper-Topf (€)",
        help_text="Budget für Skipper/Co-Skipper (z.B. Crewshirts, Fahrtkosten, Crew-Essen)",
    )

    PRAEFERENZ_MODUS_CHOICES = [
        ("alle", "Beide Präferenztypen"),
        ("nur_ausschluss", "Nur Ausschlüsse"),
        ("keiner", "Deaktiviert"),
    ]
    praeferenz_modus = models.CharField(
        max_length=20,
        choices=PRAEFERENZ_MODUS_CHOICES,
        default="alle",
        verbose_name="Kabinenpartner-Präferenzen",
    )

    def save(self, *args, **kwargs):
        self.update_status_by_deadline()

        try:
            old = Toern.objects.get(pk=self.pk)
        except Toern.DoesNotExist:
            old = None

        if old and old.bild_toern != self.bild_toern:
            delete_file(old.bild_toern)

        if old and old.logbuch_pdf != self.logbuch_pdf:
            delete_file(old.logbuch_pdf)

        if self.bild_toern and (not old or old.bild_toern != self.bild_toern):
            optimized = optimize_image(self.bild_toern)

            filename = os.path.basename(self.bild_toern.name)

            self.bild_toern.save(
                filename,
                optimized,
                save=False
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.titel} ({self.startdatum.strftime('%Y-%m-%d')} - {self.enddatum.strftime('%Y-%m-%d')})"
    
    @property
    def gesamtplaetze(self):
        # Use annotation from queryset if available (avoids extra DB query)
        if hasattr(self, '_gesamtplaetze'):
            return self._gesamtplaetze
        return self.boote.aggregate(
            total=Sum('kabinen__betten')
        )['total'] or 0

    @property
    def freie_plaetze(self):
        # Use annotations from queryset if available (avoids 2 extra DB queries per toern)
        if hasattr(self, '_gesamtplaetze') and hasattr(self, '_belegte_plaetze'):
            return max(0, self._gesamtplaetze - self._belegte_plaetze)
        belegte_plaetze = self.teilnahmen.filter(status__in=['angemeldet', 'bestaetigt']).count()
        return max(0, self.gesamtplaetze - belegte_plaetze)
    
    @property
    def gesamtpreis(self):
        """
        Berechnet die ungefähren Gesamtkosten pro Person.
        """
        return self.preis_pro_person + self.nebenkosten
    
    @property
    def is_anmeldung_offen(self):
        if self.anmeldeschluss and timezone.now() > self.anmeldeschluss:
            return False
        return self.status == "ANMELDUNG_OFFEN"

    def update_status_by_deadline(self):
        if self.anmeldeschluss and timezone.now() > self.anmeldeschluss:
            if self.status == "ANMELDUNG_OFFEN":
                self.status = "ANMELDUNG_GESCHLOSSEN"

class Teilnahme(models.Model):
    ROLE_CHOICES = [
        ("skipper", "Skipper"),
        ("coskipper", "Co-Skipper"),
        ("crew", "Crew"),
    ]

    STATUS_CHOICES = [
        ("angemeldet", "Angemeldet"),
        ("warteliste", "Warteliste"),
        ("bestaetigt", "Bestätigt"),
        ("abgesagt", "Abgesagt"),
        ("abgelehnt", "Abgelehnt"),
    ]

    SEGELERFAHRUNG_CHOICES = [
        ("1", "Landratte"),
        ("2", "Mitsegler*in"),
        ("3", "Crew"),
        ("4", "Steuermann*frau"),
        ("5", "Skipper*in"),
    ]

    GROESSE_CHOICES = [
        ("XS", "XS"),
        ("S", "S"),
        ("M", "M"),
        ("L", "L"),
        ("XL", "XL"),
        ("XXL", "XXL"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="teilnahmen")
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="teilnahmen")
    rolle = models.CharField(max_length=20, choices=ROLE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="angemeldet")
    boot = models.ForeignKey(Boot, null=True, blank=True, on_delete=models.SET_NULL, related_name="teilnahmen")
    kabine = models.ForeignKey(Kabine, null=True, blank=True, on_delete=models.SET_NULL, related_name="teilnahmen")
    wunschpartner = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="wunschpartner_teilnahmen")
    ausschlussliste = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name="ausgeschlossen_teilnahmen")
    individuelle_meilen = models.PositiveIntegerField(null=True, blank=True)
    seglerische_erfahrung = models.CharField(max_length=30, choices=SEGELERFAHRUNG_CHOICES, default="1")
    notizen = models.TextField(blank=True)  # private Notizen für Skipper/Admin
    teilnahmebedingungen_akzeptiert = models.BooleanField(default=False)
    notfallkontakt_name = models.CharField(max_length=100, blank=True)
    notfallkontakt_telefon = models.CharField(max_length=20, blank=True)
    notfallkontakt_email = models.EmailField(blank=True)
    ESSGEWOHNHEITEN_CHOICES = [
        ("alles", "Kein Fleischverzicht"),
        ("vegetarisch", "Vegetarisch"),
        ("vegan", "Vegan"),
    ]

    essgewohnheiten = models.CharField(
        max_length=20,
        choices=ESSGEWOHNHEITEN_CHOICES,
        blank=True,
        default=""
    )
    lebensmittelunvertraeglichkeiten = models.TextField(blank=True)
    allergien = models.TextField(blank=True)
    tshirt_groesse = models.CharField(max_length=5, choices=GROESSE_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "toern"], name="unique_user_toern")
        ]

    def __str__(self):
        return f"{self.user.username} - {self.toern.titel}"

class KabinenWunsch(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
    ]

    toern = models.ForeignKey("Toern", on_delete=models.CASCADE)

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kabinen_anfragen_gesendet"
    )

    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kabinen_anfragen_erhalten"
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("toern", "from_user", "to_user")

    def __str__(self):
        return f"{self.from_user} → {self.to_user} ({self.status})"
    
class CrewPraeferenz(models.Model):
    PRAEF_CHOICES = [
        ("exclude", "Ausschluss"),
        ("avoid", "Wenn möglich vermeiden"),
    ]

    toern = models.ForeignKey("Toern", on_delete=models.CASCADE)

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="praeferenzen_gesendet"
    )

    to_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="praeferenzen_erhalten"
    )

    typ = models.CharField(max_length=10, choices=PRAEF_CHOICES)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("toern", "from_user", "to_user")

    def __str__(self):
        return f"{self.from_user} -> {self.to_user} ({self.typ})"


class PacklisteVorlage(models.Model):
    toern = models.ForeignKey(
        'Toern',
        on_delete=models.CASCADE,
        related_name='packliste_vorlagen'
    )
    typ = models.CharField(max_length=10, choices=[('personal', 'Persönlich'), ('boot', 'Boot'), ('skipper', 'Skipper')])

    class Meta:
        unique_together = [('toern', 'typ')]

    def __str__(self):
        return f"{self.get_typ_display()} – {self.toern}"


class PacklisteVorlageEintrag(models.Model):
    vorlage = models.ForeignKey(PacklisteVorlage, on_delete=models.CASCADE, related_name='eintraege')
    name = models.CharField(max_length=255)
    menge = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.menge}x {self.name}"


class PacklisteStandard(models.Model):
    """Persönliche, benannte Packlisten-Standards eines Skippers — törnunabhängig wiederverwendbar."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='packliste_standards'
    )
    name = models.CharField(max_length=100)
    typ = models.CharField(max_length=10, choices=[('personal', 'Persönlich'), ('boot', 'Boot'), ('skipper', 'Skipper')])
    ist_default = models.BooleanField(
        default=False,
        help_text="Wird bei neuen Törns automatisch als Start-Vorlage verwendet (max. einer pro Typ)"
    )
    aktualisiert_am = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [('user', 'typ', 'name')]

    def __str__(self):
        return f"{self.name} ({self.get_typ_display()}) – {self.user}"


class PacklisteStandardEintrag(models.Model):
    standard = models.ForeignKey(PacklisteStandard, on_delete=models.CASCADE, related_name='eintraege')
    name = models.CharField(max_length=255)
    menge = models.PositiveIntegerField(default=1)

    def __str__(self):
        return f"{self.menge}x {self.name}"


class PinnwandNachricht(models.Model):
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="pinnwand_nachrichten")
    autor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pinnwand_nachrichten"
    )
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.autor.first_name} @ {self.toern.titel} ({self.created_at:%d.%m.%Y})"


class Mitfahrangebot(models.Model):
    TYP_CHOICES = [
        ("angebot", "Mitfahrangebot"),
        ("gesuch", "Mitfahrgesuch"),
    ]

    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="mitfahrangebote")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mitfahrangebote")
    typ = models.CharField(max_length=10, choices=TYP_CHOICES)
    abfahrtsort = models.CharField(max_length=200)
    abfahrtszeit = models.DateTimeField(null=True, blank=True)
    freie_plaetze = models.PositiveSmallIntegerField(null=True, blank=True)
    anmerkung = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_typ_display()} von {self.user.first_name} ({self.abfahrtsort})"

    @property
    def belegte_plaetze(self):
        return self.anfragen.filter(status="accepted").count()

    @property
    def verbleibende_plaetze(self):
        if self.freie_plaetze is None:
            return None
        return max(0, self.freie_plaetze - self.belegte_plaetze)


class Mitfahrtanfrage(models.Model):
    STATUS_CHOICES = [
        ("pending", "Angefragt"),
        ("accepted", "Bestätigt"),
        ("rejected", "Abgelehnt"),
    ]

    angebot = models.ForeignKey(Mitfahrangebot, on_delete=models.CASCADE, related_name="anfragen")
    anfragender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="mitfahrt_anfragen"
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("angebot", "anfragender")
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.anfragender.first_name} → {self.angebot} ({self.status})"


class ErinnerungsMailLog(models.Model):
    toern = models.ForeignKey(Toern, on_delete=models.CASCADE, related_name="erinnerungsmails")
    empfaenger = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="erinnerungsmails_erhalten",
    )
    gesendet_am = models.DateTimeField(auto_now_add=True)
    fehlende_felder = models.TextField(blank=True)

    class Meta:
        ordering = ["-gesendet_am"]

    def __str__(self):
        return f"{self.empfaenger} — {self.toern} ({self.gesendet_am:%d.%m.%Y %H:%M})"