from django.contrib.auth.models import User
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if '@' in username:
            # If the username looks like an email, try to authenticate by email
            try:
                user = User.objects.get(email=username)
            except User.DoesNotExist:
                user = None
        else:
            # Otherwise, try to authenticate by username
            user = User.objects.filter(username=username).first()

        if user is not None and user.check_password(password):
            return user
        return None