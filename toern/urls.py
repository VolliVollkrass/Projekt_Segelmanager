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
    path("warteliste/ablehnen/<int:teilnahme_id>/", warteliste_ablehnen, name="warteliste_ablehnen"),
]