from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from PIL import Image, ImageOps
from io import BytesIO
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import InMemoryUploadedFile
from .models import User, Lizenz
from utils.image_optimizer import optimize_image
import uuid


class RegisterForm(UserCreationForm):

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            "class": "input input-bordered w-full"
        })
    )

    password1 = forms.CharField(
        label="Passwort",
        widget=forms.PasswordInput(attrs={
            "class": "input input-bordered w-full"
        })
    )

    password2 = forms.CharField(
        label="Passwort wiederholen",
        widget=forms.PasswordInput(attrs={
            "class": "input input-bordered w-full"
        })
    )

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "email",
            "profilbild",
        )

        widgets = {
            "first_name": forms.TextInput(attrs={
                "class": "input input-bordered w-full"
            }),
            "last_name": forms.TextInput(attrs={
                "class": "input input-bordered w-full"
            }),
            "profilbild": forms.FileInput(attrs={
                "class": "file-input file-input-bordered w-full"
            }),
        }

    def save(self, commit=True):
        user = super().save(commit=False)

        # Email immer klein speichern
        user.email = self.cleaned_data["email"].lower()

        # Username automatisch generieren
        user.username = uuid.uuid4().hex[:10]

        if commit:
            user.save()  # nutzt automatisch die save()-Optimierung aus dem Model

        return user


class LoginForm(AuthenticationForm):

    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            "class": "input input-bordered w-full"
        })
    )

    password = forms.CharField(
        label="Passwort",
        widget=forms.PasswordInput(attrs={
            "class": "input input-bordered w-full"
        })
    )


    error_messages = {
        "invalid_login": "Email oder Passwort ist falsch.",
        "inactive": "Dieser Account ist deaktiviert.",
    }

    def clean(self):
        email = self.cleaned_data.get("username")
        password = self.cleaned_data.get("password")

        if email and password:

            email = email.lower()

            self.user_cache = authenticate(
                self.request,
                username=email,
                password=password,
            )

            if self.user_cache is None:

                # Timing-Attack Schutz
                make_password(password)

                raise forms.ValidationError(
                    self.error_messages["invalid_login"],
                    code="invalid_login",
                )

        return self.cleaned_data

class AccountEditForm(forms.ModelForm):

    email = forms.EmailField(
        disabled=True,
        required=False,
        widget=forms.EmailInput(attrs={
            "class": "input input-bordered w-full"
        })
    )

    geburtsdatum = forms.DateField(
        required=False,
        widget=forms.DateInput(
            attrs={"type": "date", "class": "input input-bordered w-full"},
            format="%Y-%m-%d"  # <- wichtig!
        ),
        input_formats=["%Y-%m-%d"]
    )


    old_password = forms.CharField(
        label="Aktuelles Passwort",
        required=False,
        widget=forms.PasswordInput(attrs={
            "class": "input input-bordered w-full"
        })
    )

    new_password1 = forms.CharField(
        label="Neues Passwort",
        required=False,
        widget=forms.PasswordInput(attrs={
            "class": "input input-bordered w-full"
        })
    )

    new_password2 = forms.CharField(
        label="Neues Passwort wiederholen",
        required=False,
        widget=forms.PasswordInput(attrs={
            "class": "input input-bordered w-full"
        })
    )

    class Meta:
        model = User
        fields = [
            "email",
            "telefonnummer",
            "geburtsdatum",
            "geburtsort",
            "nationalitaet",
            "geschlecht",
            "identifikationstyp",
            "passnummer",
            "strasse",
            "plz",
            "ort",
            "profilbild",
        ]

        widgets = {
            "telefonnummer": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "geburtsort": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "nationalitaet": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "geschlecht": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "identifikationstyp": forms.Select(attrs={"class": "select select-bordered w-full"}),
            "passnummer": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "strasse": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "plz": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "ort": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "profilbild": forms.FileInput(attrs={"class": "file-input file-input-bordered w-full"}),
        }

    def clean(self):

        cleaned_data = super().clean()

        old_password = cleaned_data.get("old_password")
        new_password1 = cleaned_data.get("new_password1")
        new_password2 = cleaned_data.get("new_password2")

        # wenn neues Passwort gesetzt wird
        if new_password1 or new_password2:

            if not old_password:
                raise forms.ValidationError(
                    "Bitte aktuelles Passwort angeben."
                )

            if not self.instance.check_password(old_password):
                raise forms.ValidationError(
                    "Aktuelles Passwort ist falsch."
                )

            if new_password1 != new_password2:
                raise forms.ValidationError(
                    "Neue Passwörter stimmen nicht überein."
                )

            validate_password(new_password1, self.instance)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)

        # Profilbild optimieren nur wenn ein neues hochgeladen wurde
        profilbild = self.cleaned_data.get("profilbild")
        if profilbild and isinstance(profilbild, InMemoryUploadedFile):
            # zentrale Optimierung nutzen
            optimized_file = optimize_image(profilbild)
            user.profilbild.save(profilbild.name, optimized_file, save=False)

        # Passwort setzen falls angegeben
        new_password = self.cleaned_data.get("new_password1")
        if new_password:
            user.set_password(new_password)

        if commit:
            user.save()  # save() aus Model kümmert sich um alte Bilder

        return user
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.geburtsdatum:
            self.fields['geburtsdatum'].initial = self.instance.geburtsdatum.strftime("%Y-%m-%d")


class LizenzForm(forms.ModelForm):
    class Meta:
        model = Lizenz
        fields = ["name", "ausstellungsdatum", "ablaufdatum", "dokument_vorne", "dokument_hinten"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "ausstellungsdatum": forms.DateInput(attrs={"class": "input input-bordered w-full", "type": "date"}),
            "ablaufdatum": forms.DateInput(attrs={"class": "input input-bordered w-full", "type": "date"}),
            "dokument_vorne": forms.ClearableFileInput(attrs={"class": "file-input file-input-bordered w-full"}),
            "dokument_hinten": forms.ClearableFileInput(attrs={"class": "file-input file-input-bordered w-full"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)

        # Nutze zentrale Optimierung
        for field_name in ["dokument_vorne", "dokument_hinten"]:
            image = getattr(self.instance, field_name)
            uploaded = self.cleaned_data.get(field_name)
            if uploaded and uploaded != image:
                optimized_file = optimize_image(uploaded)
                getattr(instance, field_name).save(uploaded.name, optimized_file, save=False)

        if commit:
            instance.save()  # save() aus Model kümmert sich um alte Bilder

        return instance