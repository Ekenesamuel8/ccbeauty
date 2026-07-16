from io import BytesIO

from PIL import Image, UnidentifiedImageError
from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordResetForm,
    UserCreationForm,
)
from django.core.exceptions import ValidationError

from .models import UserProfile


User = get_user_model()
MAX_PROFILE_IMAGE_SIZE = 5 * 1024 * 1024
ALLOWED_PROFILE_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def normalize_email(value):
    return User.objects.normalize_email((value or "").strip()).lower()


def validate_unique_email(email, *, exclude_user=None):
    query = User.objects.filter(email__iexact=email)
    if exclude_user is not None:
        query = query.exclude(pk=exclude_user.pk)
    if query.exists():
        raise ValidationError("An account with this email already exists.")


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True

    def clean_email(self):
        email = normalize_email(self.cleaned_data.get("email"))
        validate_unique_email(email)
        return email

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("An account with this username already exists.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = self.cleaned_data["username"]
        user.first_name = (self.cleaned_data.get("first_name") or "").strip()
        user.last_name = (self.cleaned_data.get("last_name") or "").strip()
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    username = forms.CharField(label="Username or email")

    def clean(self):
        identifier = (self.cleaned_data.get("username") or "").strip()
        password = self.cleaned_data.get("password")
        if identifier and password:
            self.user_cache = authenticate(
                self.request,
                username=identifier,
                password=password,
            )
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class UpdateUserForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "email")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True

    def clean_email(self):
        email = normalize_email(self.cleaned_data.get("email"))
        validate_unique_email(email, exclude_user=self.instance)
        return email

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if User.objects.filter(username__iexact=username).exclude(
            pk=self.instance.pk
        ).exists():
            raise forms.ValidationError("An account with this username already exists.")
        return username

    def clean_first_name(self):
        return (self.cleaned_data.get("first_name") or "").strip()

    def clean_last_name(self):
        return (self.cleaned_data.get("last_name") or "").strip()


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ("profile_picture",)

    def clean_profile_picture(self):
        image = self.cleaned_data.get("profile_picture")
        if not image:
            return image
        if image.size > MAX_PROFILE_IMAGE_SIZE:
            raise forms.ValidationError("Profile images must be 5 MB or smaller.")
        content_type = getattr(image, "content_type", "")
        if content_type not in ALLOWED_PROFILE_IMAGE_TYPES:
            raise forms.ValidationError("Upload a JPEG, PNG, or WebP image.")
        try:
            content = image.read()
            Image.open(BytesIO(content)).verify()
            image.seek(0)
        except (UnidentifiedImageError, OSError, ValueError):
            raise forms.ValidationError("Upload a valid image file.")
        return image


class PrivatePasswordResetForm(PasswordResetForm):
    def clean_email(self):
        return normalize_email(self.cleaned_data.get("email"))


CustomPasswordResetForm = PrivatePasswordResetForm


class DeleteAccountForm(forms.Form):
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_password(self):
        password = self.cleaned_data["password"]
        if self.user is None or not self.user.check_password(password):
            raise forms.ValidationError("The password is incorrect.")
        return password


class ResendVerificationForm(forms.Form):
    email = forms.EmailField()

    def clean_email(self):
        return normalize_email(self.cleaned_data.get("email"))
