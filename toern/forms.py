from django import forms
from .models import Toern


class ToernForm(forms.ModelForm):
    startdatum = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "class": "input input-bordered w-full"
            },
            format="%Y-%m-%dT%H:%M"  # HTML5 datetime-local Format
        ),
        input_formats=["%Y-%m-%dT%H:%M"]
    )

    enddatum = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "class": "input input-bordered w-full"
            },
            format="%Y-%m-%dT%H:%M"  # HTML5 datetime-local Format
        ),
        input_formats=["%Y-%m-%dT%H:%M"]
    )

    anmeldeschluss = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(
            attrs={
                "type": "datetime-local",
                "class": "input input-bordered w-full"
            },
            format="%Y-%m-%dT%H:%M"  # HTML5 datetime-local Format
        ),
        input_formats=["%Y-%m-%dT%H:%M"]
    )

    class Meta:
        model = Toern
        exclude = ["anbieter"]  # wird im View gesetzt

        STATUS_CHOICES = [
            ("DRAFT", "Entwurf"),
            ("ANMELDUNG_OFFEN", "Anmeldung offen"),
            ("ANMELDUNG_GESCHLOSSEN", "Anmeldung geschlossen"),
        ]

        status = forms.ChoiceField(
            choices=STATUS_CHOICES,
            widget=forms.Select(attrs={"class": "select select-bordered w-full"})
        )

        widgets = {
            "titel": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "revier": forms.TextInput(attrs={"class": "input input-bordered w-full"}),

            "startdatum": forms.DateTimeInput(attrs={
                "type": "datetime-local",
                "class": "input input-bordered w-full"
            }),
            "enddatum": forms.DateTimeInput(attrs={
                "type": "datetime-local",
                "class": "input input-bordered w-full"
            }),
            "anmeldeschluss": forms.DateTimeInput(attrs={
                "type": "datetime-local",
                "class": "input input-bordered w-full"
            }),
            "preis_pro_person": forms.NumberInput(attrs={"class": "input input-bordered w-full"}),
            "nebenkosten": forms.NumberInput(attrs={"class": "input input-bordered w-full"}),

            "kurzbeschreibung": forms.TextInput(attrs={"class": "input input-bordered w-full"}),
            "beschreibung": forms.Textarea(attrs={"class": "textarea textarea-bordered w-full"}),

            "bild_toern": forms.ClearableFileInput(attrs={"class": "file-input file-input-bordered w-full"}),

            "boote": forms.SelectMultiple(attrs={"class": "select select-bordered w-full"}),

            
        }
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        for field in ["startdatum", "enddatum", "anmeldeschluss"]:
            if self.instance and getattr(self.instance, field):
                self.fields[field].initial = getattr(self.instance, field).strftime("%Y-%m-%dT%H:%M")

        self.fields['startdatum'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['enddatum'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['anmeldeschluss'].input_formats = ['%Y-%m-%dT%H:%M']



