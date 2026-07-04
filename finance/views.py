from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from boote.models import Boot
from toern.models import Teilnahme, Toern
from .models import Ausgabe, TopfAusgabe


def _parse_betrag(raw):
    """Betrag aus dem Formular parsen (Komma oder Punkt), None wenn ungültig."""
    try:
        betrag = Decimal(str(raw).strip().replace(",", ".")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    except (InvalidOperation, AttributeError):
        return None
    if betrag <= 0:
        return None
    return betrag


def _ist_toern_skipper(user, toern):
    return Teilnahme.objects.filter(
        toern=toern, user=user, rolle__in=("skipper", "coskipper")
    ).exists()


# ───────────────────────── Bootskasse ─────────────────────────

@login_required
@require_POST
def ausgabe_erstellen(request, toern_id, boot_id):
    toern = get_object_or_404(Toern, id=toern_id)
    boot = get_object_or_404(Boot, id=boot_id, toern=toern)

    meine_teilnahme = Teilnahme.objects.filter(
        toern=toern, boot=boot, user=request.user, status="bestaetigt"
    ).first()
    if not meine_teilnahme:
        raise PermissionDenied

    kasse_url = f"{reverse('boot_dashboard', args=[toern.id])}?tab=kasse"

    beschreibung = request.POST.get("beschreibung", "").strip()
    betrag = _parse_betrag(request.POST.get("betrag"))
    bezahlt_von_id = request.POST.get("bezahlt_von")
    beteiligt_ids = request.POST.getlist("beteiligt")

    if not beschreibung or betrag is None:
        messages.error(request, "Bitte Beschreibung und einen gültigen Betrag angeben.")
        return redirect(kasse_url)

    zahler = Teilnahme.objects.filter(
        id=bezahlt_von_id, toern=toern, boot=boot, status="bestaetigt"
    ).first()
    if not zahler:
        messages.error(request, "Ungültiger Zahler.")
        return redirect(kasse_url)

    beteiligte = Teilnahme.objects.filter(
        id__in=beteiligt_ids, toern=toern, boot=boot, status="bestaetigt"
    )
    if not beteiligte.exists():
        messages.error(request, "Bitte mindestens eine beteiligte Person auswählen.")
        return redirect(kasse_url)

    ausgabe = Ausgabe.objects.create(
        boot=boot,
        toern=toern,
        beschreibung=beschreibung,
        betrag=betrag,
        bezahlt_von=zahler,
        erstellt_von=request.user,
    )
    ausgabe.beteiligt.set(beteiligte)

    messages.success(request, f"Ausgabe „{beschreibung}“ ({betrag} €) gespeichert.")
    return redirect(kasse_url)


@login_required
@require_POST
def ausgabe_bearbeiten(request, ausgabe_id):
    ausgabe = get_object_or_404(
        Ausgabe.objects.select_related("toern", "boot", "bezahlt_von__user"),
        id=ausgabe_id,
    )
    toern, boot = ausgabe.toern, ausgabe.boot

    darf_bearbeiten = (
        request.user == ausgabe.erstellt_von
        or request.user == ausgabe.bezahlt_von.user
        or request.user == toern.anbieter
        or _ist_toern_skipper(request.user, toern)
    )
    if not darf_bearbeiten:
        raise PermissionDenied

    kasse_url = f"{reverse('boot_dashboard', args=[toern.id])}?tab=kasse"

    beschreibung = request.POST.get("beschreibung", "").strip()
    betrag = _parse_betrag(request.POST.get("betrag"))
    bezahlt_von_id = request.POST.get("bezahlt_von")
    beteiligt_ids = request.POST.getlist("beteiligt")

    if not beschreibung or betrag is None:
        messages.error(request, "Bitte Beschreibung und einen gültigen Betrag angeben.")
        return redirect(kasse_url)

    zahler = Teilnahme.objects.filter(
        id=bezahlt_von_id, toern=toern, boot=boot, status="bestaetigt"
    ).first()
    if not zahler:
        messages.error(request, "Ungültiger Zahler.")
        return redirect(kasse_url)

    beteiligte = Teilnahme.objects.filter(
        id__in=beteiligt_ids, toern=toern, boot=boot, status="bestaetigt"
    )
    if not beteiligte.exists():
        messages.error(request, "Bitte mindestens eine beteiligte Person auswählen.")
        return redirect(kasse_url)

    ausgabe.beschreibung = beschreibung
    ausgabe.betrag = betrag
    ausgabe.bezahlt_von = zahler
    ausgabe.save()
    ausgabe.beteiligt.set(beteiligte)

    messages.success(request, f"Ausgabe „{beschreibung}“ aktualisiert.")
    return redirect(kasse_url)


@login_required
@require_POST
def ausgabe_loeschen(request, ausgabe_id):
    ausgabe = get_object_or_404(
        Ausgabe.objects.select_related("toern", "boot", "bezahlt_von__user"),
        id=ausgabe_id,
    )
    toern = ausgabe.toern

    darf_loeschen = (
        request.user == ausgabe.erstellt_von
        or request.user == ausgabe.bezahlt_von.user
        or request.user == toern.anbieter
        or _ist_toern_skipper(request.user, toern)
    )
    if not darf_loeschen:
        raise PermissionDenied

    ausgabe.delete()
    messages.success(request, "Ausgabe gelöscht.")
    return redirect(f"{reverse('boot_dashboard', args=[toern.id])}?tab=kasse")


# ───────────────────────── Skipper-Topf ─────────────────────────

@login_required
@require_POST
def topf_ausgabe_erstellen(request, toern_id):
    toern = get_object_or_404(Toern, id=toern_id)

    if request.user != toern.anbieter and not _ist_toern_skipper(request.user, toern):
        raise PermissionDenied

    kasse_url = f"{reverse('skipper_dashboard', args=[toern.id])}?tab=kasse"

    beschreibung = request.POST.get("beschreibung", "").strip()
    betrag = _parse_betrag(request.POST.get("betrag"))

    if not beschreibung or betrag is None:
        messages.error(request, "Bitte Beschreibung und einen gültigen Betrag angeben.")
        return redirect(kasse_url)

    TopfAusgabe.objects.create(
        toern=toern,
        erstellt_von=request.user,
        beschreibung=beschreibung,
        betrag=betrag,
    )

    messages.success(request, f"Topf-Ausgabe „{beschreibung}“ ({betrag} €) gespeichert.")
    return redirect(kasse_url)


@login_required
@require_POST
def topf_ausgabe_loeschen(request, ausgabe_id):
    ausgabe = get_object_or_404(
        TopfAusgabe.objects.select_related("toern"), id=ausgabe_id
    )
    toern = ausgabe.toern

    darf_loeschen = (
        request.user == ausgabe.erstellt_von
        or request.user == toern.anbieter
        or _ist_toern_skipper(request.user, toern)
    )
    if not darf_loeschen:
        raise PermissionDenied

    ausgabe.delete()
    messages.success(request, "Topf-Ausgabe gelöscht.")
    return redirect(f"{reverse('skipper_dashboard', args=[toern.id])}?tab=kasse")
