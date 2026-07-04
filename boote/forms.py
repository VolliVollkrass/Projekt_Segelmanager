from django import forms
from django.forms import inlineformset_factory
from .models import Boot, Kabine, Charterunternehmen


# =========================
# BOOT FORM
# =========================
class BootForm(forms.ModelForm):
    neues_charterunternehmen = forms.CharField(
        required=False,
        label="Neues Charterunternehmen",
        widget=forms.TextInput(attrs={
            "class": "input input-bordered w-full",
            "placeholder": "Optional neu anlegen..."
        })
    )

    # CharField statt FloatField — verhindert dass Django "13,5" vor clean_ ablehnt
    laenge = forms.CharField(
        required=False,
        label="Länge (m)",
        widget=forms.TextInput(attrs={
            "class": "input input-bordered w-full",
            "placeholder": "z.B. 13,5"
        })
    )
    tiefe = forms.CharField(
        required=False,
        label="Tiefe (m)",
        widget=forms.TextInput(attrs={
            "class": "input input-bordered w-full",
            "placeholder": "z.B. 2,67"
        })
    )

    class Meta:
        model = Boot
        exclude = ["toern", "skipper_meilen"]

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "z.B. Bavaria Cruiser 46"
            }),

            "typ": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "z.B. Segelyacht"
            }),

            "charterunternehmen": forms.Select(attrs={
                "class": "select select-bordered w-full"
            }),

            "hafen": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "z.B. Split"
            }),

            "hafen_googlemaps": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "Google Maps Link"
            }),

            "funkrufzeichen": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "z.B. DGXY2"
            }),

            "mmsi": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "9-stellig, z.B. 211234560",
                "inputmode": "numeric",
                "maxlength": "9"
            }),

            "baujahr": forms.NumberInput(attrs={
                "class": "input input-bordered w-full"
            }),

            "preis": forms.NumberInput(attrs={
                "class": "input input-bordered w-full"
            }),

            "bild_boot": forms.ClearableFileInput(attrs={
                "class": "file-input file-input-bordered w-full"
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['charterunternehmen'].required = False
        # Existierende Float-Werte als String vorbelegen damit das Formular beim Bearbeiten korrekt anzeigt
        if self.instance and self.instance.pk:
            if self.instance.laenge is not None:
                self.initial['laenge'] = str(self.instance.laenge).replace(".", ",")
            if self.instance.tiefe is not None:
                self.initial['tiefe'] = str(self.instance.tiefe).replace(".", ",")

    def _parse_dezimal(self, wert_str):
        wert = (wert_str or "").strip().replace(",", ".")
        if not wert:
            return None
        try:
            return float(wert)
        except ValueError:
            raise forms.ValidationError("Bitte eine gültige Zahl eingeben (z.B. 13,5).")

    def clean_mmsi(self):
        mmsi = (self.cleaned_data.get("mmsi") or "").strip()
        if mmsi and (not mmsi.isdigit() or len(mmsi) != 9):
            raise forms.ValidationError("Die MMSI besteht aus genau 9 Ziffern.")
        return mmsi

    def clean_laenge(self):
        return self._parse_dezimal(self.cleaned_data.get("laenge", ""))

    def clean_tiefe(self):
        return self._parse_dezimal(self.cleaned_data.get("tiefe", ""))

    def clean(self):
        cleaned_data = super().clean()

        charter = cleaned_data.get("charterunternehmen")
        neues = cleaned_data.get("neues_charterunternehmen")

        # ❗ Nur Fehler wenn BEIDES gesetzt
        if charter and neues:
            raise forms.ValidationError(
                "Bitte entweder ein bestehendes Charterunternehmen wählen ODER ein neues anlegen."
            )

        return cleaned_data

    def save(self, commit=True):
        boot = super().save(commit=False)

        neues = self.cleaned_data.get("neues_charterunternehmen")

        if neues:
            # 🔥 verhindert doppelte Einträge
            charter, created = Charterunternehmen.objects.get_or_create(
                name=neues.strip()
            )
            boot.charterunternehmen = charter

        if commit:
            boot.save()

        return boot


# =========================
# KABINEN FORM
# =========================
class KabineForm(forms.ModelForm):
    class Meta:
        model = Kabine
        fields = ["name", "betten"]

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "input input-bordered w-full",
                "placeholder": "z.B. Heck Backbord"
            }),
            "betten": forms.NumberInput(attrs={
                "class": "input input-bordered w-full",
                "min": "1"
            }),
        }

    def clean_betten(self):
        betten = self.cleaned_data.get("betten")

        if betten is not None and betten <= 0:
            raise forms.ValidationError("Mindestens 1 Bett erforderlich.")

        return betten


# =========================
# KABINEN FORMSET
# =========================
KabineFormSet = inlineformset_factory(
    Boot,
    Kabine,
    form=KabineForm,
    extra=0,
    can_delete=True
)