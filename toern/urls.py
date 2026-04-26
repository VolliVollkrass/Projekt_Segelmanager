from django.urls import path
from .views import *

urlpatterns = [
    path('detail/<int:pk>/', toern_detail, name='toern_detail'),  # Detailseite
    path('anmeldung/<int:pk>/', toern_anmeldung, name='toern_anmeldung'),  # Anmeldeseite
    path('anbieter/', anbieter_dashboard, name='anbieter_dashboard'),
    path('create/', toern_create, name='toern_create'),
    path('edit/<int:pk>/', toern_edit, name='toern_edit'),
    path('status/<int:pk>/', toern_status_update, name='toern_status_update'),
    path("<int:toern_id>/crew/", crew_dashboard, name="crew_dashboard"),
    path("crew/", crew_overview, name="crew_overview"),
    path("toern/<int:toern_id>/kabine/anfragen/", kabinenpartner_anfragen, name="kabinenpartner_anfragen"),
    path("kabine/<int:wunsch_id>/antwort/", kabinenpartner_antwort, name="kabinenpartner_antwort"),
    path("toern/<int:toern_id>/praeferenzen/", praeferenzen_speichern, name="praeferenzen_speichern"),
    path("<int:toern_id>/skipper/", skipper_dashboard, name="skipper_dashboard"),
    path("toern/<int:toern_id>/kabine-update/", kabine_update, name="kabine_update"),
    path("toern/<int:toern_id>/auto-assign/", auto_assign, name="auto_assign"),
    path("boot/<int:boot_id>/assign-skipper/", boot_skipper_assign, name="boot_skipper_assign"),
    path("toern/<int:toern_id>/reset/", reset_zuteilung, name="reset_zuteilung"),
    path("warteliste/bestaetigen/<int:teilnahme_id>/", warteliste_bestaetigen, name="warteliste_bestaetigen"),
    path("<int:toern_id>/fix/", zuteilung_fixieren, name="zuteilung_fixieren"),
    path("warteliste/ablehnen/<int:teilnahme_id>/", warteliste_ablehnen, name="warteliste_ablehnen"),
    path("<int:toern_id>/daten/", teilnahme_daten_edit, name="teilnahme_daten_edit"),
    path("teilnehmer/bestaetigen/<int:teilnahme_id>/", teilnehmer_bestaetigen, name="teilnehmer_bestaetigen"),
    path("teilnehmer/ablehnen/<int:teilnahme_id>/", teilnehmer_ablehnen, name="teilnehmer_ablehnen"),
    path("<int:toern_id>/boot/", boot_dashboard, name="boot_dashboard"),
    path("gegenstand/<int:gegenstand_id>/take/", take_gegenstand, name="take_gegenstand"),
    path("<int:toern_id>/packitem/add/", add_packitem, name="add_packitem"),
    path("packitem/<int:item_id>/update/", update_packitem, name="update_packitem"),
    path("packitem/<int:item_id>/delete/", delete_packitem, name="delete_packitem"),
    path("packitem/<int:item_id>/toggle/", toggle_packitem, name="toggle_packitem"),
    path("<int:toern_id>/bootitem/add/", add_boot_item, name="add_boot_item"),
    path("bootitem/<int:item_id>/update/", update_boot_item, name="update_boot_item"),
    path("bootitem/<int:item_id>/delete/", delete_boot_item, name="delete_boot_item"),
    path("gegenstand/<int:gegenstand_id>/reduce/", reduce_gegenstand, name="reduce_gegenstand"),
]