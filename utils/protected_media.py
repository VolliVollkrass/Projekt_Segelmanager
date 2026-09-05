"""Zugriffsgeschützte Auslieferung sensibler Medien-Dateien.

Django liefert `/media/` sonst über `django.views.static.serve` komplett
unauthentifiziert aus. Für sensible Uploads (Lizenz-/Ausweis-Scans, Belege,
Logbücher, Schadensfotos) prüfen wir hier vor der Auslieferung, ob der
angemeldete Nutzer die zugehörige Datei sehen darf.

Nicht als sensibel gelistete Pfade (Profilbilder, Boot-/Törn-Bilder, Rezepte,
Segelwissen) werden wie bisher direkt ausgeliefert.

WICHTIG: Neue sensible Upload-Typen (models.FileField/ImageField) müssen unten
in SENSIBLE_PREFIXE ergänzt werden, sonst sind sie öffentlich abrufbar.
"""

from django.conf import settings
from django.http import Http404
from django.views.static import serve


def _ist_skipper(user, toern):
    from toern.models import Teilnahme
    return Teilnahme.objects.filter(
        toern=toern, user=user, rolle__in=("skipper", "coskipper")
    ).exists()


def _ist_teilnehmer(user, toern):
    from toern.models import Teilnahme
    return Teilnahme.objects.filter(toern=toern, user=user).exists()


def _darf_lizenz(user, path):
    from accounts.models import Lizenz
    from django.db.models import Q
    lizenz = Lizenz.objects.filter(
        Q(dokument_vorne=path) | Q(dokument_hinten=path)
    ).first()
    if lizenz is None:
        return False
    return lizenz.user_id == user.id or user.is_staff


def _darf_beleg(user, path):
    from finance.models import TopfBeleg
    beleg = TopfBeleg.objects.select_related("ausgabe__toern").filter(bild=path).first()
    if beleg is None:
        return False
    toern = beleg.ausgabe.toern
    return (
        user.is_staff
        or user == toern.anbieter
        or beleg.hochgeladen_von_id == user.id
        or _ist_skipper(user, toern)
    )


def _darf_toern_logbuch(user, path):
    from toern.models import Toern
    toern = Toern.objects.filter(logbuch_pdf=path).first()
    if toern is None:
        return False
    return user.is_staff or user == toern.anbieter or _ist_teilnehmer(user, toern)


def _darf_boot_logbuch(user, path):
    from boote.models import Boot
    boot = Boot.objects.select_related("toern").filter(logbuch_pdf=path).first()
    if boot is None:
        return False
    toern = boot.toern
    return user.is_staff or user == toern.anbieter or _ist_teilnehmer(user, toern)


def _darf_schadensbild(user, path):
    from toern.models import Schadensbild, Teilnahme
    bild = Schadensbild.objects.select_related(
        "meldung__boot", "meldung__toern"
    ).filter(bild=path).first()
    if bild is None:
        return False
    toern = bild.meldung.toern
    if user.is_staff or user == toern.anbieter or _ist_skipper(user, toern):
        return True
    # Sonst: Crew des betroffenen Boots
    return Teilnahme.objects.filter(
        toern=toern, boot=bild.meldung.boot, user=user
    ).exists()


# (Pfad-Präfix, Prüf-Funktion) — Reihenfolge egal, Präfixe überschneiden sich nicht.
SENSIBLE_PREFIXE = (
    ("accounts/lizenz_dokumente/", _darf_lizenz),
    ("belege/topf/", _darf_beleg),
    ("toern/logbuch/", _darf_toern_logbuch),
    ("boote/logbuch/", _darf_boot_logbuch),
    ("schaeden/", _darf_schadensbild),
)


def protected_media_serve(request, path):
    """Ersetzt `serve` für /media/: sensible Pfade werden autorisiert."""
    for prefix, darf in SENSIBLE_PREFIXE:
        if path.startswith(prefix):
            # 404 (statt 403) bei fehlender Berechtigung, damit die Existenz
            # einer Datei nicht preisgegeben wird (Enumeration-Schutz).
            if not request.user.is_authenticated or not darf(request.user, path):
                raise Http404
            break
    return serve(request, path, document_root=settings.MEDIA_ROOT)
