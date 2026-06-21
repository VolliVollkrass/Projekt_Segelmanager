from django.shortcuts import render
from django.db.models import Count, Sum, OuterRef, Subquery, IntegerField, Q
from django.db.models.functions import Coalesce
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

    toerns = (
        Toern.objects
        .filter(status='ANMELDUNG_OFFEN')
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
