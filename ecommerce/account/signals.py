from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=get_user_model())
def ensure_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


def repair_missing_profile(user):
    """Explicit repair path for legacy users created before profile signals."""
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile
