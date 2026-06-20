from django.urls import path
from . import views
from .views import register, CustomLoginView
from django.contrib.auth.views import (
    LogoutView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)


urlpatterns = [
    path("register/", views.register, name="register"),
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("my-account/", views.my_account, name="my_account"),
    path("account-edit/", views.account_edit, name="account_edit"),
    path("lizenz-hinzufuegen/", views.lizenz_hinzufuegen, name="lizenz_hinzufuegen"),
    path("lizenz-loeschen/<int:pk>/", views.lizenz_loeschen, name="lizenz_loeschen"),
    path("seemeilen/hinzufuegen/", views.manueller_seemeileneintrag_hinzufuegen, name="seemeilen_hinzufuegen"),
    path("seemeilen/loeschen/<int:pk>/", views.manueller_seemeileneintrag_loeschen, name="seemeilen_loeschen"),
    path("onboarding/", views.onboarding, name="onboarding"),

    # E-Mail-Verifikation
    path("email-verifizieren/<uuid:token>/", views.verify_email, name="verify_email"),
    path("email-bestaetigung/warten/", views.verification_pending, name="verification_pending"),
    path("email-bestaetigung/erneut/", views.resend_verification, name="resend_verification"),

    # Passwort-Reset
    path("passwort-reset/", PasswordResetView.as_view(
        template_name="accounts/password_reset_form.html",
        email_template_name="accounts/password_reset_email.txt",
        subject_template_name="accounts/password_reset_subject.txt",
        success_url="/accounts/passwort-reset/bestaetigung/",
    ), name="password_reset"),
    path("passwort-reset/bestaetigung/", PasswordResetDoneView.as_view(
        template_name="accounts/password_reset_done.html",
    ), name="password_reset_done"),
    path("passwort-reset/<uidb64>/<token>/", PasswordResetConfirmView.as_view(
        template_name="accounts/password_reset_confirm.html",
        success_url="/accounts/passwort-reset/abgeschlossen/",
    ), name="password_reset_confirm"),
    path("passwort-reset/abgeschlossen/", PasswordResetCompleteView.as_view(
        template_name="accounts/password_reset_complete.html",
    ), name="password_reset_complete"),
]
