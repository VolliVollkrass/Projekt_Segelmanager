"""JSON-Endpoints für die Briefing-Auswahl (Briefing-Tab im Skipper-Dashboard).

Die Bausteine selbst (Text/Bild) leben global in der App `briefing` und werden
dort verwaltet (briefing/views.py). Hier geht es nur um den törn-spezifischen
Zustand: welche Bausteine sind für dieses Törn-Briefing aktiv, in welcher
Reihenfolge."""
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from briefing.models import BriefingBaustein, kategorie_sortierung
from .models import Toern, BriefingAuswahl


def get_or_create_briefing_auswahl(toern):
    """Beim ersten Öffnen des Briefing-Tabs eines Törns: Standard-Bausteine übernehmen.
    Danach ist die Auswahl unabhängig — spätere Änderungen an ist_standard in der
    globalen Bibliothek wirken sich nicht rückwirkend auf bereits konfigurierte
    Törns aus (gleiches Verhalten wie Packliste/Dokumente-Vorlagen)."""
    if not toern.briefing_auswahl.exists():
        standard_bausteine = (
            BriefingBaustein.objects.filter(ist_standard=True)
            .order_by(kategorie_sortierung(), 'reihenfolge', 'id')
        )
        BriefingAuswahl.objects.bulk_create([
            BriefingAuswahl(toern=toern, baustein=b, aktiv=True, reihenfolge=i)
            for i, b in enumerate(standard_bausteine)
        ])
    return toern.briefing_auswahl.select_related('baustein').all()


def _auswahl_json(auswahl_qs):
    return [
        {
            'id': a.id,
            'baustein_id': a.baustein_id,
            'titel': a.baustein.titel,
            'kategorie': a.baustein.kategorie,
            'kategorie_label': a.baustein.get_kategorie_display(),
            'aktiv': a.aktiv,
            'reihenfolge': a.reihenfolge,
            'bild_url': a.baustein.bild.url if a.baustein.bild else None,
        }
        for a in auswahl_qs
    ]


@login_required
def briefing_liste(request, toern_id):
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    auswahl = get_or_create_briefing_auswahl(toern)
    return JsonResponse({'items': _auswahl_json(auswahl)})


@login_required
@require_POST
def briefing_toggle(request, toern_id, auswahl_id):
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    auswahl = get_object_or_404(BriefingAuswahl, id=auswahl_id, toern=toern)
    auswahl.aktiv = not auswahl.aktiv
    auswahl.save(update_fields=['aktiv'])
    return JsonResponse({'status': 'ok', 'aktiv': auswahl.aktiv})


@login_required
@require_POST
def briefing_reihenfolge(request, toern_id):
    """Neue Reihenfolge speichern. Erwartet {'ids': [auswahl_id, ...]} in Zielreihenfolge."""
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    ids = data.get('ids', [])
    auswahl_by_id = {a.id: a for a in BriefingAuswahl.objects.filter(toern=toern, id__in=ids)}
    for i, aid in enumerate(ids):
        auswahl = auswahl_by_id.get(aid)
        if auswahl and auswahl.reihenfolge != i:
            auswahl.reihenfolge = i
            auswahl.save(update_fields=['reihenfolge'])
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def briefing_baustein_hinzufuegen(request, toern_id):
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    baustein = get_object_or_404(BriefingBaustein, id=data.get('baustein_id'))

    auswahl, created = BriefingAuswahl.objects.get_or_create(
        toern=toern, baustein=baustein,
        defaults={'aktiv': True},
    )
    if not created and not auswahl.aktiv:
        auswahl.aktiv = True
        auswahl.save(update_fields=['aktiv'])
    if created:
        max_reihenfolge = toern.briefing_auswahl.aggregate(m=Max('reihenfolge'))['m'] or 0
        auswahl.reihenfolge = max_reihenfolge + 1
        auswahl.save(update_fields=['reihenfolge'])

    return JsonResponse({'status': 'ok', 'id': auswahl.id})


@login_required
def briefing_baustein_suche(request, toern_id):
    """Bibliothek durchsuchen fürs '+ Baustein hinzufügen'-Modal — markiert, was
    für diesen Törn bereits ausgewählt ist."""
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    q = request.GET.get('q', '').strip()
    qs = BriefingBaustein.objects.all()
    if q:
        from django.db.models import Q
        qs = qs.filter(Q(titel__icontains=q) | Q(text__icontains=q))
    qs = qs.order_by(kategorie_sortierung(), 'reihenfolge', 'id')[:60]

    bereits_ausgewaehlt = set(toern.briefing_auswahl.values_list('baustein_id', flat=True))
    return JsonResponse({
        'items': [
            {
                'id': b.id,
                'titel': b.titel,
                'kategorie_label': b.get_kategorie_display(),
                'bereits_ausgewaehlt': b.id in bereits_ausgewaehlt,
            }
            for b in qs
        ]
    })
