from django.urls import path
from .views import *

urlpatterns = [
    path('create/<int:toern_id>/', boot_create, name='boot_create'),
    path('edit/<int:pk>/', boot_update, name='boot_update'),
]