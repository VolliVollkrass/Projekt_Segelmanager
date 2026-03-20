from django.shortcuts import render
from toern.models import Toern

def index(request):
    # Nur Törns mit Status 'ANMELDUNG_OFFEN' oder 'VEROEFFENTLICHT'
    toerns = Toern.objects.filter(status__in=['ANMELDUNG_OFFEN', 'VEROEFFENTLICHT']).order_by('startdatum')
    return render(request, 'home/index.html', {'toerns': toerns})

