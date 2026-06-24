import re
from django.db import models
from imagekit.models import ProcessedImageField
from imagekit.processors import ResizeToFit


class Knoten(models.Model):
    SCHWIERIGKEIT_CHOICES = [
        ('leicht', 'Leicht'),
        ('mittel', 'Mittel'),
        ('schwer', 'Schwer'),
    ]

    name             = models.CharField(max_length=200)
    beschreibung     = models.TextField()
    bild             = ProcessedImageField(
                           upload_to='segelwissen/knoten/',
                           processors=[ResizeToFit(900, 900)],
                           format='JPEG',
                           options={'quality': 85},
                           blank=True,
                           null=True,
                       )
    schwierigkeitsgrad = models.CharField(
        max_length=10,
        choices=SCHWIERIGKEIT_CHOICES,
        default='mittel',
    )
    reihenfolge      = models.PositiveSmallIntegerField(default=0, help_text='Sortierreihenfolge (aufsteigend)')
    erstellt_am      = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['reihenfolge', 'name']
        verbose_name = 'Knoten'
        verbose_name_plural = 'Knoten'

    def __str__(self):
        return self.name


class Segelinformation(models.Model):
    KATEGORIE_CHOICES = [
        ('wetter', 'Wetter'),
        ('seemannschaft', 'Seemannschaft'),
        ('navigation', 'Navigation'),
        ('sicherheit', 'Sicherheit'),
        ('sonstiges', 'Sonstiges'),
    ]

    titel        = models.CharField(max_length=200)
    text         = models.TextField()
    bild         = ProcessedImageField(
                       upload_to='segelwissen/infos/',
                       processors=[ResizeToFit(1200, 800)],
                       format='JPEG',
                       options={'quality': 85},
                       blank=True,
                       null=True,
                   )
    kategorie    = models.CharField(max_length=20, choices=KATEGORIE_CHOICES, default='sonstiges')
    reihenfolge  = models.PositiveSmallIntegerField(default=0)
    erstellt_am  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['reihenfolge', 'titel']
        verbose_name = 'Segelinformation'
        verbose_name_plural = 'Segelinformationen'

    def __str__(self):
        return self.titel


class Segelvideo(models.Model):
    titel        = models.CharField(max_length=200)
    beschreibung = models.TextField(blank=True)
    youtube_url  = models.URLField(help_text='YouTube-URL (z. B. https://www.youtube.com/watch?v=...)')
    reihenfolge  = models.PositiveSmallIntegerField(default=0)
    erstellt_am  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['reihenfolge', 'titel']
        verbose_name = 'Segelvideo'
        verbose_name_plural = 'Segelvideos'

    def __str__(self):
        return self.titel

    @property
    def embed_url(self):
        url = self.youtube_url
        # youtu.be/ID
        match = re.search(r'youtu\.be/([A-Za-z0-9_-]{11})', url)
        if match:
            return f'https://www.youtube-nocookie.com/embed/{match.group(1)}'
        # watch?v=ID
        match = re.search(r'[?&]v=([A-Za-z0-9_-]{11})', url)
        if match:
            return f'https://www.youtube-nocookie.com/embed/{match.group(1)}'
        # already an embed URL → replace with nocookie
        match = re.search(r'youtube\.com/embed/([A-Za-z0-9_-]{11})', url)
        if match:
            return f'https://www.youtube-nocookie.com/embed/{match.group(1)}'
        return url
