from django.urls import path
from .views import *

urlpatterns = [
    path("", index, name="index"),
    path("pdf-viewer/", pdf_viewer, name="pdf_viewer"),
]