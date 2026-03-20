from django.urls import path
from . import views
from .views import register, CustomLoginView
from django.contrib.auth.views import LogoutView


urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("my-account/", views.my_account, name="my_account"),
    path("account-edit/", views.account_edit, name="account_edit"),
    path("lizenz-hinzufuegen/", views.lizenz_hinzufuegen, name="lizenz_hinzufuegen"),
    path("lizenz-loeschen/<int:pk>/", views.lizenz_loeschen, name="lizenz_loeschen"),
]