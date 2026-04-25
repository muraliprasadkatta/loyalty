# offers/services/branch_api/branch_live_api_service.py

from django.utils import timezone

from offers.models import UserVisitEvent, UserOfferClaim
from offers.services.common.time_helpers import get_local_day_bounds


def get_branch_live_api_data(branch):
    """
    Common live data for branch-side pages/cards.
    Use this for branch home, all visits overview, side cards, etc.
    """

    now_ts = timezone.localtime(timezone.now())
    day_start, next_day_start = get_local_day_bounds(now_ts)

    today_visit_qs = UserVisitEvent.objects.filter(
        branch=branch,
        created_at__gte=day_start,
        created_at__lt=next_day_start,
    )

    all_visit_qs = UserVisitEvent.objects.filter(branch=branch)

    today_offer_claims = UserOfferClaim.objects.filter(
        visit_event__branch=branch,
        issued_at__gte=day_start,
        issued_at__lt=next_day_start,
    ).count()

    all_claims = UserOfferClaim.objects.filter(
        visit_event__branch=branch,
    ).count()

    return {
        "today": {
            "visits": today_visit_qs.count(),
            "offer_claims": today_offer_claims,
            "qr_visits": today_visit_qs.filter(
                visit_method="qr_code",
            ).count(),
            "staff_verified": today_visit_qs.filter(
                visit_method__in=["qr_pin", "offer_day_pin"],
            ).count(),
        },
        "all_time": {
            "visits": all_visit_qs.count(),
            "claims": all_claims,
            "unique_users": all_visit_qs.exclude(user__isnull=True)
                .values("user_id")
                .distinct()
                .count(),
            "qr_pin_visits": all_visit_qs.filter(
                visit_method="qr_pin",
            ).count(),
            "qr_visits": all_visit_qs.filter(
                visit_method="qr_code",
            ).count(),
        },
    }