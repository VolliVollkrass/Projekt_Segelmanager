"""JSON-Endpoints für die Briefing-Auswahl (Briefing-Tab im Skipper-Dashboard).

Die Bausteine selbst (Text/Bild) leben global in der App `briefing` und werden
dort verwaltet (briefing/views.py). Hier geht es nur um den bootsspezifischen
Zustand: welche Bausteine sind für das Briefing dieses Boots aktiv, in welcher
Reihenfolge — plus die persönlichen Vorlagen, mit denen ein Skipper seine
Zusammenstellung von Törn zu Törn mitnimmt."""
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Max, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from boote.models import Boot
from briefing.models import BriefingBaustein, kategorie_sortierung
from .models import BriefingAuswahl, BriefingStandard, BriefingStandardEintrag, Teilnahme


def hat_briefing_recht(request, boot):
    """Skipper/Co-Skipper dieses Boots, Anbieter des Törns oder Staff.

    Enger als die törnweite Prüfung: Auf einem Flottentörn soll nicht jeder
    Skipper im Briefing eines fremden Boots herumschalten."""
    user = request.user
    if user.is_superuser or boot.toern.anbieter_id == user.id:
        return
    teilnahme = Teilnahme.objects.filter(user=user, boot=boot).first()
    if not (teilnahme and teilnahme.rolle in ("skipper", "coskipper")):
        raise PermissionDenied


def _standard_quelle(user):
    """Bausteine der Default-Vorlage des Skippers, sonst None."""
    standard = BriefingStandard.objects.filter(user=user, ist_default=True).first()
    if not standard:
        return None
    return [e.baustein for e in standard.eintraege.select_related("baustein")]


def get_or_create_briefing_auswahl(boot, user=None):
    """Beim ersten Öffnen des Briefing-Tabs eines Boots die Auswahl befüllen.

    Quelle in dieser Reihenfolge: die als Standard markierte Vorlage des Skippers,
    sonst die als Standard gekennzeichneten Bausteine der Bibliothek. Danach ist
    die Auswahl unabhängig von späteren Änderungen an Vorlage und Bibliothek."""
    if not boot.briefing_auswahl.exists():
        bausteine = _standard_quelle(user) if user else None
        if bausteine is None:
            bausteine = list(
                BriefingBaustein.objects.filter(ist_standard=True)
                .order_by(kategorie_sortierung(), "reihenfolge", "id")
            )
        BriefingAuswahl.objects.bulk_create([
            BriefingAuswahl(boot=boot, baustein=b, aktiv=True, reihenfolge=i)
            for i, b in enumerate(bausteine)
        ])
        reihenfolge_normalisieren(boot)
    return boot.briefing_auswahl.select_related("baustein").all()


def reihenfolge_normalisieren(boot):
    """Nummeriert die Auswahl neu durch, sortiert nach Kategorie-Rang und bisheriger
    Reihenfolge. Hält die Kategorie-Blöcke zusammenhängend — sonst landet ein später
    hinzugefügter Baustein am Ende der Liste statt in seiner Kategorie, und die
    Auf/Ab-Knöpfe können ihn nicht mehr bewegen, weil beide Nachbarn zu einer
    anderen Kategorie gehören."""
    rang = {code: i for i, (code, _) in enumerate(BriefingBaustein.KATEGORIE_CHOICES)}
    eintraege = sorted(
        boot.briefing_auswahl.select_related("baustein"),
        key=lambda a: (rang.get(a.baustein.kategorie, 999), a.reihenfolge, a.id),
    )
    for i, auswahl in enumerate(eintraege):
        if auswahl.reihenfolge != i:
            auswahl.reihenfolge = i
            auswahl.save(update_fields=["reihenfolge"])


def _auswahl_json(auswahl_qs):
    return [
        {
            "id": a.id,
            "baustein_id": a.baustein_id,
            "titel": a.baustein.titel,
            "kategorie": a.baustein.kategorie,
            "kategorie_label": a.baustein.get_kategorie_display(),
            "aktiv": a.aktiv,
            "reihenfolge": a.reihenfolge,
            "bild_url": a.baustein.bild.url if a.baustein.bild else None,
        }
        for a in auswahl_qs
    ]


@login_required
def briefing_liste(request, boot_id):
    boot = get_object_or_404(Boot, id=boot_id)
    hat_briefing_recht(request, boot)
    auswahl = get_or_create_briefing_auswahl(boot, user=request.user)
    return JsonResponse({"items": _auswahl_json(auswahl)})


@login_required
@require_POST
def briefing_toggle(request, boot_id, auswahl_id):
    boot = get_object_or_404(Boot, id=boot_id)
    hat_briefing_recht(request, boot)

    auswahl = get_object_or_404(BriefingAuswahl, id=auswahl_id, boot=boot)
    auswahl.aktiv = not auswahl.aktiv
    auswahl.save(update_fields=["aktiv"])
    return JsonResponse({"status": "ok", "aktiv": auswahl.aktiv})


@login_required
@require_POST
def briefing_reihenfolge(request, boot_id):
    """Neue Reihenfolge speichern. Erwartet {'ids': [auswahl_id, ...]} in Zielreihenfolge."""
    boot = get_object_or_404(Boot, id=boot_id)
    hat_briefing_recht(request, boot)

    ids = json.loads(request.body).get("ids", [])
    nach_id = {a.id: a for a in BriefingAuswahl.objects.filter(boot=boot, id__in=ids)}
    for i, aid in enumerate(ids):
        auswahl = nach_id.get(aid)
        if auswahl and auswahl.reihenfolge != i:
            auswahl.reihenfolge = i
            auswahl.save(update_fields=["reihenfolge"])
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def briefing_baustein_hinzufuegen(request, boot_id):
    boot = get_object_or_404(Boot, id=boot_id)
    hat_briefing_recht(request, boot)

    baustein = get_object_or_404(BriefingBaustein, id=json.loads(request.body).get("baustein_id"))
    auswahl, created = BriefingAuswahl.objects.get_or_create(
        boot=boot, baustein=baustein, defaults={"aktiv": True})
    if not created and not auswahl.aktiv:
        auswahl.aktiv = True
        auswahl.save(update_fields=["aktiv"])
    if created:
        # Ans Ende stellen, dann neu durchnummerieren — dadurch rutscht der Baustein
        # ans Ende seiner eigenen Kategorie statt ans Ende der ganzen Liste.
        groesste = boot.briefing_auswahl.aggregate(m=Max("reihenfolge"))["m"] or 0
        auswahl.reihenfolge = groesste + 1
        auswahl.save(update_fields=["reihenfolge"])
        reihenfolge_normalisieren(boot)
    return JsonResponse({"status": "ok", "id": auswahl.id})


@login_required
def briefing_baustein_suche(request, boot_id):
    """Bibliothek durchsuchen fürs '+ Baustein hinzufügen'-Modal — markiert, was
    für dieses Boot bereits ausgewählt ist."""
    boot = get_object_or_404(Boot, id=boot_id)
    hat_briefing_recht(request, boot)

    q = request.GET.get("q", "").strip()
    qs = BriefingBaustein.objects.all()
    if q:
        qs = qs.filter(Q(titel__icontains=q) | Q(text__icontains=q))
    qs = qs.order_by(kategorie_sortierung(), "reihenfolge", "id")[:60]

    ausgewaehlt = set(boot.briefing_auswahl.values_list("baustein_id", flat=True))
    return JsonResponse({"items": [
        {
            "id": b.id,
            "titel": b.titel,
            "kategorie_label": b.get_kategorie_display(),
            "bereits_ausgewaehlt": b.id in ausgewaehlt,
        }
        for b in qs
    ]})


# =========================
# PERSÖNLICHE BRIEFING-VORLAGEN
# =========================

def _standard_json(standard):
    return {
        "id": standard.id,
        "name": standard.name,
        "ist_default": standard.ist_default,
        "anzahl": standard.eintraege.count(),
        "aktualisiert_am": standard.aktualisiert_am.strftime("%d.%m.%Y"),
    }


@login_required
def briefing_standard_list(request):
    standards = BriefingStandard.objects.filter(user=request.user).prefetch_related("eintraege")
    return JsonResponse({"standards": [_standard_json(s) for s in standards]})


@login_required
@require_POST
def briefing_standard_speichern(request, boot_id):
    """Die aktive Auswahl dieses Boots als persönliche Vorlage sichern."""
    boot = get_object_or_404(Boot, id=boot_id)
    hat_briefing_recht(request, boot)

    name = (json.loads(request.body).get("name") or "").strip()
    if not name:
        return JsonResponse({"error": "Bitte einen Namen angeben."}, status=400)

    standard, _ = BriefingStandard.objects.get_or_create(user=request.user, name=name)
    standard.eintraege.all().delete()
    aktive = boot.briefing_auswahl.filter(aktiv=True).order_by("reihenfolge", "id")
    BriefingStandardEintrag.objects.bulk_create([
        BriefingStandardEintrag(standard=standard, baustein_id=a.baustein_id, reihenfolge=i)
        for i, a in enumerate(aktive)
    ])
    standard.save()  # aktualisiert_am nachziehen
    return JsonResponse({"status": "ok", **_standard_json(standard)})


@login_required
@require_POST
def briefing_standard_laden(request, boot_id):
    """Vorlage auf dieses Boot anwenden — ersetzt die bisherige Auswahl."""
    boot = get_object_or_404(Boot, id=boot_id)
    hat_briefing_recht(request, boot)

    standard = get_object_or_404(
        BriefingStandard, id=json.loads(request.body).get("standard_id"), user=request.user)

    boot.briefing_auswahl.all().delete()
    BriefingAuswahl.objects.bulk_create([
        BriefingAuswahl(boot=boot, baustein_id=e.baustein_id, aktiv=True, reihenfolge=i)
        for i, e in enumerate(standard.eintraege.all())
    ])
    reihenfolge_normalisieren(boot)
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def briefing_standard_loeschen(request, standard_id):
    standard = get_object_or_404(BriefingStandard, id=standard_id, user=request.user)
    standard.delete()
    return JsonResponse({"status": "ok"})


@login_required
@require_POST
def briefing_standard_default(request, standard_id):
    """Als Start-Vorlage markieren — höchstens eine pro Skipper."""
    standard = get_object_or_404(BriefingStandard, id=standard_id, user=request.user)
    standard.ist_default = not standard.ist_default
    if standard.ist_default:
        BriefingStandard.objects.filter(user=request.user).exclude(
            id=standard.id).update(ist_default=False)
    standard.save()
    return JsonResponse({"status": "ok", "ist_default": standard.ist_default})
