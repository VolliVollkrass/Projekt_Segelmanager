from django.urls import path
from .views import *

urlpatterns = [
    path('detail/<int:pk>/', toern_detail, name='toern_detail'),  # Detailseite
    path('anmeldung/<int:pk>/', toern_anmeldung, name='toern_anmeldung'),  # Anmeldeseite
    path('anbieter/', anbieter_dashboard, name='anbieter_dashboard'),
    path('create/', toern_create, name='toern_create'),
    path('edit/<int:pk>/', toern_edit, name='toern_edit'),
    path('status/<int:pk>/', toern_status_update, name='toern_status_update'),

]