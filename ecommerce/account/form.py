from django.contrib.auth.models import User#django built_in User model
from django import forms
from django.contrib.auth.forms import UserCreationForm#django built_in UserCreationForm

from django.contrib.auth.forms import AuthenticationForm#django built_in AuthenticationForm
from django.forms.widgets import PasswordInput, TextInput#PasswordInput and TextInput widgets
from .models import UserProfile#UserProfile model


class RegisterForm(UserCreationForm):#RegisterForm class inherits from UserCreationForm

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email', 'password1', 'password2']
        #fields to be displayed in the form

    def __init__(self, *args, **kwargs):
        super(RegisterForm, self).__init__(*args, **kwargs)
        #calling the __init__ method of the parent class

        self.fields['email'].required = True
        #email field is required

    def clean_email(self):
        email = self.cleaned_data.get('email')
        #get the email from the form
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email already exists")
            #if email already exists in the database
        return email
    

class LoginForm(AuthenticationForm):#LoginForm class inherits from AuthenticationForm

    username = forms.CharField(widget=TextInput())
    password = forms.CharField(widget=PasswordInput())

    
class UpdateUserForm(forms.ModelForm):#UpdateUserForm class inherits from forms.ModelForm

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'email']
        #fields to be displayed in the form
        exclude = ['password1', 'password2']
        #fields to be excluded from the form

    def __init__(self, *args, **kwargs):
        super(UpdateUserForm, self).__init__(*args, **kwargs)
        #calling the __init__ method of the parent class

        self.fields['email'].required = True
        #email field is required

    def clean_email(self):
        email = self.cleaned_data.get('email')
        #get the email from the form
        if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Email already exists")
            #if email already exists in the database
        return email
    

class UserProfileForm(forms.ModelForm):#UpdateProfileForm class inherits from forms.ModelForm

    class Meta:
        model = UserProfile
        fields = ['profile_picture']
