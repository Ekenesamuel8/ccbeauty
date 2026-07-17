import re

from django import forms

from .models import RegisterAddress


class AddressForm(forms.ModelForm):
    class Meta:
        model = RegisterAddress
        fields = (
            "label",
            "fullname",
            "email",
            "phone",
            "address1",
            "address2",
            "city",
            "state",
            "zipcode",
            "country",
            "is_default",
        )
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "phone": forms.TextInput(attrs={"type": "tel", "autocomplete": "tel"}),
            "fullname": forms.TextInput(attrs={"autocomplete": "name"}),
            "address1": forms.TextInput(attrs={"autocomplete": "address-line1"}),
            "address2": forms.TextInput(attrs={"autocomplete": "address-line2"}),
            "city": forms.TextInput(attrs={"autocomplete": "address-level2"}),
            "state": forms.TextInput(attrs={"autocomplete": "address-level1"}),
            "zipcode": forms.TextInput(attrs={"autocomplete": "postal-code"}),
            "country": forms.TextInput(attrs={"autocomplete": "country-name"}),
        }

    def clean(self):
        cleaned = super().clean()
        for field in self.Meta.fields:
            value = cleaned.get(field)
            if isinstance(value, str):
                cleaned[field] = value.strip()
        return cleaned

    def clean_phone(self):
        phone = (self.cleaned_data.get("phone") or "").strip()
        if not re.fullmatch(r"\+?[0-9][0-9()\-\s]{6,18}", phone):
            raise forms.ValidationError("Enter a valid phone number.")
        return phone
