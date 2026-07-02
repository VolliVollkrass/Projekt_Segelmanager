from django.urls import path

from .views import (
    ausgabe_erstellen,
    ausgabe_loeschen,
    topf_ausgabe_erstellen,
    topf_ausgabe_loeschen,
)

urlpatterns = [
    path("<int:toern_id>/boot/<int:boot_id>/ausgabe/add/", ausgabe_erstellen, name="ausgabe_erstellen"),
    path("ausgabe/<int:ausgabe_id>/loeschen/", ausgabe_loeschen, name="ausgabe_loeschen"),
    path("<int:toern_id>/topf/add/", topf_ausgabe_erstellen, name="topf_ausgabe_erstellen"),
    path("topf/<int:ausgabe_id>/loeschen/", topf_ausgabe_loeschen, name="topf_ausgabe_loeschen"),
]
