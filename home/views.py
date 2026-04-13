from django.shortcuts import render
from toern.models import Toern, Teilnahme

def index(request):
    # Nur Törns mit Status 'ANMELDUNG_OFFEN' oder 'VEROEFFENTLICHT'
    toerns = Toern.objects.filter(status__in=['ANMELDUNG_OFFEN', 'VEROEFFENTLICHT']).order_by('startdatum')

    user_teilnahme = None
    if request.user.is_authenticated:
        user_teilnahme = Teilnahme.objects.filter(
            user=request.user,
            toern__in=toerns
        ).first()

    rtx = {
        'toerns': toerns,
        'user_teilnahme': user_teilnahme,
    }

    return render(request, 'home/index.html', rtx)

