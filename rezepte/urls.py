from django.urls import path
from . import views

urlpatterns = [
    path("",                              views.kochbuch_liste,        name="kochbuch_liste"),
    path("neu/",                          views.rezept_erstellen,      name="rezept_erstellen"),
    path("<int:pk>/",                     views.rezept_detail,         name="rezept_detail"),
    path("<int:pk>/bearbeiten/",          views.rezept_bearbeiten,     name="rezept_bearbeiten"),
    path("<int:pk>/loeschen/",            views.rezept_loeschen,       name="rezept_loeschen"),
    path("<int:pk>/stern/",               views.rezept_stern_toggle,   name="rezept_stern_toggle"),
    path("ki/schritte/",                  views.ki_schritte_generieren, name="ki_schritte_generieren"),
    path("ki/url-import/",               views.ki_url_import,          name="ki_url_import"),
]
