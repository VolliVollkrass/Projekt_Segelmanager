from django.urls import path

from .views import (
    ausgabe_erstellen,
    ausgleich_beglichen,
    ausgleich_zuruecknehmen,
    ausgabe_bearbeiten,
    ausgabe_loeschen,
    topf_ausgabe_erstellen,
    topf_ausgabe_bearbeiten,
    topf_ausgabe_loeschen,
    topf_beleg_add,
    topf_beleg_loeschen,
    topf_belege_pdf,
    topf_abrechnung_xlsx,
    umlage_formular,
    umlage_loeschen,
    umlage_anteil_beglichen,
)

urlpatterns = [
    path("<int:toern_id>/boot/<int:boot_id>/ausgabe/add/", ausgabe_erstellen, name="ausgabe_erstellen"),
    path("ausgabe/<int:ausgabe_id>/bearbeiten/", ausgabe_bearbeiten, name="ausgabe_bearbeiten"),
    path("ausgabe/<int:ausgabe_id>/loeschen/", ausgabe_loeschen, name="ausgabe_loeschen"),
    path("<int:toern_id>/boot/<int:boot_id>/ausgleich/beglichen/", ausgleich_beglichen, name="ausgleich_beglichen"),
    path("ausgleich/<int:zahlung_id>/zuruecknehmen/", ausgleich_zuruecknehmen, name="ausgleich_zuruecknehmen"),
    path("<int:toern_id>/umlage/neu/", umlage_formular, name="umlage_erstellen"),
    path("<int:toern_id>/umlage/<int:umlage_id>/bearbeiten/", umlage_formular, name="umlage_bearbeiten"),
    path("umlage/<int:umlage_id>/loeschen/", umlage_loeschen, name="umlage_loeschen"),
    path("umlage/anteil/<int:anteil_id>/beglichen/", umlage_anteil_beglichen, name="umlage_anteil_beglichen"),
    path("<int:toern_id>/topf/add/", topf_ausgabe_erstellen, name="topf_ausgabe_erstellen"),
    path("topf/<int:ausgabe_id>/bearbeiten/", topf_ausgabe_bearbeiten, name="topf_ausgabe_bearbeiten"),
    path("topf/<int:ausgabe_id>/loeschen/", topf_ausgabe_loeschen, name="topf_ausgabe_loeschen"),
    path("topf/<int:ausgabe_id>/beleg/add/", topf_beleg_add, name="topf_beleg_add"),
    path("topf/beleg/<int:beleg_id>/loeschen/", topf_beleg_loeschen, name="topf_beleg_loeschen"),
    path("<int:toern_id>/topf/belege.pdf", topf_belege_pdf, name="topf_belege_pdf"),
    path("<int:toern_id>/topf/abrechnung.xlsx", topf_abrechnung_xlsx, name="topf_abrechnung_xlsx"),
]
