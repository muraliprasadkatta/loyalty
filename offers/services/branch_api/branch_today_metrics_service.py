import math

from django.db.models import Count, Exists, OuterRef, Q
from django.db.models.functions import ExtractHour
from django.utils import timezone

from offers.models import UserVisitEvent, UserOfferClaim
from offers.services.common.time_helpers import get_local_day_bounds


def get_branch_all_time_customer_summary_counts(branch):
    customer_rows = (
        UserVisitEvent.objects
        .filter(branch=branch, user__isnull=False)
        .values("user_id")
        .annotate(total_visits=Count("id"))
    )

    total_customers = customer_rows.count()
    repeated_customers = customer_rows.filter(total_visits__gt=1).count()
    one_time_customers = customer_rows.filter(total_visits=1).count()

    repeat_rate = 0
    one_time_rate = 0

    if total_customers:
        repeat_rate = round((repeated_customers / total_customers) * 100)
        one_time_rate = round((one_time_customers / total_customers) * 100)

    return {
        "total_customers": total_customers,
        "one_time_customers": one_time_customers,
        "repeated_customers": repeated_customers,
        "returning_rate": repeat_rate,
        "one_time_rate": one_time_rate,
    }


def get_branch_today_customer_summary_counts(branch, day_start, next_day_start):
    previous_visit_exists = UserVisitEvent.objects.filter(
        branch=branch,
        user_id=OuterRef("user_id"),
        created_at__lt=day_start,
    )

    today_customer_rows = (
        UserVisitEvent.objects
        .filter(
            branch=branch,
            user__isnull=False,
            created_at__gte=day_start,
            created_at__lt=next_day_start,
        )
        .values("user_id")
        .distinct()
        .annotate(had_previous_visit=Exists(previous_visit_exists))
    )

    total_today_customers = today_customer_rows.count()
    new_customers = today_customer_rows.filter(had_previous_visit=False).count()
    repeated_customers = today_customer_rows.filter(had_previous_visit=True).count()

    returning_rate = 0
    new_customer_rate = 0

    if total_today_customers:
        returning_rate = round((repeated_customers / total_today_customers) * 100)
        new_customer_rate = round((new_customers / total_today_customers) * 100)

    return {
        "total_today_customers": total_today_customers,
        "new_customers": new_customers,
        "repeated_customers": repeated_customers,
        "returning_rate": returning_rate,
        "new_customer_rate": new_customer_rate,
    }


def build_today_visits_chart_data(today_visit_qs):
    """
    Today visits ni 3-hour buckets ga split chestundi.

    X-axis:
      12 AM = 12 AM to 3 AM
      3 AM  = 3 AM to 6 AM
      ...
      9 PM  = 9 PM to 12 AM

    Y-axis:
      Highest bucket count batti dynamic ga scale avuthundi.
    """
    labels = ["12 AM", "3 AM", "6 AM", "9 AM", "12 PM", "3 PM", "6 PM", "9 PM"]
    values = [0, 0, 0, 0, 0, 0, 0, 0]

    current_tz = timezone.get_current_timezone()

    hour_rows = (
        today_visit_qs
        .annotate(local_hour=ExtractHour("created_at", tzinfo=current_tz))
        .values("local_hour")
        .annotate(total=Count("id"))
        .order_by("local_hour")
    )

    for row in hour_rows:
        hour = row.get("local_hour")
        if hour is None:
            continue

        bucket_index = min(int(hour) // 3, 7)
        values[bucket_index] += row.get("total") or 0

    highest_count = max(values) if values else 0

    if highest_count <= 10:
        y_max = 10
    else:
        y_max = int(math.ceil(highest_count / 10) * 10)

    y_step = max(1, y_max // 5)
    y_axis = [y_max - (y_step * i) for i in range(6)]

    bars = []

    for label, value in zip(labels, values):
        height_percent = 0

        if y_max:
            height_percent = round((value / y_max) * 100, 2)

        bars.append({
            "label": label,
            "value": value,
            "height_percent": height_percent,
        })

    return {
        "bars": bars,
        "y_axis": y_axis,
        "y_max": y_max,
        "highest_count": highest_count,
        "has_data": highest_count > 0,
    }


def get_branch_today_visits_live_data(branch):
    now_ts = timezone.now()
    day_start, next_day_start = get_local_day_bounds(now_ts)

    today_visit_qs = UserVisitEvent.objects.filter(
        branch=branch,
        created_at__gte=day_start,
        created_at__lt=next_day_start,
    )

    today_stats = today_visit_qs.aggregate(
        visits=Count("id"),
        qr_visits=Count("id", filter=Q(visit_method="qr_code")),
        staff_verified=Count(
            "id",
            filter=Q(visit_method__in=["qr_pin", "offer_day_pin"]),
        ),
    )

    today_offer_claims = UserOfferClaim.objects.filter(
        branch=branch,
        issued_at__gte=day_start,
        issued_at__lt=next_day_start,
    ).count()

    customer_counts = get_branch_today_customer_summary_counts(
        branch,
        day_start,
        next_day_start,
    )

    chart_data = build_today_visits_chart_data(today_visit_qs)

    return {
        "visits": today_stats["visits"] or 0,
        "qr_visits": today_stats["qr_visits"] or 0,
        "staff_verified": today_stats["staff_verified"] or 0,
        "offer_claims": today_offer_claims,

        "total_today_customers": customer_counts["total_today_customers"],
        "new_customers": customer_counts["new_customers"],
        "repeated_customers": customer_counts["repeated_customers"],
        "returning_rate": customer_counts["returning_rate"],
        "new_customer_rate": customer_counts["new_customer_rate"],

        # ✅ New chart data for today visits graph
        "chart": chart_data,
    }