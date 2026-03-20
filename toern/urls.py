from django.urls import path
from .views import *

urlpatterns = [
    path('detail/<int:pk>/', toern_detail, name='toern_detail'),  # Detailseite

]