from django import forms
from .models import RegisterAddress

class AddressForm(forms.ModelForm):
    class Meta:
        model = RegisterAddress
        fields = ['fullname', 'email', 'address1', 'address2', 'city', 'state', 'country', 'zipcode', 'phone']
        exclude = ['user']