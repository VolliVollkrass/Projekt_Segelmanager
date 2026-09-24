"""Einkaufsliste aufräumen: Dubletten zusammenführen — mit Vorschau und Rückweg.

Ablauf, bewusst in drei Schritten:
  1. Vorschau (GET)  — was würde passieren, ohne irgendetwas zu ändern
  2. Anwenden (POST) — legt ZUERST einen Snapshot an, führt dann zusammen
  3. Rückgängig (POST) — stellt den Snapshot wieder her

Der Snapshot ist kein Komfort, sondern Bedingung: Zusammenführen löscht Zeilen,
und eine Einkaufsliste, aus der auf See etwas verschwindet, fällt erst im Hafen
auf. Deshalb wird nie zusammengeführt, ohne vorher den Zustand zu sichern.
"""
import json
import uuid

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST

from boote.models import Boot
from toern.models import Teilnahme, Toern

from utils.produktnamen import anzeigename, varianten_hinweis
from utils.rezept_skalierung import summiere_mengen, zerlege_mengen

from .dubletten import fuehre_zusammen, plane_zusammenfuehrung
from .models import EinkaufslistenEintrag, EinkaufslistenSnapshot

# Felder, die eine Zeile vollständig beschreiben — der Snapshot muss sie alle
# mitnehmen, sonst ist das Zurückspielen unvollständig.
SNAPSHOT_FELDER = [
    'name', 'menge', 'kategorie', 'quelle', 'rezept_info',
    'erledigt', 'archiviert', 'erledigt_von_id', 'einkaufer_id',
]


def _zugriff(request, toern):
    if not Teilnahme.objects.filter(user=request.user, toern=toern).exists() \
            and request.user != toern.anbieter:
        raise PermissionDenied


def _hole(request, toern_id, boot_id):
    toern = get_object_or_404(Toern, id=toern_id)
    boot = get_object_or_404(Boot, id=boot_id)
    _zugriff(request, toern)
    return toern, boot


def _aktive(boot, toern):
    return EinkaufslistenEintrag.objects.filter(boot=boot, toern=toern, archiviert=False)


def _json_wert(wert):
    """JSONField verträgt keine UUIDs — der User-Primärschlüssel ist eine."""
    return str(wert) if isinstance(wert, uuid.UUID) else wert


def _snapshot_daten(boot, toern):
    """Alle aktiven Zeilen als einfache Datensätze — inklusive Zeitstempel."""
    daten = []
    for e in _aktive(boot, toern):
        zeile = {feld: _json_wert(getattr(e, feld)) for feld in SNAPSHOT_FELDER}
        zeile['id'] = e.id
        zeile['erledigt_am'] = e.erledigt_am.isoformat() if e.erledigt_am else None
        daten.append(zeile)
    return daten


@login_required
def einkaufsliste_aufraeumen_vorschau(request, toern_id, boot_id):
    """Was würde zusammengeführt? Ändert nichts."""
    toern, boot = _hole(request, toern_id, boot_id)
    gruppen = plane_zusammenfuehrung(list(_aktive(boot, toern)))

    letzter = EinkaufslistenSnapshot.objects.filter(
        boot=boot, toern=toern, zurueckgespielt_am__isnull=True
    ).first()

    return JsonResponse({
        'gruppen': [g.als_json() for g in gruppen],
        'zeilen_vorher': _aktive(boot, toern).count(),
        'zeilen_nachher': _aktive(boot, toern).count() - sum(len(g.entfernen) for g in gruppen),
        'snapshot': {
            'id': letzter.id,
            'erstellt_am': timezone.localtime(letzter.erstellt_am).strftime('%d.%m.%Y %H:%M'),
            'posten': len(letzter.daten),
        } if letzter else None,
    })


@login_required
@require_POST
def einkaufsliste_aufraeumen(request, toern_id, boot_id):
    """Zusammenführen — erst Snapshot, dann Änderung, beides in einer Transaktion."""
    toern, boot = _hole(request, toern_id, boot_id)

    with transaction.atomic():
        eintraege = list(_aktive(boot, toern).select_for_update())
        gruppen = plane_zusammenfuehrung(eintraege)
        if not gruppen:
            return JsonResponse({'ok': True, 'zusammengefuehrt': 0, 'entfernt': 0,
                                 'snapshot_id': None})

        snapshot = EinkaufslistenSnapshot.objects.create(
            boot=boot, toern=toern, erstellt_von=request.user,
            anlass='aufraeumen', daten=_snapshot_daten(boot, toern),
        )
        entfernt = fuehre_zusammen(gruppen)

    return JsonResponse({
        'ok': True,
        'zusammengefuehrt': len(gruppen),
        'entfernt': entfernt,
        'snapshot_id': snapshot.id,
        'zeilen': _aktive(boot, toern).count(),
    })


@login_required
@require_POST
def einkaufsliste_merge(request, toern_id, boot_id):
    """Ausgewählte Posten von Hand zu einem zusammenlegen.

    Die Automatik fasst nur zusammen, was sie sicher erkennt. Alles andere —
    Karotten und Möhren, Toast und Toastbrot — entscheidet hier ein Mensch:
    Er wählt die Zeilen aus, bestimmt Name und Menge und drückt zusammen.
    Auch das wird vorher gesichert und lässt sich zurücknehmen.
    """
    toern, boot = _hole(request, toern_id, boot_id)
    data = json.loads(request.body or '{}')

    ids = data.get('ids') or []
    if len(ids) < 2:
        return JsonResponse({'error': 'Bitte mindestens zwei Posten auswählen.'}, status=400)

    with transaction.atomic():
        eintraege = list(_aktive(boot, toern).filter(id__in=ids).select_for_update())
        if len(eintraege) < 2:
            return JsonResponse({'error': 'Die Auswahl ist nicht mehr aktuell.'}, status=400)

        snapshot = EinkaufslistenSnapshot.objects.create(
            boot=boot, toern=toern, erstellt_von=request.user,
            anlass='merge', daten=_snapshot_daten(boot, toern),
        )

        name = (data.get('name') or '').strip() or anzeigename([e.name for e in eintraege])
        menge = data.get('menge')
        if menge is None:
            menge = summiere_mengen([e.menge for e in eintraege])

        behalten = next((e for e in eintraege if e.name == name), eintraege[0])
        rest = [e for e in eintraege if e.id != behalten.id]

        # Rezept-Hinweise und verworfene Schreibweisen übernehmen, damit
        # nachvollziehbar bleibt, woraus der Posten entstanden ist.
        infos = []
        for e in eintraege:
            for stueck in (e.rezept_info or '').split(', '):
                if stueck and stueck not in infos:
                    infos.append(stueck)
        hinweis = varianten_hinweis([e.name for e in eintraege], name)
        text = ', '.join(infos)
        if hinweis:
            text = f"{text} · {hinweis}" if text else hinweis

        behalten.name = name[:200]
        behalten.menge = (menge or '').strip()[:100]
        behalten.rezept_info = text[:500]
        behalten.quelle = 'manuell'
        # Eigene Menge: die selbst getippte, sonst nur die manuellen Anteile.
        # Rezept- und Grundeinkauf-Anteile kommen beim Generieren neu dazu.
        if data.get('menge') is not None:
            behalten.manuelle_menge = behalten.menge
        else:
            behalten.manuelle_menge = summiere_mengen([
                teil
                for e in eintraege if e.quelle == 'manuell'
                for teil in zerlege_mengen(e.manuelle_menge or e.menge)
            ])
        behalten.erledigt = any(e.erledigt for e in eintraege)
        if not behalten.einkaufer_id:
            behalten.einkaufer_id = next((e.einkaufer_id for e in eintraege if e.einkaufer_id), None)
        behalten.save()

        for e in rest:
            e.delete()

    return JsonResponse({
        'ok': True,
        'name': behalten.name,
        'menge': behalten.menge,
        'entfernt': len(rest),
        'snapshot_id': snapshot.id,
    })


@login_required
@require_POST
def einkaufsliste_aufraeumen_undo(request, toern_id, boot_id):
    """Den letzten Snapshot zurückspielen — Zeile für Zeile, wie sie war."""
    toern, boot = _hole(request, toern_id, boot_id)

    snapshot = EinkaufslistenSnapshot.objects.filter(
        boot=boot, toern=toern, zurueckgespielt_am__isnull=True
    ).first()
    if not snapshot:
        return JsonResponse({'error': 'Kein Snapshot zum Zurückspielen vorhanden.'}, status=404)

    with transaction.atomic():
        _aktive(boot, toern).delete()

        wieder = []
        for zeile in snapshot.daten:
            felder = {feld: zeile.get(feld) for feld in SNAPSHOT_FELDER}
            wieder.append(EinkaufslistenEintrag(
                id=zeile.get('id'), boot=boot, toern=toern,
                erledigt_am=zeile.get('erledigt_am') or None,
                **felder,
            ))
        EinkaufslistenEintrag.objects.bulk_create(wieder)

        snapshot.zurueckgespielt_am = timezone.now()
        snapshot.save(update_fields=['zurueckgespielt_am'])

    return JsonResponse({'ok': True, 'wiederhergestellt': len(wieder)})
