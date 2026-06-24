from django.shortcuts import get_object_or_404, render
from .models import Knoten, Segelinformation, Segelvideo


def uebersicht(request):
    tab = request.GET.get('tab', 'knoten')
    context = {
        'aktiver_tab': tab,
        'knoten_liste': Knoten.objects.all() if tab == 'knoten' else None,
        'info_liste': Segelinformation.objects.all() if tab == 'infos' else None,
        'video_liste': Segelvideo.objects.all() if tab == 'videos' else None,
    }
    return render(request, 'segelwissen/uebersicht.html', context)


def knoten_detail(request, pk):
    knoten = get_object_or_404(Knoten, pk=pk)
    return render(request, 'segelwissen/knoten_detail.html', {'knoten': knoten})
