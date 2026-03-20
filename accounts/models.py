import uuid
import os
from datetime import date

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver

from utils.image_optimizer import optimize_image
from utils.file_cleanup import delete_file


# --------------------------------------------------
# Upload Pfad Profilbild
# --------------------------------------------------

def profilbild_upload_path(instance, filename):
    ext = filename.split('.')[-1]
    filename = f"{uuid.uuid4()}.{ext}"
    return os.path.join("accounts/profilbilder", filename)


# --------------------------------------------------
# User Model
# --------------------------------------------------

class User(AbstractUser):

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    email = models.EmailField(unique=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    IDENTIFIKATIONSTYPEN = [
        ("pers", "Personalausweis"),
        ("reise", "Reisepass"),
    ]

    GESCHLECHT = [
        ("m", "Männlich"),
        ("w", "Weiblich"),
        ("d", "Divers"),
    ]

    geschlecht = models.CharField(max_length=10, choices=GESCHLECHT, default="d", blank=True)
    geburtsdatum = models.DateField(null=True, blank=True)
    geburtsort = models.CharField(max_length=100, blank=True)
    nationalitaet = models.CharField(max_length=50, blank=True)

    identifikationstyp = models.CharField(max_length=100, choices=IDENTIFIKATIONSTYPEN, default="pers")
    passnummer = models.CharField(max_length=50, blank=True)

    strasse = models.CharField(max_length=100, blank=True)
    plz = models.CharField(max_length=5, blank=True)
    ort = models.CharField(max_length=50, blank=True)

    telefonnummer = models.CharField(max_length=20, blank=True)

    profilbild = models.ImageField(
        upload_to=profilbild_upload_path,
        null=True,
        blank=True
    )

    # --------------------------------------------------
    # Save Methode
    # --------------------------------------------------

    def save(self, *args, **kwargs):

        if self.email:
            self.email = self.email.lower()

        # Bild optimieren
        if self.profilbild:
            optimized = optimize_image(self.profilbild)

            self.profilbild.save(
                self.profilbild.name,
                optimized,
                save=False
            )

        super().save(*args, **kwargs)

    # --------------------------------------------------

    def __str__(self):
        return f"{self.username} - {self.first_name} {self.last_name}"

    # --------------------------------------------------

    def alter(self):
        if self.geburtsdatum:
            today = date.today()
            return (
                today.year
                - self.geburtsdatum.year
                - ((today.month, today.day) < (self.geburtsdatum.month, self.geburtsdatum.day))
            )
        return None


# --------------------------------------------------
# Lizenz Model
# --------------------------------------------------

class Lizenz(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="lizenzen")

    name = models.CharField(max_length=100)

    ausstellungsdatum = models.DateField()

    ablaufdatum = models.DateField(null=True, blank=True)

    dokument_vorne = models.ImageField(
        upload_to="accounts/lizenz_dokumente/",
        null=True,
        blank=True
    )

    dokument_hinten = models.ImageField(
        upload_to="accounts/lizenz_dokumente/",
        null=True,
        blank=True
    )

    # --------------------------------------------------

    def save(self, *args, **kwargs):

        if self.dokument_vorne:
            optimized = optimize_image(self.dokument_vorne)

            self.dokument_vorne.save(
                self.dokument_vorne.name,
                optimized,
                save=False
            )

        if self.dokument_hinten:
            optimized = optimize_image(self.dokument_hinten)

            self.dokument_hinten.save(
                self.dokument_hinten.name,
                optimized,
                save=False
            )

        super().save(*args, **kwargs)

    # --------------------------------------------------

    def __str__(self):
        return f"{self.name} ({self.user.first_name} {self.user.last_name})"


# --------------------------------------------------
# Notizen
# --------------------------------------------------

class Notiz(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notizen")

    ersteller = models.ForeignKey(User, on_delete=models.CASCADE, related_name="erstellt_notizen")

    text = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)


# --------------------------------------------------
# Alte Bilder löschen beim Update
# --------------------------------------------------

@receiver(pre_save, sender=User)
def delete_old_profile_image(sender, instance, **kwargs):

    if not instance.pk:
        return

    try:
        old = User.objects.get(pk=instance.pk)
    except User.DoesNotExist:
        return

    if old.profilbild != instance.profilbild:
        delete_file(old.profilbild)


# --------------------------------------------------
# Bilder löschen wenn User gelöscht wird
# --------------------------------------------------

@receiver(post_delete, sender=User)
def delete_profile_image(sender, instance, **kwargs):

    delete_file(instance.profilbild)