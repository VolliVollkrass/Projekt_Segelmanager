import json
import re

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import Rezept, RezeptSchritt, RezeptStern, RezeptZutat


def kochbuch_liste(request):
    qs = Rezept.objects.annotate(anzahl_sterne=Count("sterne")).select_related("autor")

    q = request.GET.get("q", "").strip()
    kategorie = request.GET.get("kategorie", "")
    sort = request.GET.get("sort", "neu")

    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(zutaten__name__icontains=q)).distinct()
    if kategorie:
        qs = qs.filter(kategorie=kategorie)
    if sort == "beliebt":
        qs = qs.order_by("-anzahl_sterne", "-erstellt_am")
    else:
        qs = qs.order_by("-erstellt_am")

    paginator = Paginator(qs, 12)
    page = paginator.get_page(request.GET.get("page"))

    meine_sterne = set()
    if request.user.is_authenticated:
        meine_sterne = set(
            RezeptStern.objects.filter(user=request.user).values_list("rezept_id", flat=True)
        )

    return render(request, "rezepte/liste.html", {
        "page_obj": page,
        "q": q,
        "kategorie": kategorie,
        "sort": sort,
        "kategorien": Rezept.KATEGORIE_CHOICES,
        "meine_sterne": meine_sterne,
    })


def rezept_detail(request, pk):
    rezept = get_object_or_404(
        Rezept.objects.prefetch_related("zutaten", "schritte", "sterne").select_related("autor"),
        pk=pk,
    )
    hat_stern = (
        request.user.is_authenticated
        and RezeptStern.objects.filter(rezept=rezept, user=request.user).exists()
    )
    return render(request, "rezepte/detail.html", {
        "rezept": rezept,
        "hat_stern": hat_stern,
    })


@login_required
def rezept_erstellen(request):
    if request.method == "POST":
        return _rezept_speichern(request, rezept=None)
    return render(request, "rezepte/form.html", {
        "kategorien": Rezept.KATEGORIE_CHOICES,
        "action": "erstellen",
    })


@login_required
def rezept_bearbeiten(request, pk):
    rezept = get_object_or_404(Rezept, pk=pk)
    if rezept.autor != request.user and not request.user.is_staff:
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied

    if request.method == "POST":
        return _rezept_speichern(request, rezept=rezept)

    return render(request, "rezepte/form.html", {
        "rezept": rezept,
        "kategorien": Rezept.KATEGORIE_CHOICES,
        "action": "bearbeiten",
        "zutaten_json": json.dumps([
            {"menge": z.menge, "name": z.name}
            for z in rezept.zutaten.all()
        ]),
        "schritte_json": json.dumps([s.text for s in rezept.schritte.all()]),
    })


def _rezept_speichern(request, rezept):
    name = request.POST.get("name", "").strip()
    kategorie = request.POST.get("kategorie", "hauptgericht")
    zubereitungszeit = int(request.POST.get("zubereitungszeit") or 30)
    portionen = int(request.POST.get("portionen") or 4)
    tipps = request.POST.get("tipps", "").strip()
    getraenk = request.POST.get("getraenk", "").strip()
    quelle_url = request.POST.get("quelle_url", "").strip()

    zutaten_raw = request.POST.get("zutaten_json", "[]")
    schritte_raw = request.POST.get("schritte_json", "[]")

    try:
        zutaten_data = json.loads(zutaten_raw)
    except (json.JSONDecodeError, ValueError):
        zutaten_data = []
    try:
        schritte_data = json.loads(schritte_raw)
    except (json.JSONDecodeError, ValueError):
        schritte_data = []

    if rezept is None:
        rezept = Rezept(autor=request.user)

    rezept.name = name
    rezept.kategorie = kategorie
    rezept.zubereitungszeit = zubereitungszeit
    rezept.portionen = portionen
    rezept.tipps = tipps
    rezept.getraenk = getraenk
    rezept.quelle_url = quelle_url

    if "bild" in request.FILES:
        rezept.bild = request.FILES["bild"]
    rezept.save()

    rezept.zutaten.all().delete()
    RezeptZutat.objects.bulk_create([
        RezeptZutat(rezept=rezept, menge=z.get("menge", ""), name=z.get("name", ""), order=i)
        for i, z in enumerate(zutaten_data) if z.get("name", "").strip()
    ])

    rezept.schritte.all().delete()
    RezeptSchritt.objects.bulk_create([
        RezeptSchritt(rezept=rezept, nummer=i + 1, text=s)
        for i, s in enumerate(schritte_data) if s.strip()
    ])

    return redirect("rezept_detail", pk=rezept.pk)


@login_required
@require_POST
def rezept_loeschen(request, pk):
    rezept = get_object_or_404(Rezept, pk=pk)
    if rezept.autor == request.user or request.user.is_staff:
        rezept.delete()
    return redirect("kochbuch_liste")


@login_required
@require_POST
def rezept_stern_toggle(request, pk):
    rezept = get_object_or_404(Rezept, pk=pk)
    stern, created = RezeptStern.objects.get_or_create(rezept=rezept, user=request.user)
    if not created:
        stern.delete()
        hat_stern = False
    else:
        hat_stern = True
    return JsonResponse({"hat_stern": hat_stern, "anzahl": rezept.sterne.count()})


@login_required
@require_POST
def ki_schritte_generieren(request):
    from django.conf import settings as django_settings
    import anthropic

    api_key = django_settings.ANTHROPIC_API_KEY
    if not api_key:
        return JsonResponse({"error": "KI nicht verfügbar."}, status=503)

    data = json.loads(request.body)
    name = data.get("name", "")
    zutaten = data.get("zutaten", [])
    portionen = data.get("portionen", 4)

    zutaten_text = ", ".join(
        f"{z.get('menge', '')} {z.get('name', '')}".strip()
        for z in zutaten if z.get("name")
    )

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"Du bist Kochberater für Segelboote. "
                f"Die Bordküche hat nur: 2 Gasflammen, einen kleinen Gasofen (meist nur Ober- ODER Unterhitze, kein Umluft). "
                f"Kein Geschirrspüler, begrenzte Arbeitsfläche, das Boot kann schwanken. "
                f"Schreibe 4–8 präzise, nummerierte Kochschritte für folgendes Rezept:\n"
                f"Gericht: {name}\n"
                f"Zutaten: {zutaten_text}\n"
                f"Portionen: {portionen}\n"
                f"Passe die Schritte an die Bordküche an: koordiniere parallele Schritte auf 2 Flammen, "
                f"gib praktische Hinweise für das Kochen auf See. "
                f"Antworte ausschließlich als JSON ohne Markdown: {{\"schritte\": [\"Schritt 1...\", \"Schritt 2...\", ...]}}"
            ),
        }],
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    return JsonResponse(json.loads(raw))


@login_required
@require_POST
def ki_url_import(request):
    from django.conf import settings as django_settings
    import anthropic
    try:
        import requests as http_requests
        from bs4 import BeautifulSoup
    except ImportError:
        return JsonResponse({"error": "Import-Bibliotheken nicht installiert."}, status=503)

    api_key = django_settings.ANTHROPIC_API_KEY
    if not api_key:
        return JsonResponse({"error": "KI nicht verfügbar."}, status=503)

    data = json.loads(request.body)
    url = data.get("url", "").strip()
    if not url:
        return JsonResponse({"error": "Keine URL angegeben."}, status=400)

    try:
        resp = http_requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; Segelkochbuch/1.0)"
        })
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        # Störende Elemente entfernen
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        text = text[:6000]  # Token-Limit schonen
    except Exception as e:
        return JsonResponse({"error": f"Seite konnte nicht geladen werden: {e}"}, status=400)

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": (
                f"Extrahiere das Rezept aus folgendem Webseiteninhalt und passe es für eine Bordküche an. "
                f"Die Bordküche hat: 2 Gasflammen, einen kleinen Gasofen (meist nur Ober- ODER Unterhitze). "
                f"Kein Geschirrspüler, begrenzte Arbeitsfläche.\n\n"
                f"Webseiteninhalt:\n{text}\n\n"
                f"Gib das Rezept als JSON zurück (ohne Markdown-Codeblöcke):\n"
                f'{{"name": "...", "kategorie": "hauptgericht", "zubereitungszeit": 30, "portionen": 4, '
                f'"zutaten": [{{"menge": "200g", "name": "Nudeln"}}], '
                f'"schritte": ["Schritt 1...", "Schritt 2..."], '
                f'"tipps": "...", "getraenk": "..."}}\n'
                f'Kategorie muss einer dieser Werte sein: fruehstueck, hauptgericht, snack, dessert, sonstiges.'
            ),
        }],
    )

    raw = message.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        return JsonResponse({"error": "KI-Antwort konnte nicht verarbeitet werden."}, status=500)

    return JsonResponse(result)
