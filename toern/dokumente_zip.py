"""Gebündelter Download aller Törn-Dokumente als ZIP.

Die einzelnen PDFs werden von ihren normalen Views erzeugt — hier werden sie
nur eingesammelt und verpackt. Dadurch bleibt jede Änderung an einem PDF
automatisch auch im ZIP wirksam, und die Rechteprüfung jedes Views greift
weiterhin.

Ein Dokument, das sich nicht erzeugen lässt (z. B. ein Tagesplan ohne Einträge
oder ein fehlendes Recht), lässt das ZIP nicht scheitern: es fehlt dann in der
Datei und wird in HINWEIS.txt benannt.
"""
import re
import zipfile
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone

from boote.models import Boot
from .dokumente_pdf import (
    dokument_checkliste_pdf, mayday_plakat_pdf, notrollen_plakat_pdf,
)
from .models import Toern
from .views import _hat_skipper_oder_anbieter, crewlist_pdf, tagesplan_pdf, teilnehmerliste_pdf

CHECKLISTEN = [
    ('uebernahme', 'Checkliste-1-Charteruebernahme'),
    ('ablegen', 'Checkliste-2-Bevor-wir-ablegen'),
    ('anlegen', 'Checkliste-3-Nach-dem-Anlegen'),
    ('rueckgabe', 'Checkliste-4-Rueckgabe'),
]


def _sicher(name):
    """Dateinamen entschärfen: keine Pfadtrenner, keine Umlaute-Fallen."""
    ersetzt = (
        name.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')
            .replace('Ä', 'Ae').replace('Ö', 'Oe').replace('Ü', 'Ue')
            .replace('ß', 'ss')
    )
    return re.sub(r'[^A-Za-z0-9._-]+', '-', ersetzt).strip('-') or 'Datei'


def _hole(fehler, dateiname, view, *args, **kwargs):
    """Ein PDF erzeugen und als (Dateiname, Bytes) zurückgeben.

    Schlägt es fehl, wird None geliefert und der Grund in `fehler` vermerkt —
    ein einzelnes Dokument soll den ganzen Download nicht kippen.
    """
    try:
        antwort = view(*args, **kwargs)
    except Exception as exc:  # PermissionDenied, Http404, leere Daten …
        fehler.append(f"{dateiname}: {exc.__class__.__name__}")
        return None

    if getattr(antwort, 'status_code', 200) != 200:
        fehler.append(f"{dateiname}: HTTP {antwort.status_code}")
        return None
    return dateiname, antwort.content


def _boot_dateien(request, boot, fehler, mit_teilnehmerliste=True):
    """Alle Dokumente eines Bootes als Liste von (Dateiname, Bytes)."""
    dateien = [
        _hole(fehler, 'Mayday-Plakat.pdf', mayday_plakat_pdf, request, boot.id),
        _hole(fehler, 'Notfall-Sofortmassnahmen.pdf', notrollen_plakat_pdf, request, boot.id),
    ]
    for typ, name in CHECKLISTEN:
        dateien.append(
            _hole(fehler, f'{name}.pdf', dokument_checkliste_pdf, request, boot.id, typ)
        )
    dateien.append(_hole(fehler, 'Crewliste.pdf', crewlist_pdf, request, boot.id))
    dateien.append(
        _hole(fehler, 'Tagesplan.pdf', tagesplan_pdf, request, boot.toern_id, boot.id)
    )
    if mit_teilnehmerliste:
        dateien.append(
            _hole(fehler, 'Teilnehmerliste.pdf', teilnehmerliste_pdf, request, boot.toern_id)
        )
    return [d for d in dateien if d]


def _hinweis(fehler):
    return (
        "Diese Dokumente konnten nicht erzeugt werden und fehlen deshalb:\n\n"
        + "\n".join(f"- {f}" for f in fehler)
        + "\n\nHäufigster Grund: Für das Dokument gibt es noch keine Inhalte.\n"
    )


def _antwort(puffer, dateiname):
    puffer.seek(0)
    antwort = HttpResponse(puffer, content_type='application/zip')
    antwort['Content-Disposition'] = f'attachment; filename="{dateiname}"'
    return antwort


@login_required
def boot_dokumente_zip(request, boot_id):
    """Alle Dokumente eines Bootes gebündelt."""
    boot = get_object_or_404(Boot.objects.select_related('toern'), id=boot_id)
    _hat_skipper_oder_anbieter(request, boot.toern)

    fehler = []
    puffer = BytesIO()
    with zipfile.ZipFile(puffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, inhalt in _boot_dateien(request, boot, fehler):
            zf.writestr(name, inhalt)
        if fehler:
            zf.writestr('HINWEIS.txt', _hinweis(fehler))

    stand = timezone.localdate().strftime('%Y-%m-%d')
    return _antwort(puffer, f'Dokumente_{_sicher(boot.name)}_{stand}.zip')


@login_required
def toern_dokumente_zip(request, toern_id):
    """Alle Boote eines Törns, je Boot ein Ordner.

    Die Teilnehmerliste gilt für den ganzen Törn und liegt deshalb einmal
    oben im Archiv statt in jedem Bootsordner.
    """
    toern = get_object_or_404(Toern, id=toern_id)
    _hat_skipper_oder_anbieter(request, toern)

    fehler = []
    puffer = BytesIO()
    with zipfile.ZipFile(puffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for boot in toern.boote.order_by('name'):
            ordner = _sicher(boot.name)
            for name, inhalt in _boot_dateien(request, boot, fehler, mit_teilnehmerliste=False):
                zf.writestr(f'{ordner}/{name}', inhalt)

        gesamt = _hole(fehler, 'Teilnehmerliste.pdf', teilnehmerliste_pdf, request, toern.id)
        if gesamt:
            zf.writestr(*gesamt)
        if fehler:
            zf.writestr('HINWEIS.txt', _hinweis(fehler))

    stand = timezone.localdate().strftime('%Y-%m-%d')
    return _antwort(puffer, f'Dokumente_{_sicher(toern.titel)}_{stand}.zip')
