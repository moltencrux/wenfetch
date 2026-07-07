from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import UserProfile


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    Ensure every User has a matching UserProfile.

    - On first creation of a User, create the profile row too.
    - On later saves, just make sure the profile exists (covers users
      created before this signal existed, or rows lost some other way)
      without touching any preference they've already set.
    """
    if created:
        UserProfile.objects.create(user=instance)
    else:
        UserProfile.objects.get_or_create(user=instance)
