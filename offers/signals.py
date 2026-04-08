from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in
from django.utils import timezone

from .models import Profile, LoginVisit

User = get_user_model()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(user=instance)


@receiver(user_logged_in)
def create_daily_login_visit(sender, request, user, **kwargs):
    """
    On every successful login, stamp one row per local calendar day.
    Unique(user, visit_date) maintains 1/day de-dupe.
    """
    today_ist = timezone.localdate()

    LoginVisit.objects.get_or_create(
        user=user,
        visit_date=today_ist,
        defaults={"source": "login"},
    )