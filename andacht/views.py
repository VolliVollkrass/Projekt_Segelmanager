import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_POST

from utils.permissions import andacht_required
from .models import Andacht
from .losung import hole_tageslosung
from .ki import generiere_andacht
from .pdf_export import erstelle_andacht_pdf


@login_required
@andacht_required
def dashboard(request):
    andachten = Andacht.objects.filter(user=request.user)
    return render(request, 'andacht/dashboard.html', {'andachten': andachten})


@login_required
@andacht_required
def erstellen(request):
    if request.method == 'POST':
        dauer_raw = request.POST.get('dauer_minuten', '15')
        try:
            dauer = int(dauer_raw)
        except (ValueError, TypeError):
            dauer = 15

        andacht = Andacht(
            user=request.user,
            typ=request.POST.get('typ', 'morgen'),
            zielgruppe=request.POST.get('zielgruppe', 'erwachsene'),
            dauer_minuten=dauer,
            thema=request.POST.get('thema', '').strip(),
            stichpunkte=request.POST.get('stichpunkte', '').strip(),
            bibelstelle_eingabe=request.POST.get('bibelstelle_eingabe', '').strip(),
            tageslosung_verwendet='tageslosung_verwendet' in request.POST,
            kirchenjahr=request.POST.get('kirchenjahr', ''),
            stil=request.POST.get('stil', ''),
            eigener_liedwunsch=request.POST.get('eigener_liedwunsch', '').strip(),
            mit_liedern='mit_liedern' in request.POST,
            mit_gespraechsimpulsen='mit_gespraechsimpulsen' in request.POST,
            mit_geschichte='mit_geschichte' in request.POST,
            mit_gebeten='mit_gebeten' in request.POST,
        )

        try:
            ergebnis = generiere_andacht(andacht)
        except Exception:
            ergebnis = None

        if not ergebnis:
            return render(request, 'andacht/erstellen.html', {
                'fehler': 'Die KI konnte keine Andacht generieren. Bitte versuche es erneut.',
                'post': request.POST,
            })

        andacht.titel = ergebnis.get('titel', '')
        andacht.bibelstelle = ergebnis.get('bibelstelle', '')
        andacht.bibeltext = ergebnis.get('bibeltext', '')
        andacht.exegese = ergebnis.get('exegese', '')
        andacht.einstieg = ergebnis.get('einstieg', '')
        andacht.entfaltung = ergebnis.get('entfaltung', '')
        andacht.abschluss = ergebnis.get('abschluss', '')
        andacht.geschichte = ergebnis.get('geschichte', '')
        andacht.lieder_json = json.dumps(ergebnis.get('lieder', []), ensure_ascii=False)
        andacht.gebete_json = json.dumps(ergebnis.get('gebete', {}), ensure_ascii=False)
        andacht.gespraechsimpulse_json = json.dumps(ergebnis.get('gespraechsimpulse', []), ensure_ascii=False)
        andacht.save()

        return redirect('andacht_detail', pk=andacht.pk)

    return render(request, 'andacht/erstellen.html', {})


@login_required
@andacht_required
def detail(request, pk):
    andacht = get_object_or_404(Andacht, pk=pk, user=request.user)
    return render(request, 'andacht/detail.html', {'andacht': andacht})


@login_required
@andacht_required
def loeschen(request, pk):
    andacht = get_object_or_404(Andacht, pk=pk, user=request.user)
    andacht.delete()
    return redirect('andacht_dashboard')


@login_required
@andacht_required
def pdf(request, pk):
    andacht = get_object_or_404(Andacht, pk=pk, user=request.user)
    buffer = erstelle_andacht_pdf(andacht)
    dateiname = f'andacht_{andacht.pk}.pdf'
    response = HttpResponse(buffer, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{dateiname}"'
    return response


@login_required
@andacht_required
def tageslosung_api(request):
    losung = hole_tageslosung()
    if losung:
        return JsonResponse(losung)
    return JsonResponse({'fehler': 'Tageslosung konnte nicht geladen werden.'}, status=503)
