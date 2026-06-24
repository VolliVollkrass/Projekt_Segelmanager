from django.urls import path
from . import views

urlpatterns = [
    path('', views.uebersicht, name='segelwissen_uebersicht'),
    path('knoten/<int:pk>/', views.knoten_detail, name='knoten_detail'),
]
