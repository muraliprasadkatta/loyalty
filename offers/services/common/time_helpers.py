from datetime import datetime, time, timedelta

from django.utils import timezone


def get_local_day_bounds(dt=None):
    """
    Return (day_start, next_day_start) for the current local timezone day.
    Safe for USE_TZ=True projects where business logic should follow local day boundaries.
    """
    now_ts = dt or timezone.now()
    local_now = timezone.localtime(now_ts)
    tz = timezone.get_current_timezone()

    day_start = timezone.make_aware(
        datetime.combine(local_now.date(), time.min),
        tz,
    )
    next_day_start = day_start + timedelta(days=1)
    return day_start, next_day_start