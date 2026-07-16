from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q


class EmailOrUsernameModelBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = username or kwargs.get("email")
        if not identifier or password is None:
            return None
        identifier = identifier.strip()
        User = get_user_model()
        users = User._default_manager.filter(
            Q(username__iexact=identifier) | Q(email__iexact=identifier)
        )[:2]
        if len(users) != 1:
            User().set_password(password)
            return None
        user = users[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
