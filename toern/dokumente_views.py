"""JSON-Endpoints für die editierbaren Boots-Checklisten (Dokumente-Tab im Skipper-Dashboard)."""
import json

from django.contrib.auth.decorators import login_required
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from utils.dokumente import DOKUMENT_DEFAULTS
from .models import (
    Toern, DokumentVorlage, DokumentEintrag,
    DokumentStandard, DokumentStandardEintrag,
)

DOKUMENT_TYPEN_KEYS = tuple(DOKUMENT_DEFAULTS.keys())


def get_or_create_dokument_vorlage(toern, typ, user=None):
    """Törn-Checkliste holen oder anlegen. Quelle beim Anlegen (in dieser Reihenfolge):
    Default-Standard des Users (falls Skipper/Co-Skipper/Anbieter des Törns),
    sonst die statischen Standard-Inhalte."""
    vorlage, created = DokumentVorlage.objects.get_or_create(toern=toern, typ=typ)
    if created:
        source = None
        if user is not None:
            from .views import _ist_skipper_oder_anbieter
            if _ist_skipper_oder_anbieter(user, toern):
                default = DokumentStandard.objects.filter(user=user, typ=typ, ist_default=True).first()
                if default:
                    source = list(default.eintraege.values_list('sektion', 'text'))
        if source is None:
            source = [
                (sektion, text)
                for sektion, items in DOKUMENT_DEFAULTS[typ]
                for text in items
            ]
        DokumentEintrag.objects.bulk_create([
            DokumentEintrag(vorlage=vorlage, sektion=sektion, text=text, reihenfolge=i)
            for i, (sektion, text) in enumerate(source)
        ])
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

    vorlage = get_or_create_dokument_vorlage(toern, typ, user=request.user)
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


# =========================
# PERSÖNLICHE CHECKLISTEN-STANDARDS
# =========================

@login_required
def dok_standard_list(request):
    typ = request.GET.get('typ')
    if typ not in DOKUMENT_TYPEN_KEYS:
        return JsonResponse({'error': 'Ungültiger Typ'}, status=400)
    standards = [
        {'id': s.id, 'name': s.name, 'ist_default': s.ist_default, 'anzahl': s.eintraege.count()}
        for s in DokumentStandard.objects.filter(user=request.user, typ=typ).order_by('name')
    ]
    return JsonResponse({'standards': standards})


@login_required
@require_POST
def dok_standard_speichern(request, toern_id):
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    typ = data.get('typ')
    name = (data.get('name') or '').strip()
    ist_default = bool(data.get('ist_default', False))

    if typ not in DOKUMENT_TYPEN_KEYS:
        return JsonResponse({'error': 'Ungültiger Typ'}, status=400)
    if not name:
        return JsonResponse({'error': 'Name fehlt'}, status=400)

    vorlage = get_or_create_dokument_vorlage(toern, typ, user=request.user)
    standard, created = DokumentStandard.objects.get_or_create(user=request.user, typ=typ, name=name)
    standard.eintraege.all().delete()
    DokumentStandardEintrag.objects.bulk_create([
        DokumentStandardEintrag(standard=standard, sektion=s, text=t, reihenfolge=i)
        for i, (s, t) in enumerate(vorlage.eintraege.values_list('sektion', 'text'))
    ])
    if ist_default:
        DokumentStandard.objects.filter(user=request.user, typ=typ).exclude(id=standard.id).update(ist_default=False)
    standard.ist_default = ist_default
    standard.save()
    return JsonResponse({'status': 'ok', 'id': standard.id, 'created': created})


@login_required
@require_POST
def dok_standard_laden(request, toern_id):
    from .views import _hat_skipper_oder_anbieter
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body)
    standard = get_object_or_404(DokumentStandard, id=data.get('standard_id'), user=request.user)

    vorlage, _ = DokumentVorlage.objects.get_or_create(toern=toern, typ=standard.typ)
    vorlage.eintraege.all().delete()
    DokumentEintrag.objects.bulk_create([
        DokumentEintrag(vorlage=vorlage, sektion=s, text=t, reihenfolge=i)
        for i, (s, t) in enumerate(standard.eintraege.values_list('sektion', 'text'))
    ])
    return JsonResponse({'status': 'ok', 'typ': standard.typ})


@login_required
@require_POST
def dok_standard_loeschen(request, standard_id):
    standard = get_object_or_404(DokumentStandard, id=standard_id, user=request.user)
    standard.delete()
    return JsonResponse({'status': 'ok'})


@login_required
@require_POST
def dok_standard_default(request, standard_id):
    standard = get_object_or_404(DokumentStandard, id=standard_id, user=request.user)
    standard.ist_default = not standard.ist_default
    if standard.ist_default:
        DokumentStandard.objects.filter(user=request.user, typ=standard.typ).exclude(id=standard.id).update(ist_default=False)
    standard.save()
    return JsonResponse({'status': 'ok', 'ist_default': standard.ist_default})
