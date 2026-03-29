from django import forms
from .models import Toern, Teilnahme


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


class TeilnahmeForm(forms.ModelForm):

    password1 = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            "class": "input input-bordered w-full"
        })
    )

    password2 = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={
            "class": "input input-bordered w-full"
        })
    )

    gesegelte_meilen = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "input input-bordered w-full",
            "placeholder": "z.B. 250",
            "min": "0"
        })
    )

    gesegelte_meilen = forms.IntegerField(
        required=False,
        widget=forms.NumberInput(attrs={
            "class": "input input-bordered w-full",
            "placeholder": "z.B. 250",
            "min": "0"
        })
    )
    teilnahmebedingungen_akzeptiert = forms.BooleanField(
        required=True,
        widget=forms.CheckboxInput(attrs={
            "class": "checkbox checkbox-primary"
        })
    )

    notizen = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            "class": "textarea textarea-bordered w-full",
            "placeholder": "z.B. besondere Wünsche, Fragen...",
            "rows": 3
        })
    )
    geburtsdatum = forms.DateField(
        required=True,
        widget=forms.DateInput(attrs={
            "type": "date",
            "class": "input input-bordered w-full"
        })
    )


    class Meta:
        model = Teilnahme
        fields = [
            "gesegelte_meilen",
            "seglerische_erfahrung",
            "notizen",
            "teilnahmebedingungen_akzeptiert"
        ]

    def clean(self):
        cleaned_data = super().clean()

        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 or password2:
            if password1 != password2:
                raise forms.ValidationError("Passwörter stimmen nicht überein.")

        return cleaned_data
