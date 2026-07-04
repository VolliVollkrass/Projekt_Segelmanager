from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='andacht_dashboard'),
    path('buch/', views.buch, name='andacht_buch'),
    path('buch/<int:pk>/', views.buch_detail, name='andacht_buch_detail'),
    path('neu/', views.erstellen, name='andacht_erstellen'),
    path('<int:pk>/veroeffentlichen/', views.veroeffentlichen, name='andacht_veroeffentlichen'),
    path('<int:pk>/', views.detail, name='andacht_detail'),
    path('<int:pk>/bearbeiten/', views.bearbeiten, name='andacht_bearbeiten'),
    path('<int:pk>/loeschen/', views.loeschen, name='andacht_loeschen'),
    path('<int:pk>/pdf/', views.pdf, name='andacht_pdf'),
    path('api/tageslosung/', views.tageslosung_api, name='andacht_tageslosung_api'),
]
