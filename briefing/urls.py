from django.urls import path

from . import views

urlpatterns = [
    path("", views.bibliothek, name="briefing_bibliothek"),
    path("neu/", views.baustein_erstellen, name="briefing_baustein_erstellen"),
    path("<int:pk>/", views.baustein_detail, name="briefing_baustein_detail"),
    path("<int:pk>/bearbeiten/", views.baustein_bearbeiten, name="briefing_baustein_bearbeiten"),
    path("<int:pk>/loeschen/", views.baustein_loeschen, name="briefing_baustein_loeschen"),
    path("vorschau/", views.vorschau, name="briefing_vorschau"),
    path("ki/korrektur/", views.ki_korrektur, name="briefing_ki_korrektur"),
]
