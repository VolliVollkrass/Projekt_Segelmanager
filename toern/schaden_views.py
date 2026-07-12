"""Schadensprotokoll pro Boot — CRUD, Status-Umschalten, Bild-Löschen.

Zugriff wie beim Boot-Dashboard: bestätigte Teilnahme, die diesem Boot zugeteilt ist,
und Törn im Status ZUTEILUNG_FIXIERT. Die ganze Boots-Crew darf lesen, anlegen und
jeden Eintrag bearbeiten. Löschen darf nur der Autor oder Skipper/Co-Skipper des Boots.
"""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from boote.models import Boot
from .forms import SchadensmeldungForm
from .models import Schadensbild, Schadensmeldung, Teilnahme

MAX_BILDER = 5

# Gültige Status-Keys für schnelle Validierung des Umschaltens
STATUS_KEYS = {key for key, _ in Schadensmeldung.STATUS_CHOICES}


def _boot_crew_teilnahme(request, boot):
    """Teilnahme des Users an diesem Boot holen oder 403.

    Spiegelt die Boot-Dashboard-Freigabe: bestätigt, diesem Boot zugeteilt,
    Törn ZUTEILUNG_FIXIERT.
    """
    teilnahme = Teilnahme.objects.filter(
        user=request.user, toern=boot.toern, boot=boot
    ).first()
    if not (
        teilnahme
        and teilnahme.status == "bestaetigt"
        and boot.toern.status == "ZUTEILUNG_FIXIERT"
    ):
        raise PermissionDenied
    return teilnahme


def _darf_loeschen(user, meldung, teilnahme):
    """Nur der Autor des Eintrags oder Skipper/Co-Skipper des Boots."""
    return meldung.erstellt_von_id == user.id or teilnahme.rolle in ("skipper", "coskipper")


def _bilder_speichern(meldung, dateien):
    """Neue Fotos anhängen, ohne die 5er-Grenze zu überschreiten.

    Gibt die Zahl der wegen der Grenze verworfenen Bilder zurück.
    """
    frei = MAX_BILDER - meldung.bilder.count()
    verworfen = 0
    for datei in dateien:
        if frei <= 0:
            verworfen += 1
            continue
        Schadensbild.objects.create(meldung=meldung, bild=datei)
        frei -= 1
    return verworfen


@login_required
def schaden_neu(request, boot_id):
    boot = get_object_or_404(Boot, id=boot_id)
    teilnahme = _boot_crew_teilnahme(request, boot)

    if request.method == "POST":
        form = SchadensmeldungForm(request.POST)
        if form.is_valid():
            meldung = form.save(commit=False)
            meldung.boot = boot
            meldung.toern = boot.toern
            meldung.erstellt_von = request.user
            meldung.geaendert_von = request.user
            meldung.save()
            verworfen = _bilder_speichern(meldung, request.FILES.getlist("bilder"))
            if verworfen:
                messages.warning(request, f"Es sind max. {MAX_BILDER} Fotos möglich – {verworfen} wurde(n) nicht gespeichert.")
            messages.success(request, "Schaden gemeldet.")
            return redirect(f"/toern/{boot.toern.id}/boot/?tab=schaden")
    else:
        form = SchadensmeldungForm()

    return render(request, "boot/schaden_form.html", {
        "form": form,
        "boot": boot,
        "toern": boot.toern,
        "teilnahme": teilnahme,
        "meldung": None,
        "max_bilder": MAX_BILDER,
    })


@login_required
def schaden_bearbeiten(request, meldung_id):
    meldung = get_object_or_404(Schadensmeldung.objects.select_related("boot", "toern"), id=meldung_id)
    boot = meldung.boot
    teilnahme = _boot_crew_teilnahme(request, boot)

    if request.method == "POST":
        form = SchadensmeldungForm(request.POST, instance=meldung)
        if form.is_valid():
            meldung = form.save(commit=False)
            meldung.geaendert_von = request.user
            meldung.save()
            verworfen = _bilder_speichern(meldung, request.FILES.getlist("bilder"))
            if verworfen:
                messages.warning(request, f"Es sind max. {MAX_BILDER} Fotos möglich – {verworfen} wurde(n) nicht gespeichert.")
            messages.success(request, "Schaden aktualisiert.")
            return redirect(f"/toern/{boot.toern.id}/boot/?tab=schaden")
    else:
        form = SchadensmeldungForm(instance=meldung)

    return render(request, "boot/schaden_form.html", {
        "form": form,
        "boot": boot,
        "toern": boot.toern,
        "teilnahme": teilnahme,
        "meldung": meldung,
        "max_bilder": MAX_BILDER,
        "darf_loeschen": _darf_loeschen(request.user, meldung, teilnahme),
    })


@login_required
@require_POST
def schaden_loeschen(request, meldung_id):
    meldung = get_object_or_404(Schadensmeldung.objects.select_related("boot", "toern"), id=meldung_id)
    boot = meldung.boot
    teilnahme = _boot_crew_teilnahme(request, boot)
    if not _darf_loeschen(request.user, meldung, teilnahme):
        raise PermissionDenied
    # Erst die Bild-Dateien via Schadensbild.delete() entfernen, dann die Meldung.
    # (DB-CASCADE würde die Zeilen löschen, aber nicht die Dateien auf der Platte.)
    for bild in list(meldung.bilder.all()):
        bild.delete()
    meldung.delete()
    messages.success(request, "Schaden gelöscht.")
    return redirect(f"/toern/{boot.toern.id}/boot/?tab=schaden")


@login_required
@require_POST
def schaden_status(request, meldung_id):
    """Status eines Schadens setzen (AJAX). Die ganze Boots-Crew darf das."""
    meldung = get_object_or_404(Schadensmeldung.objects.select_related("boot", "toern"), id=meldung_id)
    teilnahme = _boot_crew_teilnahme(request, meldung.boot)

    neuer_status = request.POST.get("status", "")
    if neuer_status not in STATUS_KEYS:
        return JsonResponse({"error": "Ungültiger Status"}, status=400)

    meldung.status = neuer_status
    meldung.geaendert_von = request.user
    meldung.save(update_fields=["status", "geaendert_von", "geaendert_am"])
    return JsonResponse({
        "status": neuer_status,
        "label": meldung.get_status_display(),
        "farbe": meldung.status_farbe,
    })


@login_required
@require_POST
def schaden_bild_loeschen(request, bild_id):
    """Einzelnes Foto löschen (während Bearbeiten). Wer bearbeiten darf, darf löschen = ganze Crew."""
    bild = get_object_or_404(Schadensbild.objects.select_related("meldung__boot__toern"), id=bild_id)
    _boot_crew_teilnahme(request, bild.meldung.boot)
    meldung = bild.meldung
    meldung.geaendert_von = request.user
    meldung.save(update_fields=["geaendert_von", "geaendert_am"])
    bild.delete()
    return JsonResponse({"status": "ok"})
