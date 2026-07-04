from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.db.models import Count, Sum, OuterRef, Subquery, IntegerField, Q
from django.db.models.functions import Coalesce
from django.utils.text import slugify
from toern.models import Toern, Teilnahme
from boote.models import Kabine


def index(request):
    # Subquery: belegte Plätze pro Törn (1 DB-Query für alle Törns)
    belegte_sq = (
        Teilnahme.objects
        .filter(toern=OuterRef('pk'), status__in=['angemeldet', 'bestaetigt'])
        .values('toern')
        .annotate(n=Count('pk'))
        .values('n')[:1]
    )

    # Subquery: Gesamtplätze pro Törn aus Kabinen (1 DB-Query für alle Törns)
    gesamtplaetze_sq = (
        Kabine.objects
        .filter(boot__toern=OuterRef('pk'))
        .values('boot__toern')
        .annotate(total=Sum('betten'))
        .values('total')[:1]
    )

    # 🔒 Private Törns nur für den eigenen Anbieter bzw. Teilnehmer anzeigen
    sichtbar = Q(ist_privat=False)
    if request.user.is_authenticated:
        sichtbar |= Q(anbieter=request.user)
        sichtbar |= Q(teilnahmen__user=request.user)

    toerns = (
        Toern.objects
        .filter(status='ANMELDUNG_OFFEN')
        .filter(sichtbar)
        .distinct()
        .annotate(
            _belegte_plaetze=Coalesce(Subquery(belegte_sq, output_field=IntegerField()), 0),
            _gesamtplaetze=Coalesce(Subquery(gesamtplaetze_sq, output_field=IntegerField()), 0),
        )
        .order_by('startdatum')
    )

    user_toern_ids = set()
    if request.user.is_authenticated:
        user_toern_ids = set(
            Teilnahme.objects
            .filter(user=request.user, toern__in=toerns)
            .values_list('toern_id', flat=True)
        )

    return render(request, 'home/index.html', {
        'toerns': toerns,
        'user_toern_ids': user_toern_ids,
    })


@login_required
def pdf_viewer(request):
    """In-App-PDF-Viewer (PDF.js) mit Zurück- und Teilen-Button.

    Nötig für die iOS-WebApp: dort öffnen PDFs sonst ohne Navigations-Chrome
    und es gibt keinen Weg zurück. Zeigt nur eigene (same-origin) Pfade an.
    """
    src = request.GET.get("src", "")
    titel = request.GET.get("titel", "").strip() or "Dokument"

    # Nur relative Pfade der eigenen App — keine externen URLs einbetten
    if not src.startswith("/") or src.startswith("//") or "\\" in src:
        raise Http404

    dateiname = src.split("?")[0].rstrip("/").split("/")[-1]
    if not dateiname.endswith(".pdf"):
        dateiname = f"{slugify(titel) or 'dokument'}.pdf"

    return render(request, "pdf_viewer.html", {
        "src": src,
        "titel": titel,
        "dateiname": dateiname,
    })
