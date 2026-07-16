from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    profile_picture = models.ImageField(
        upload_to="images/",
        null=True,
        blank=True,
    )

    def __str__(self):
        return str(self.user)
