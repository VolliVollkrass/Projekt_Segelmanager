from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='andacht_dashboard'),
    path('neu/', views.erstellen, name='andacht_erstellen'),
    path('<int:pk>/', views.detail, name='andacht_detail'),
    path('<int:pk>/loeschen/', views.loeschen, name='andacht_loeschen'),
    path('<int:pk>/pdf/', views.pdf, name='andacht_pdf'),
    path('api/tageslosung/', views.tageslosung_api, name='andacht_tageslosung_api'),
]
