import re
from django.contrib.auth.models import User#django built_in User model
from django import forms
from django.contrib.auth.forms import UserCreationForm#django built_in UserCreationForm

from django.contrib.auth.forms import AuthenticationForm#django built_in AuthenticationForm
from django.forms.widgets import PasswordInput, TextInput#PasswordInput and TextInput widgets
from .models import UserProfile#UserProfile model
from django.contrib.auth.forms import PasswordResetForm
from django.contrib.auth import authenticate#django built_in authenticate function
from django_recaptcha.fields import ReCaptchaField

class RegisterForm(UserCreationForm):#RegisterForm class inherits from UserCreationForm

    captcha = ReCaptchaField()

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
        email = self.cleaned_data.get('email').lower()
        #get the email from the form
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Email already exists")
            #if email already exists in the database
        return email
    
    def clean_username(self):
        username = self.cleaned_data.get('username').lower()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Username already exists")
            #if username already exists in the database
        return username
    
    def clean_password2(self):
        password1 = self.cleaned_data.get('password1')
        password2 = self.cleaned_data.get('password2')

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match")
        if password1:
            if len(password1) < 8:
                raise forms.ValidationError("Password must be at least 8 characters long")
            if not re.search(r'[A-Z]', password1):
                raise forms.ValidationError("Password must contain at least one uppercase letter")
            if not re.search(r'[a-z]', password1):
                raise forms.ValidationError("Password must contain at least one lowercase letter")
            if not re.search(r'[0-9]', password1):
                raise forms.ValidationError("Password must contain at least one digit")
            if not re.search(r'[@$!%*?&]', password1):
                raise forms.ValidationError("Password must contain at least one special character (@, $, !, %, *, ?, &)")
        return password2

class LoginForm(AuthenticationForm):#LoginForm class inherits from AuthenticationForm

    #captcha = ReCaptchaField(required=False)

    username = forms.CharField(widget=TextInput(attrs={'placeholder': 'Username or Email'}), label="Username or Email")
    password = forms.CharField(widget=PasswordInput(attrs={'placeholder': 'Password'}), label="Password")

    def clean(self):
        # Get the cleaned data
        username_or_email = self.cleaned_data.get('username').lower()
        password = self.cleaned_data.get('password')
        '''#captcha = self.cleaned_data.get('captcha')

        # Require CAPTCHA if rate limit exceeded (6 attempts per minute)
        if hasattr(self.request, 'limited') and self.request.limited:
            if not captcha:
                raise forms.ValidationError("Please complete the CAPTCHA after multiple failed attempts.")'''

        if username_or_email and password:
            # Try to authenticate the user
            user = None
            # Check if the input is an email
            if '@' in username_or_email:
                try:
                    # Get the user by email
                    user_obj = User.objects.get(email=username_or_email)
                    user = authenticate(self.request, username=user_obj.username, password=password)
                except User.DoesNotExist:
                    raise forms.ValidationError("Invalid email or password.")
            else:
                # Assume the input is a username
                user = authenticate(self.request, username=username_or_email, password=password)

            if user is None:
                raise forms.ValidationError("Invalid username/email or password.")
            
            # If authentication is successful, store the user in cleaned_data
            self.cleaned_data['user'] = user

        return self.cleaned_data

    def get_user(self):
        # Return the authenticated user
        return self.cleaned_data.get('user')

    
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
    
    def clean_username(self):
        username = self.cleaned_data.get('username').lower()
        #get the username from the form
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Username already exists")
            #if username already exists in the database
        return username
    

class UserProfileForm(forms.ModelForm):#UpdateProfileForm class inherits from forms.ModelForm

    class Meta:
        model = UserProfile
        fields = ['profile_picture']


class CustomPasswordResetForm(PasswordResetForm):
    def clean_email(self):
        email = self.cleaned_data['email']
        if not User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is not registered with us.")
        return email
