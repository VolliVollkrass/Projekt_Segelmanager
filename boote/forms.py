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

    class Meta:
        model = Boot
        exclude = ["toern"]

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

            "baujahr": forms.NumberInput(attrs={
                "class": "input input-bordered w-full"
            }),

            "laenge": forms.NumberInput(attrs={
                "class": "input input-bordered w-full",
                "step": "0.01"
            }),

            "tiefe": forms.NumberInput(attrs={
                "class": "input input-bordered w-full",
                "step": "0.01"
            }),

            "preis": forms.NumberInput(attrs={
                "class": "input input-bordered w-full"
            }),

            "bild_boot": forms.ClearableFileInput(attrs={
                "class": "file-input file-input-bordered w-full"
            }),
        }

    # 🔥 WICHTIG
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Charterunternehmen optional machen
        self.fields['charterunternehmen'].required = False

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

        if betten <= 0:
            raise forms.ValidationError("Mindestens 1 Bett erforderlich.")

        return betten


# =========================
# KABINEN FORMSET
# =========================
KabineFormSet = inlineformset_factory(
    Boot,
    Kabine,
    form=KabineForm,
    extra=1,
    can_delete=True
)