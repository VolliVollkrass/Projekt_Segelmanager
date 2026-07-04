"""JSON-Endpoints für die editierbaren Boots-Checklisten (Dokumente-Tab im Skipper-Dashboard)."""
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from utils.dokumente import DOKUMENT_DEFAULTS
from .models import Toern, DokumentVorlage, DokumentEintrag

DOKUMENT_TYPEN_KEYS = tuple(DOKUMENT_DEFAULTS.keys())


def get_or_create_dokument_vorlage(toern, typ):
    vorlage, created = DokumentVorlage.objects.get_or_create(toern=toern, typ=typ)
    if created:
        eintraege = []
        reihenfolge = 0
        for sektion, items in DOKUMENT_DEFAULTS[typ]:
            for text in items:
                eintraege.append(DokumentEintrag(
                    vorlage=vorlage, sektion=sektion, text=text, reihenfolge=reihenfolge
                ))
                reihenfolge += 1
        DokumentEintrag.objects.bulk_create(eintraege)
    return vorlage


def _items_json(vorlage):
    return list(vorlage.eintraege.values('id', 'sektion', 'text'))


@login_required
def dokument_items_get(request, toern_id, typ):
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    if typ not in DOKUMENT_TYPEN_KEYS:
        return JsonResponse({'error': 'Ungültiger Typ'}, status=400)

    vorlage = get_or_create_dokument_vorlage(toern, typ)
    return JsonResponse({'items': _items_json(vorlage), 'vorlage_id': vorlage.id})


@login_required
@require_POST
def dokument_item_add(request, toern_id):
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    vorlage = get_object_or_404(DokumentVorlage, id=data.get('vorlage_id'), toern=toern)
    sektion = (data.get('sektion') or '').strip()
    text = (data.get('text') or '').strip()
    if not sektion or not text:
        return JsonResponse({'error': 'Sektion und Text erforderlich'}, status=400)

    max_reihenfolge = vorlage.eintraege.aggregate(m=Max('reihenfolge'))['m'] or 0
    eintrag = DokumentEintrag.objects.create(
        vorlage=vorlage, sektion=sektion, text=text, reihenfolge=max_reihenfolge + 1
    )
    return JsonResponse({'status': 'ok', 'id': eintrag.id})


@login_required
@require_POST
def dokument_item_update(request, toern_id, item_id):
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    eintrag = get_object_or_404(DokumentEintrag, id=item_id, vorlage__toern=toern)
    data = json.loads(request.body)
    sektion = (data.get('sektion') or eintrag.sektion).strip()
    text = (data.get('text') or eintrag.text).strip()
    if not sektion or not text:
        return JsonResponse({'error': 'Sektion und Text erforderlich'}, status=400)
    eintrag.sektion = sektion
    eintrag.text = text
    eintrag.save()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def dokument_item_delete(request, toern_id, item_id):
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    eintrag = get_object_or_404(DokumentEintrag, id=item_id, vorlage__toern=toern)
    eintrag.delete()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def dokument_reset(request, toern_id):
    """Checkliste auf die Standard-Inhalte zurücksetzen."""
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    typ = data.get('typ')
    if typ not in DOKUMENT_TYPEN_KEYS:
        return JsonResponse({'error': 'Ungültiger Typ'}, status=400)

    DokumentVorlage.objects.filter(toern=toern, typ=typ).delete()
    vorlage = get_or_create_dokument_vorlage(toern, typ)
    return JsonResponse({'status': 'ok', 'items': _items_json(vorlage), 'vorlage_id': vorlage.id})
