"""Bordvorrat — was an Bord ohnehin da ist, muss nicht eingekauft werden.

Rezepte führen Salz, Pfeffer, Öl und Essig als Zutat auf, oft mit Mengen wie
„etwas" oder „nach Bedarf". Auf dem Einkaufszettel sind solche Posten nur
Rauschen. Wer sie hier einträgt, sieht sie beim Generieren nicht wieder.

Der Abgleich läuft über denselben normalisierten Produktnamen wie die
Dubletten-Zusammenführung — „Olivenöl (nur falls der Speck mager ist)" wird
also von einem Eintrag „Olivenöl" erfasst.
"""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from toern.models import Toern
from utils.produktnamen import normalisiere_produktname

from .models import Bordvorrat, BordvorratEintrag, EinkaufslistenEintrag

# Vorschläge beim ersten Öffnen — bewusst kurz und unstrittig. Nichts davon
# wird automatisch gesetzt; der Skipper hakt an, was auf SEIN Boot zutrifft.
VORSCHLAEGE = [
    'Salz', 'Pfeffer', 'Olivenöl', 'Sonnenblumenöl', 'Essig', 'Zucker',
    'Mehl', 'Senf', 'Ketchup', 'Gewürze',
]


def _vorrat(toern):
    vorrat, _ = Bordvorrat.objects.get_or_create(toern=toern)
    return vorrat


def bordvorrat_schluessel(toern):
    """Normalisierte Namen des Bordvorrats — für den Filter beim Generieren."""
    return {
        normalisiere_produktname(n)
        for n in BordvorratEintrag.objects.filter(vorrat__toern=toern).values_list('name', flat=True)
        if normalisiere_produktname(n)
    }


@login_required
def bordvorrat_get(request, toern_id):
    from toern.views import _hat_skipper_oder_anbieter

    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    eintraege = list(_vorrat(toern).eintraege.values('id', 'name', 'notiz'))
    vorhandene = {normalisiere_produktname(e['name']) for e in eintraege}
    return JsonResponse({
        'items': eintraege,
        'vorschlaege': [
            v for v in VORSCHLAEGE if normalisiere_produktname(v) not in vorhandene
        ],
    })


@login_required
@require_POST
def bordvorrat_add(request, toern_id):
    from toern.views import _hat_skipper_oder_anbieter

    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    data = json.loads(request.body or '{}')
    name = (data.get('name') or '').strip()
    if not name:
        return JsonResponse({'error': 'Name fehlt'}, status=400)

    vorrat = _vorrat(toern)
    schluessel = normalisiere_produktname(name)
    schon_da = any(
        normalisiere_produktname(e.name) == schluessel for e in vorrat.eintraege.all()
    )
    if schon_da:
        return JsonResponse({'error': f'„{name}" steht schon im Bordvorrat.'}, status=400)

    eintrag = BordvorratEintrag.objects.create(
        vorrat=vorrat, name=name, notiz=(data.get('notiz') or '').strip(),
    )

    # Wenn gewünscht, den Posten gleich von den aktiven Einkaufslisten nehmen.
    # Ohne dieses Häkchen bleibt die laufende Liste unangetastet.
    entfernt = 0
    if data.get('von_liste_entfernen'):
        for e in EinkaufslistenEintrag.objects.filter(toern=toern, archiviert=False):
            if normalisiere_produktname(e.name) == schluessel:
                e.delete()
                entfernt += 1

    return JsonResponse({'ok': True, 'id': eintrag.id, 'name': eintrag.name,
                         'entfernt': entfernt})


@login_required
@require_POST
def bordvorrat_delete(request, toern_id, item_id):
    from toern.views import _hat_skipper_oder_anbieter

    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    eintrag = get_object_or_404(BordvorratEintrag, id=item_id, vorrat__toern=toern)
    eintrag.delete()
    return JsonResponse({'ok': True})
