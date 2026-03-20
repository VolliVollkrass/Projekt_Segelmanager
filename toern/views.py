from django.shortcuts import render, get_object_or_404
from .models import Toern, Teilnahme

def toern_detail(request, pk):
    toern = get_object_or_404(Toern, pk=pk)

    # optional: alle Boote des Törns laden
    boote = toern.boote.all()

    # Skipper pro Boot
    skipper_pro_boot = {
        boot.id: Teilnahme.objects.filter(
            toern=toern,
            boot=boot,
            rolle="skipper",
            status__in=["angemeldet", "bestaetigt"]
        ).select_related("user").first()
        for boot in boote
    }


    rtx = {
        'toern': toern,
        'boote': boote,
        'skipper_pro_boot': skipper_pro_boot,
    }

    return render(request, 'toern/toern_detail.html', rtx )