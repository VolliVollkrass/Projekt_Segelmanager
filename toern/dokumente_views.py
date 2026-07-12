"""JSON-Endpoints für die editierbaren Boots-Checklisten (Dokumente-Tab im Skipper-Dashboard)."""
import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from boote.models import Boot
from utils.dokumente import DOKUMENT_DEFAULTS
from .models import (
    Toern, Teilnahme, DokumentVorlage, DokumentEintrag,
    DokumentAbhakstatus, DokumentStandard, DokumentStandardEintrag,
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
# DIGITALES ABHAKEN PRO BOOT (Boot-Dashboard)
# =========================

def _boot_dokument_recht(request, boot):
    """Nur Skipper/Co-Skipper dieses Boots dürfen die Checkliste abhaken."""
    t = Teilnahme.objects.filter(user=request.user, boot=boot).first()
    if not (t and t.rolle in ('skipper', 'coskipper')):
        raise PermissionDenied
    return t


def _abhak_json(status):
    """Serialisiert den Abhak-Stand für die JSON-Antwort."""
    if status and status.erledigt:
        return {
            'erledigt': True,
            'erledigt_von': status.erledigt_von.first_name if status.erledigt_von else '',
            'erledigt_am': status.erledigt_am.strftime('%d.%m.%Y %H:%M') if status.erledigt_am else '',
        }
    return {'erledigt': False, 'erledigt_von': '', 'erledigt_am': ''}


@login_required
def boot_dokument_get(request, boot_id, typ):
    """Checkliste eines Typs inkl. Abhak-Stand dieses Boots (nur Skipper/Co)."""
    boot = get_object_or_404(Boot, id=boot_id)
    _boot_dokument_recht(request, boot)

    if typ not in DOKUMENT_TYPEN_KEYS:
        return JsonResponse({'error': 'Ungültiger Typ'}, status=400)

    vorlage = get_or_create_dokument_vorlage(boot.toern, typ, user=request.user)
    status_map = {
        s.eintrag_id: s
        for s in DokumentAbhakstatus.objects
        .filter(boot=boot, eintrag__vorlage=vorlage)
        .select_related('erledigt_von')
    }
    items = [
        {'id': e.id, 'sektion': e.sektion, 'text': e.text, **_abhak_json(status_map.get(e.id))}
        for e in vorlage.eintraege.all()
    ]
    return JsonResponse({'items': items})


@login_required
@require_POST
def boot_dokument_toggle(request, boot_id, eintrag_id):
    """Häkchen eines Eintrags für dieses Boot umschalten (nur Skipper/Co)."""
    boot = get_object_or_404(Boot, id=boot_id)
    _boot_dokument_recht(request, boot)

    eintrag = get_object_or_404(DokumentEintrag, id=eintrag_id, vorlage__toern=boot.toern)
    status, _ = DokumentAbhakstatus.objects.get_or_create(boot=boot, eintrag=eintrag)
    status.erledigt = not status.erledigt
    if status.erledigt:
        status.erledigt_von = request.user
        status.erledigt_am = timezone.now()
    else:
        status.erledigt_von = None
        status.erledigt_am = None
    status.save()
    return JsonResponse({'status': 'ok', **_abhak_json(status)})


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
