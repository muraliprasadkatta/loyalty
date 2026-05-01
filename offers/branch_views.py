# offers/branch_views.py

import json
import re
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.db import models
from django.db.models import Max
from django.http import HttpRequest, JsonResponse, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache, cache_control
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from offers.services.common.time_helpers import get_local_day_bounds

from offers.models import ComplementaryOffer
from offers.services.qr.qr_token_utils import mint_qr_token
from offers.models import Branch, UserVisitEvent, UserOfferClaim
from django.db.models import Q, Count, Exists, OuterRef
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count
from django.utils import timezone
from django.db.models.functions import ExtractHour
from .models import Branch, UserVisitEvent, UserOfferClaim
from django.template.loader import render_to_string

from offers.services.branch_api.branch_today_metrics_service import (
    get_branch_all_time_customer_summary_counts,
    get_branch_today_customer_summary_counts,
    get_branch_today_visits_live_data,
)



from offers.services.auth.otp_utils import (
    normalize_email,
    valid_email,
    gen_code,
    hash_code,
    codes_match,
    now,
    in_cooldown,
    OTP_TTL_MINUTES,
    RESEND_COOLDOWN_SECONDS,
    RESEND_WINDOW_MINUTES,
    MAX_RESENDS_PER_15M,
    MAX_VERIFY_ATTEMPTS,
)

from .models import (
    Branch,
    BranchOTP,
    BranchStaff,
    BranchStaffEmailOTP,
    QRToken,
    YashPin,
    UserVisitEvent,
    Profile,
    LoginVisit,
)

# ===== Config =====




# ===== Guard: branch/admin access =====

def _wants_json(request):
    accept = request.headers.get("Accept", "")
    xrw = request.headers.get("X-Requested-With", "")
    ctype = request.headers.get("Content-Type", "")
    return (
        xrw == "XMLHttpRequest"
        or "application/json" in accept
        or "application/json" in ctype
    )


def has_branch_session(request) -> bool:
    return bool(request.session.get("branch_id"))


def require_branch_session(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if has_branch_session(request):
            return view_func(request, *args, **kwargs)
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": "Branch auth required"}, status=401)
        return HttpResponseRedirect(reverse("offers:branch_login"))
    return _wrapped


def require_branch_or_admin(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        ok = has_branch_session(request) or (
            request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser)
        )
        if ok:
            return view_func(request, *args, **kwargs)
        if _wants_json(request):
            return JsonResponse({"ok": False, "error": "Auth required"}, status=401)
        return HttpResponseRedirect(reverse("offers:branch_login"))
    return _wrapped


def get_branch_from_session(request):
    return {
        "id": request.session.get("branch_id"),
        "name": request.session.get("branch_name"),
    }


# ===== Helpers =====

def _json(req: HttpRequest):
    try:
        return json.loads(req.body.decode("utf-8") or "{}")
    except Exception:
        return {}


def _clean_branch(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (v or "").strip().lower())


def _find_branch_by_input(raw_value: str):
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return None

    cleaned = _clean_branch(raw_value)
    if not cleaned:
        return None

    return (
        Branch.objects
        .filter(name__iexact=cleaned)
        .only("id", "email", "name", "public_id")
        .first()
    )



def _resolve_branch_and_identifier(data):
    """
    Returns:
        branch, identifier(normalized lower), staff_obj_or_none, error_response_or_none
    """
    raw_branch = (data.get("branch") or "").strip()
    raw_identifier = (data.get("identifier") or "").strip()

    if not raw_branch:
        return None, None, None, JsonResponse({"ok": False, "error": "Branch required."}, status=400)

    branch = _find_branch_by_input(raw_branch)
    if not branch:
        return None, None, None, JsonResponse({"ok": False, "error": "Branch not found."}, status=404)

    if raw_identifier:
        identifier = normalize_email(raw_identifier)
    else:
        if not branch.email:
            return None, None, None, JsonResponse(
                {"ok": False, "error": "No email configured for this branch."},
                status=400,
            )
        identifier = normalize_email(branch.email)

    branch_email = normalize_email(branch.email)
    staff_obj = None

    if branch_email and identifier == branch_email:
        return branch, identifier, None, None

    staff_obj = (
        BranchStaff.objects
        .filter(branch=branch, email__iexact=identifier)
        .only("id", "name", "staff_id", "email")
        .first()
    )
    if staff_obj:
        return branch, identifier, staff_obj, None

    return None, None, None, JsonResponse(
        {"ok": False, "error": "Email not linked to this branch."},
        status=400,
    )


def _clear_branch_staff_session(request):
    request.session.pop("branch_staff_id", None)
    request.session.pop("branch_staff_name", None)
    request.session.pop("branch_staff_code", None)


def _set_branch_session(request, branch, staff=None):
    request.session["branch_id"] = branch.id
    request.session["branch_name"] = branch.name

    _clear_branch_staff_session(request)

    if staff:
        request.session["branch_staff_id"] = staff.id
        request.session["branch_staff_name"] = staff.name
        request.session["branch_staff_code"] = staff.staff_id or ""

    request.session.modified = True


# ===== Views =====

@cache_control(no_store=True, no_cache=True, must_revalidate=True)
@never_cache
def branch_login_view(request):
    if request.session.get("branch_id"):
        return redirect("offers:branch_home")

    if request.user.is_authenticated and not getattr(request.user, "is_admin", False):
        return redirect("offers:user_home")

    return render(request, "branch/branch_registration/branch_login.html")


def branch_check_view(request):
    """
    GET /branch/check?name=...  → {ok: true, exists: bool, email?: "...", staff?: [...]}
    """
    name = (request.GET.get("name") or "").strip()
    if not name:
        return JsonResponse({"ok": True, "exists": False})

    branch = _find_branch_by_input(name)
    if not branch:
        return JsonResponse({"ok": True, "exists": False})

    staff_qs = (
        BranchStaff.objects
        .filter(branch=branch)
        .exclude(staff_id__isnull=True)
        .exclude(staff_id="")
        .values("id", "name", "staff_id", "email")
        .order_by("name")
    )

    return JsonResponse({
        "ok": True,
        "exists": True,
        "email": (branch.email or ""),
        "staff": list(staff_qs),
    })


@require_POST
def branch_otp_send(request: HttpRequest):
    """
    IN  : { "branch": "<branch>", "identifier": "<email>" }
    OUT : { "ok": true } | { "ok": false, "error": "..." }

    identifier:
      - If empty -> uses Branch.email
      - If given -> must match branch email OR a staff email of that branch
    """
    data = _json(request)
    branch, identifier, staff_obj, error = _resolve_branch_and_identifier(data)
    if error:
        return error

    now_ts = now()

    recent = (
        BranchOTP.objects
        .filter(
            identifier=identifier,
            created_at__gte=now_ts - timedelta(seconds=RESEND_COOLDOWN_SECONDS),
        )
        .order_by("-created_at")
        .first()
    )
    if recent:
        cooling, wait = in_cooldown(recent.created_at)
        if cooling:
            return JsonResponse(
                {"ok": False, "error": f"Please wait {max(1, wait)}s before requesting again."},
                status=429,
            )

    since = now_ts - timedelta(minutes=RESEND_WINDOW_MINUTES)
    if BranchOTP.objects.filter(identifier=identifier, created_at__gte=since).count() >= MAX_RESENDS_PER_15M:
        return JsonResponse({"ok": False, "error": "Too many requests. Try later."}, status=429)

    code = gen_code()
    row = BranchOTP.objects.create(
        identifier=identifier,
        code_hash=make_password(code),
        expires_at=now_ts + timedelta(minutes=OTP_TTL_MINUTES),
        attempts=0,
        used=False,
        sent_count=1,
    )

    if staff_obj:
        subject = f"Staff Login OTP · {branch.name}"
        who_line = f"Staff: {staff_obj.staff_id or ''} {staff_obj.name}".strip()
    else:
        subject = f"Branch Login OTP · {branch.name}"
        who_line = f"Branch: {branch.name}"

    try:
        send_mail(
            subject=subject,
            message=(
                f"Your one-time code is {code}. It expires in 5 minutes.\n"
                f"{who_line}"
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            recipient_list=[identifier],
            fail_silently=False,
        )
    except Exception:
        row.delete()
        return JsonResponse({"ok": False, "error": "Failed to send OTP email."}, status=500)

    return JsonResponse({"ok": True})


@require_POST
def branch_otp_verify(request: HttpRequest):
    """
    IN : { "branch": "<branch>", "otp": "123456", "identifier": "<email>" }
    OUT: { "ok": true, "next": "/branch_home/" } OR { "ok": false, "error": "..." }
    """
    data = _json(request)
    otp = (data.get("otp") or "").strip()

    if not otp:
        return JsonResponse({"ok": False, "error": "Enter OTP."}, status=400)

    branch, identifier, staff_obj, error = _resolve_branch_and_identifier(data)
    if error:
        return error

    now_ts = now()

    row = (
        BranchOTP.objects
        .filter(identifier=identifier, used=False, expires_at__gte=now_ts)
        .order_by("-created_at")
        .first()
    )

    if not row:
        return JsonResponse({"ok": False, "error": "OTP expired or not found."}, status=400)

    if (row.attempts or 0) >= MAX_VERIFY_ATTEMPTS:
        return JsonResponse({"ok": False, "error": "Too many attempts. Request a new OTP."}, status=429)

    ok = check_password(otp, row.code_hash)

    row.attempts = (row.attempts or 0) + 1
    if ok:
        row.used = True
    row.save(update_fields=["attempts", "used"])

    if not ok:
        return JsonResponse({"ok": False, "error": "Invalid OTP."}, status=400)

    _set_branch_session(request, branch, staff=staff_obj)

    next_url = reverse("offers:branch_home")
    return JsonResponse({"ok": True, "next": next_url})


@never_cache
@require_branch_session
def branch_home_view(request):
    branch_ctx = get_branch_from_session(request)
    bid = branch_ctx["id"]

    branch = get_object_or_404(
        Branch.objects.only("id", "name", "public_id"),
        pk=bid,
    )

    now_ts = timezone.now()
    local_now = timezone.localtime(now_ts)
    day_start, next_day_start = get_local_day_bounds(now_ts)

    base = (
        ComplementaryOffer.objects
        .filter(kind="complementary_offer", is_active=True)
        .filter(start_at__lte=local_now)
        .filter(models.Q(end_at__isnull=True) | models.Q(end_at__gte=local_now))
        .only("id", "visit_unit", "all_branches", "start_at")
    )

    offer = (
        base.filter(all_branches=False, eligible_branches__id=branch.id)
        .order_by("-start_at", "-id")
        .first()
    )

    if not offer:
        offer = (
            base.filter(all_branches=True)
            .order_by("-start_at", "-id")
            .first()
        )

    visit_unit = (offer.visit_unit or "qr_pin") if offer else "qr_pin"
    if visit_unit not in ("qr_pin", "qr_code"):
        visit_unit = "qr_pin"

    visit_unit_label = "QR scan + Code" if visit_unit == "qr_pin" else "QR code"

    today_visit_qs = UserVisitEvent.objects.filter(
        branch=branch,
        created_at__gte=day_start,
        created_at__lt=next_day_start,
    )

    today_stats = today_visit_qs.aggregate(
        today_visits=Count("id"),
        today_qr_visits=Count(
            "id",
            filter=Q(visit_method="qr_code"),
        ),
        today_staff_verified=Count(
            "id",
            filter=Q(visit_method__in=["qr_pin", "offer_day_pin"]),
        ),
    )

    today_customer_counts = get_branch_today_customer_summary_counts(
        branch,
        day_start,
        next_day_start,
    )

    today_visits = today_stats["today_visits"] or 0
    today_qr_visits = today_stats["today_qr_visits"] or 0
    today_staff_verified = today_stats["today_staff_verified"] or 0

    today_offer_claims = UserOfferClaim.objects.filter(
        branch=branch,
        issued_at__gte=day_start,
        issued_at__lt=next_day_start,
    ).count()
    today_live_data = get_branch_today_visits_live_data(branch)
    return render(
        request,
        "branch/branch_homepage/branch_homepage.html",
        {
            "branch": branch,
            "visit_unit": visit_unit,
            "visit_unit_label": visit_unit_label,

            "today_visits": today_visits,
            "today_qr_visits": today_qr_visits,
            "today_staff_verified": today_staff_verified,
            "today_offer_claims": today_offer_claims,
            "total_today_customers": today_customer_counts["total_today_customers"],
            "new_customers": today_customer_counts["new_customers"],
            "repeated_customers": today_customer_counts["repeated_customers"],
            "returning_rate": today_customer_counts["returning_rate"],
            "new_customer_rate": today_customer_counts["new_customer_rate"],
            "today_chart": today_live_data["chart"],
        },
    )


def branch_logout_view(request):
    request.session.pop("branch_id", None)
    request.session.pop("branch_name", None)
    _clear_branch_staff_session(request)
    request.session.modified = True
    return redirect(reverse("offers:branch_login"))



@require_branch_session
def branch_user_visit_list(request):
    branch_id = request.session.get("branch_id")
    today = timezone.localdate()
    now_ts = timezone.now()
    day_start, next_day_start = get_local_day_bounds(now_ts)
    filter_type = (request.GET.get("filter") or "all").lower()

    base = UserVisitEvent.objects.filter(branch_id=branch_id)

    if filter_type == "today":
        base = base.filter(
            created_at__gte=day_start,
            created_at__lt=next_day_start,
        )

    qs = (
        base.values("user_id")
        .annotate(last_visit=Max("created_at"))
        .order_by("-last_visit")
    )

    user_ids = [row["user_id"] for row in qs]

    name_map = {}
    if user_ids:
        profiles = Profile.objects.filter(user_id__in=user_ids).values("user_id", "display_name")
        for p in profiles:
            name_map[p["user_id"]] = (p["display_name"] or "").strip()

    users = []
    for row in qs:
        uid = row["user_id"]
        users.append({
            "user_id": uid,
            "name": name_map.get(uid) or f"User {uid}",
            "last_visit": row["last_visit"].isoformat() if row["last_visit"] else None,
        })

    return JsonResponse({
        "ok": True,
        "branch_id": branch_id,
        "filter": filter_type,
        "date": today.isoformat(),
        "count": len(users),
        "users": users,
    })




from collections import OrderedDict

from django.db.models import Q
from django.shortcuts import get_object_or_404, render
from django.utils import timezone

from offers.models import Branch, UserVisitEvent


def mask_email_for_staff(email: str) -> str:
    email = (email or "").strip()
    if not email or "@" not in email:
        return ""

    name, domain = email.split("@", 1)
    if not name or not domain:
        return ""

    visible_tail = name[-4:] if len(name) >= 4 else name
    return f"Mail ******{visible_tail}@{domain}"


@require_branch_session
def branch_all_visits(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    context = build_branch_visits_context(request, branch)

    return render(
        request,
        "branch/branch_all_visits/branch_all_visits.html",
        context,
    )


def build_branch_visits_context(request, branch):
    q = (request.GET.get("q") or "").strip()
    method = (request.GET.get("method") or "").strip()
    date_str = (request.GET.get("date") or "").strip()

    # ✅ Today bounds once calculate chestham
    now_ts = timezone.localtime(timezone.now())
    day_start, next_day_start = get_local_day_bounds(now_ts)

    # ✅ Branch-wise all-time customer summary counts
    # Search/filter ki link undadhu
    customer_counts = get_branch_all_time_customer_summary_counts(branch)


    # ======================================================
    # ✅ CARD / OVERVIEW METRICS
    # These should be branch overall data.
    # Search/filter ki link avvakudadhu.
    # ======================================================
    all_branch_visits_qs = UserVisitEvent.objects.filter(branch=branch)

    total_visits = all_branch_visits_qs.count()

    today_visits = all_branch_visits_qs.filter(
        created_at__gte=day_start,
        created_at__lt=next_day_start,
    ).count()

    unique_users = (
        all_branch_visits_qs
        .exclude(user__isnull=True)
        .values("user_id")
        .distinct()
        .count()
    )

    qr_pin_visits = all_branch_visits_qs.filter(
        visit_method="qr_pin"
    ).count()

    # ✅ Total offer claims for this branch overall
    # Current old logic: visit_event__in=qs
    # New logic: all branch data
    total_claims = UserOfferClaim.objects.filter(
        visit_event__branch=branch
    ).count()

    # ✅ Claim rate should not cross 100%.
    # So we count distinct visits that have at least one claim.
    claimed_visit_count = (
        UserOfferClaim.objects
        .filter(visit_event__branch=branch)
        .values("visit_event_id")
        .distinct()
        .count()
    )

    claim_rate = 0
    if total_visits:
        claim_rate = round((claimed_visit_count / total_visits) * 100)

    # ======================================================
    # ✅ TABLE DATA
    # Search/filter only table ki apply avvali.
    # Cards/percentages ki apply avvakudadhu.
    # ======================================================
    qs = (
        UserVisitEvent.objects
        .filter(branch=branch)
        .order_by("-created_at")
    )

    if q:
        qs = qs.filter(
            Q(user__email__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(user__profile__display_name__icontains=q) |
            Q(token__icontains=q)
        )

    if method:
        qs = qs.filter(visit_method=method)

    if date_str:
        qs = qs.filter(created_at__date=date_str)

    customer_rows = (
        qs
        .exclude(user__isnull=True)
        .values("user_id")
        .annotate(
            latest_visit_at=Max("created_at"),
            user_total_visits=Count("id"),
        )
        .order_by("-latest_visit_at")
    )

    CUSTOMERS_PER_PAGE = 50
    HISTORY_LIMIT_PER_USER = 30

    paginator = Paginator(customer_rows, CUSTOMERS_PER_PAGE)

    page_number = request.GET.get("page") or 1
    page_obj = paginator.get_page(page_number)

    page_user_ids = [row["user_id"] for row in page_obj.object_list]

    page_visits_qs = (
        qs
        .filter(user_id__in=page_user_ids)
        .select_related("user", "user__profile")
        .order_by("-created_at")
    )

    visit_list = list(page_visits_qs)
    visit_ids = [visit.id for visit in visit_list]

    claim_counts = {}

    if visit_ids:
        claim_counts = {
            row["visit_event_id"]: row["claim_count"]
            for row in (
                UserOfferClaim.objects
                .filter(visit_event_id__in=visit_ids)
                .values("visit_event_id")
                .annotate(claim_count=Count("id"))
            )
        }

    grouped = OrderedDict()

    for visit in visit_list:
        visit.claim_count = claim_counts.get(visit.id, 0)
        visit.has_offer_claim = visit.claim_count > 0

        key = f"user-{visit.user_id}"

        if key not in grouped:
            grouped[key] = {
                "user": visit.user,
                "masked_email": mask_email_for_staff(visit.user.email) if visit.user else "",
                "total_visits": 1,
                "latest_visit": visit,

                # ✅ Initial render lo latest 30 visits matrame show chestham
                "all_visits": [visit],
                "history_limit": HISTORY_LIMIT_PER_USER,
                "has_more_history": False,

                "total_claims": visit.claim_count,
            }
        else:
            grouped[key]["total_visits"] += 1

            if len(grouped[key]["all_visits"]) < HISTORY_LIMIT_PER_USER:
                grouped[key]["all_visits"].append(visit)
            else:
                grouped[key]["has_more_history"] = True

            grouped[key]["total_claims"] += visit.claim_count

    visits = list(grouped.values())

    return {
        "branch": branch,
        "visits": visits,

        # ✅ These are now branch overall card values
        # Search/filter tho change avvavu
        "total_visits": total_visits,
        "today_visits": today_visits,
        "unique_users": unique_users,
        "qr_pin_visits": qr_pin_visits,
        "total_claims": total_claims,
        "claim_rate": claim_rate,

        # Optional, template lo use cheyyali ante available untundhi
        "claimed_visit_count": claimed_visit_count,

        # ✅ Branch all-time customer summary cards
        "one_time_customers": customer_counts["one_time_customers"],
        "one_time_customer_percentage": customer_counts["one_time_rate"],

        # temporary alias: template old variable use chesthe break avvakudadhu
        "new_customers": customer_counts["one_time_customers"],

        "total_customers": customer_counts["total_customers"],
        "repeated_customers": customer_counts["repeated_customers"],

        # repeat customer percentage
        "returning_rate": customer_counts["returning_rate"],
        "repeat_customer_percentage": customer_counts["returning_rate"],

        # ✅ Search/filter values table kosam
        "q": q,
        "method": method,
        "date": date_str,
        "page_obj": page_obj,
    }



@require_branch_session
def branch_today_visits_live(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    today_data = get_branch_today_visits_live_data(branch)

    return JsonResponse({
        "ok": True,
        "today": today_data,
    })


@require_branch_session
def branch_all_visits_table_live(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    context = build_branch_visits_context(request, branch)

    meta_html = render_to_string(
        "branch/branch_all_visits/partials/allvisits_record_table/visits_meta.html",
        context,
        request=request,
    )

    table_body_html = render_to_string(
        "branch/branch_all_visits/partials/allvisits_record_table/visits_table_body.html",
        context,
        request=request,
    )

    pagination_html = render_to_string(
        "branch/branch_all_visits/partials/allvisits_record_table/visits_pagination.html",
        context,
        request=request,
    )

    return JsonResponse({
        "ok": True,
        "meta_html": meta_html,
        "table_body_html": table_body_html,
        "pagination_html": pagination_html,
        "q": context.get("q", ""),
        "page": context["page_obj"].number if context.get("page_obj") else 1,
    })



@require_branch_session
def branch_visit_history_live(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    user_id = (request.GET.get("user_id") or "").strip()
    history_page = request.GET.get("history_page") or 1
    method = (request.GET.get("method") or "").strip()
    date_str = (request.GET.get("date") or "").strip()

    if not user_id:
        return JsonResponse(
            {"ok": False, "error": "User id required."},
            status=400,
        )

    HISTORY_PER_PAGE = 30

    qs = (
        UserVisitEvent.objects
        .filter(branch=branch, user_id=user_id)
        .select_related("user", "user__profile")
        .order_by("-created_at")
    )

    if method:
        qs = qs.filter(visit_method=method)

    if date_str:
        qs = qs.filter(created_at__date=date_str)

    paginator = Paginator(qs, HISTORY_PER_PAGE)
    page_obj = paginator.get_page(history_page)

    history_visits = list(page_obj.object_list)
    visit_ids = [visit.id for visit in history_visits]

    claim_counts = {}

    if visit_ids:
        claim_counts = {
            row["visit_event_id"]: row["claim_count"]
            for row in (
                UserOfferClaim.objects
                .filter(visit_event_id__in=visit_ids)
                .values("visit_event_id")
                .annotate(claim_count=Count("id"))
            )
        }

    for visit in history_visits:
        visit.claim_count = claim_counts.get(visit.id, 0)

    history_html = render_to_string(
        "branch/branch_all_visits/partials/allvisits_record_table/visits_history_rows.html",
        {"history_visits": history_visits},
        request=request,
    )

    return JsonResponse({
        "ok": True,
        "history_html": history_html,
        "has_next": page_obj.has_next(),
        "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
    })




@require_branch_session
def branch_all_claims(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    context = build_branch_claims_context(request, branch)

    return render(
        request,
        "branch/branch_all_claims/branch_all_claims.html",
        context,
    )


@require_branch_session
def branch_all_claims_table_live(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    context = build_branch_claims_context(request, branch)

    table_body_html = render_to_string(
        "branch/branch_all_claims/partials/claims_record_table/claims_table_body.html",
        context,
        request=request,
    )

    footer_html = render_to_string(
        "branch/branch_all_claims/partials/claims_record_table/claims_table_footer.html",
        context,
        request=request,
    )

    return JsonResponse({
        "ok": True,
        "table_body_html": table_body_html,
        "footer_html": footer_html,
        "q": context.get("q", ""),
        "page": context["page_obj"].number if context.get("page_obj") else 1,
    })

def build_branch_claims_context(request, branch):
    q = (request.GET.get("q") or "").strip()
    method = (request.GET.get("method") or "").strip()
    date_str = (request.GET.get("date") or "").strip()
    claim_count_filter = (request.GET.get("claim_count") or "").strip()

    # Summary cards / sidebar analytics ki unfiltered branch claims
    all_claims_qs = UserOfferClaim.objects.filter(branch=branch)

    # Per customer claim count rows
    # Same data ni dropdown, repeat customers, frequency buckets kosam reuse chestham.
    user_claim_rows = list(
        all_claims_qs
        .exclude(user__isnull=True)
        .values("user_id")
        .annotate(total_user_claims=Count("id"))
    )

    # Auto dropdown options: 1 claim, 2 claims, ... highest claim count varaku
    highest_claim_count = 0

    for row in user_claim_rows:
        claim_count = row.get("total_user_claims") or 0

        if claim_count > highest_claim_count:
            highest_claim_count = claim_count

    claim_count_options = list(range(1, highest_claim_count + 1))

    # Table data ki filtered queryset
    qs = (
        all_claims_qs
        .select_related(
            "user",
            "user__profile",
            "offer",
            "visit_event",
        )
        .order_by("-issued_at")
    )

    if q:
        qs = qs.filter(
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(user__profile__display_name__icontains=q) |
            Q(offer__title__icontains=q) |
            Q(token__icontains=q) |
            Q(staff_name__icontains=q) |
            Q(staff_code__icontains=q)
        )

    if method:
        qs = qs.filter(visit_event__visit_method=method)

    if date_str:
        qs = qs.filter(issued_at__date=date_str)

    # Claim count dropdown filter
    # Example: 3 claims select chesthe, all-time exactly 3 claims unna users claim rows matrame table lo show avuthayi.
    if claim_count_filter.isdigit():
        selected_claim_count = int(claim_count_filter)

        filtered_user_ids = [
            row["user_id"]
            for row in user_claim_rows
            if (row.get("total_user_claims") or 0) == selected_claim_count
        ]

        qs = qs.filter(user_id__in=filtered_user_ids)

    total_claims = all_claims_qs.count()

    # Today claims - local day bounds use chestham
    now_ts = timezone.now()
    day_start, next_day_start = get_local_day_bounds(now_ts)

    today_claims = all_claims_qs.filter(
        issued_at__gte=day_start,
        issued_at__lt=next_day_start,
    ).count()

    # Summary card: 2+ claims chesina customers count
    repeat_claim_customers = sum(
        1
        for row in user_claim_rows
        if (row.get("total_user_claims") or 0) > 1
    )

    # Sidebar: claim frequency buckets
    claim_frequency_map = {
        "5+": 0,
        "4": 0,
        "3": 0,
        "2": 0,
        "1": 0,
    }

    for row in user_claim_rows:
        claim_count = row.get("total_user_claims") or 0

        if claim_count >= 5:
            claim_frequency_map["5+"] += 1
        elif claim_count == 4:
            claim_frequency_map["4"] += 1
        elif claim_count == 3:
            claim_frequency_map["3"] += 1
        elif claim_count == 2:
            claim_frequency_map["2"] += 1
        elif claim_count == 1:
            claim_frequency_map["1"] += 1

    max_bucket_count = max(claim_frequency_map.values()) if claim_frequency_map else 0

    claim_frequency_buckets = []

    for label in ["5+", "4", "3", "2", "1"]:
        count = claim_frequency_map[label]

        percent = 0
        if max_bucket_count:
            percent = round((count / max_bucket_count) * 100)

        claim_frequency_buckets.append({
            "label": label,
            "count": count,
            "percent": percent,
        })

    # Sidebar: peak claim time buckets
    # Breakfast  : 6 AM  - 11 AM
    # Lunch      : 11 AM - 4 PM
    # Dinner     : 4 PM  - 11 PM
    # Late Night : 11 PM - 6 AM
    current_tz = timezone.get_current_timezone()

    claim_hour_rows = (
        all_claims_qs
        .annotate(local_hour=ExtractHour("issued_at", tzinfo=current_tz))
        .values("local_hour")
        .annotate(count=Count("id"))
    )

    claim_time_map = {
        "Breakfast": 0,
        "Lunch": 0,
        "Dinner": 0,
        "Late Night": 0,
    }

    for row in claim_hour_rows:
        hour = row.get("local_hour")
        count = row.get("count") or 0

        if hour is None:
            continue

        if 6 <= hour < 11:
            claim_time_map["Breakfast"] += count
        elif 11 <= hour < 16:
            claim_time_map["Lunch"] += count
        elif 16 <= hour < 23:
            claim_time_map["Dinner"] += count
        else:
            claim_time_map["Late Night"] += count

    peak_claim_times = []


    for label in ["Breakfast", "Lunch", "Dinner", "Late Night"]:
        count = claim_time_map[label]

        percent = 0
        if total_claims:
            percent = round((count / total_claims) * 100)

        peak_claim_times.append({
            "label": label,
            "count": count,
            "percent": percent,
        })

    peak_claim_percent_map = {
        item["label"]: item["percent"]
        for item in peak_claim_times
    }

    # Testing ki 5 okay. Final production lo 50 cheyyi.
    CLAIMS_PER_PAGE = 5

    paginator = Paginator(qs, CLAIMS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    return {
        "branch": branch,
        "claims": page_obj.object_list,
        "page_obj": page_obj,

        "total_claims": total_claims,
        "today_claims": today_claims,
        "repeat_claim_customers": repeat_claim_customers,

        "claim_frequency_buckets": claim_frequency_buckets,
        "peak_claim_times": peak_claim_times,

        "claim_count_options": claim_count_options,
        "claim_count_filter": claim_count_filter,

        "q": q,
        "method": method,
        "date": date_str,

        "breakfast_pct": peak_claim_percent_map.get("Breakfast", 0),
        "lunch_pct": peak_claim_percent_map.get("Lunch", 0),
        "dinner_pct": peak_claim_percent_map.get("Dinner", 0),
        "late_night_pct": peak_claim_percent_map.get("Late Night", 0),
    }



from django.shortcuts import render, get_object_or_404
from offers.models import Branch, BranchStaff


def branch_staff_manage(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    staff_members = (
        BranchStaff.objects
        .filter(branch=branch)
        .order_by("-created_at")
    )

    return render(
        request,
        "branch/branch_staff/branch_staff_manage.html",
        {
            "branch": branch,
            "staff_members": staff_members,
        },
    )



import re
from django.db import transaction, IntegrityError


def generate_branch_staff_id(branch_id, staff_name):
    """
    Branch-wise auto staff ID.

    Examples:
    MURALI  -> MURA001
    NARESH  -> NARE002
    PALLAVI -> PALL003
    """

    base = re.sub(r"[^A-Z0-9]", "", staff_name.upper())[:4]

    if not base:
        base = "STAF"

    next_number = BranchStaff.objects.filter(branch_id=branch_id).count() + 1

    while True:
        staff_id = f"{base}{next_number:03d}"

        exists = BranchStaff.objects.filter(
            branch_id=branch_id,
            staff_id=staff_id,
        ).exists()

        if not exists:
            return staff_id

        next_number += 1






def _validate_staff_payload(data):
    raw_name = (data.get("staff_name") or "").strip()
    email = normalize_email(data.get("staff_email") or "")

    if not raw_name or not email:
        return None, None, JsonResponse(
            {"ok": False, "error": "Name and email are required."},
            status=400,
        )

    name = raw_name.upper()

    if len(name) > 12 or not all(ch.isalpha() or ch.isspace() for ch in name):
        return None, None, JsonResponse(
            {
                "ok": False,
                "error": "Staff name must be letters only (A–Z) and max 12 characters.",
            },
            status=400,
        )

    if not valid_email(email):
        return None, None, JsonResponse(
            {"ok": False, "error": "Invalid email address."},
            status=400,
        )

    return name, email, None


def _branch_staff_otp_salt(branch_id):
    return f"branch_staff_create:{branch_id}"



@require_POST
@csrf_protect
@require_branch_session
def branch_staff_send_otp_view(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch.objects.only("id", "name"), id=branch_id)

    data = _json(request)
    name, email, error = _validate_staff_payload(data)
    if error:
        return error

    if BranchStaff.objects.filter(branch_id=branch_id, email__iexact=email).exists():
        return JsonResponse(
            {"ok": False, "error": "Email already exists in this branch."},
            status=400,
        )

    now_ts = now()

    recent = (
        BranchStaffEmailOTP.objects
        .filter(branch_id=branch_id, email__iexact=email, used=False)
        .order_by("-created_at")
        .first()
    )

    if recent:
        cooling, wait = in_cooldown(recent.last_sent_at or recent.created_at)
        if cooling:
            return JsonResponse(
                {
                    "ok": False,
                    "error": f"Please wait {max(1, wait)}s before requesting again.",
                    "resend_after_sec": max(1, wait),
                },
                status=429,
            )

    since = now_ts - timedelta(minutes=RESEND_WINDOW_MINUTES)

    recent_send_count = BranchStaffEmailOTP.objects.filter(
        branch_id=branch_id,
        email__iexact=email,
        created_at__gte=since,
    ).count()

    if recent_send_count >= MAX_RESENDS_PER_15M:
        return JsonResponse(
            {"ok": False, "error": "Too many OTP requests. Try later."},
            status=429,
        )

    code = gen_code()

    row = BranchStaffEmailOTP.objects.create(
        branch=branch,
        staff_name=name,
        email=email,
        code_hash=hash_code(
            email=email,
            code=code,
            salt=_branch_staff_otp_salt(branch_id),
        ),
        expires_at=now_ts + timedelta(minutes=OTP_TTL_MINUTES),
        attempts=0,
        used=False,
        sent_count=1,
        last_sent_at=now_ts,
    )

    try:
        send_mail(
            subject=f"Staff Email Verification OTP · {branch.name}",
            message=(
                f"Your staff verification code is {code}. "
                f"It expires in {OTP_TTL_MINUTES} minutes.\n"
                f"Branch: {branch.name}\n"
                f"Staff name: {name}"
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        row.delete()
        return JsonResponse(
            {"ok": False, "error": "Failed to send OTP email."},
            status=500,
        )

    return JsonResponse(
        {
            "ok": True,
            "message": "OTP sent to staff email.",
            "resend_after_sec": RESEND_COOLDOWN_SECONDS,
        }
    )

@require_POST
@csrf_protect
@require_branch_session
def branch_staff_verify_otp_and_create_view(request):
    branch_id = request.session.get("branch_id")
    data = _json(request)

    name, email, error = _validate_staff_payload(data)
    if error:
        return error

    otp = (data.get("otp") or data.get("code") or "").strip()

    if not otp:
        return JsonResponse(
            {"ok": False, "error": "Enter OTP."},
            status=400,
        )

    if not otp.isdigit() or len(otp) != 6:
        return JsonResponse(
            {"ok": False, "error": "OTP must be 6 digits."},
            status=400,
        )

    now_ts = now()

    try:
        with transaction.atomic():
            Branch.objects.select_for_update().only("id").get(id=branch_id)

            if BranchStaff.objects.filter(branch_id=branch_id, email__iexact=email).exists():
                return JsonResponse(
                    {"ok": False, "error": "Email already exists in this branch."},
                    status=400,
                )

            row = (
                BranchStaffEmailOTP.objects
                .select_for_update()
                .filter(
                    branch_id=branch_id,
                    email__iexact=email,
                    used=False,
                    expires_at__gte=now_ts,
                )
                .order_by("-created_at")
                .first()
            )

            if not row:
                return JsonResponse(
                    {"ok": False, "error": "OTP expired or not found."},
                    status=400,
                )

            if (row.attempts or 0) >= MAX_VERIFY_ATTEMPTS:
                return JsonResponse(
                    {"ok": False, "error": "Too many attempts. Request a new OTP."},
                    status=429,
                )

            is_valid = codes_match(
                stored_hash=row.code_hash,
                email=email,
                code=otp,
                salt=_branch_staff_otp_salt(branch_id),
            )

            row.attempts = (row.attempts or 0) + 1

            if not is_valid:
                row.save(update_fields=["attempts"])
                return JsonResponse(
                    {"ok": False, "error": "Invalid OTP."},
                    status=400,
                )

            verified_name = row.staff_name
            verified_email = row.email

            staff_id = generate_branch_staff_id(branch_id, verified_name)

            staff = BranchStaff.objects.create(
                branch_id=branch_id,
                name=verified_name,
                email=verified_email,
                staff_id=staff_id,
            )

            row.used = True
            row.used_at = timezone.now()
            row.save(update_fields=["attempts", "used", "used_at"])

    except IntegrityError:
        return JsonResponse(
            {"ok": False, "error": "Staff could not be created. Please try again."},
            status=400,
        )

    return JsonResponse(
        {
            "ok": True,
            "id": staff.id,
            "staff_id": staff.staff_id,
            "message": "Staff email verified and staff created.",
        }
    )





def _branch_staff_edit_otp_salt(branch_id, staff_id):
    return f"branch_staff_edit:{branch_id}:{staff_id}"


@require_POST
@csrf_protect
@require_branch_session
def branch_staff_edit_start_view(request, staff_id):
    """
    Edit staff flow.

    Case 1:
      Same email -> direct update name only.

    Case 2:
      Email changed -> send OTP to new email.
      Final update happens in branch_staff_edit_verify_otp_view.
    """
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch.objects.only("id", "name"), id=branch_id)

    staff = get_object_or_404(
        BranchStaff.objects.only("id", "branch_id", "name", "email", "staff_id"),
        id=staff_id,
        branch_id=branch_id,
    )

    data = _json(request)
    name, email, error = _validate_staff_payload(data)
    if error:
        return error

    old_email = normalize_email(staff.email or "")
    email_changed = old_email.lower() != email.lower()

    duplicate_exists = (
        BranchStaff.objects
        .filter(branch_id=branch_id, email__iexact=email)
        .exclude(id=staff.id)
        .exists()
    )

    if duplicate_exists:
        return JsonResponse(
            {"ok": False, "error": "Email already exists in this branch."},
            status=400,
        )

    # ✅ Same email: no OTP required, update name directly.
    if not email_changed:
        staff.name = name
        staff.save(update_fields=["name", "updated_at"])

        return JsonResponse(
            {
                "ok": True,
                "updated": True,
                "otp_required": False,
                "id": staff.id,
                "staff_id": staff.staff_id,
                "name": staff.name,
                "email": staff.email,
                "message": "Staff updated successfully.",
            }
        )

    # ✅ Email changed: send OTP to new email.
    now_ts = now()

    recent = (
        BranchStaffEmailOTP.objects
        .filter(branch_id=branch_id, email__iexact=email, used=False)
        .order_by("-created_at")
        .first()
    )

    if recent:
        cooling, wait = in_cooldown(recent.last_sent_at or recent.created_at)
        if cooling:
            return JsonResponse(
                {
                    "ok": False,
                    "error": f"Please wait {max(1, wait)}s before requesting again.",
                    "resend_after_sec": max(1, wait),
                },
                status=429,
            )

    since = now_ts - timedelta(minutes=RESEND_WINDOW_MINUTES)

    recent_send_count = BranchStaffEmailOTP.objects.filter(
        branch_id=branch_id,
        email__iexact=email,
        created_at__gte=since,
    ).count()

    if recent_send_count >= MAX_RESENDS_PER_15M:
        return JsonResponse(
            {"ok": False, "error": "Too many OTP requests. Try later."},
            status=429,
        )

    code = gen_code()

    row = BranchStaffEmailOTP.objects.create(
        branch=branch,
        staff_name=name,
        email=email,
        code_hash=hash_code(
            email=email,
            code=code,
            salt=_branch_staff_edit_otp_salt(branch_id, staff.id),
        ),
        expires_at=now_ts + timedelta(minutes=OTP_TTL_MINUTES),
        attempts=0,
        used=False,
        sent_count=1,
        last_sent_at=now_ts,
    )

    try:
        send_mail(
            subject=f"Staff Email Change OTP · {branch.name}",
            message=(
                f"Your staff email change verification code is {code}. "
                f"It expires in {OTP_TTL_MINUTES} minutes.\n"
                f"Branch: {branch.name}\n"
                f"Staff name: {name}\n"
                f"Staff ID: {staff.staff_id or '-'}"
            ),
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            recipient_list=[email],
            fail_silently=False,
        )
    except Exception:
        row.delete()
        return JsonResponse(
            {"ok": False, "error": "Failed to send OTP email."},
            status=500,
        )

    return JsonResponse(
        {
            "ok": True,
            "updated": False,
            "otp_required": True,
            "message": "OTP sent to new staff email.",
            "resend_after_sec": RESEND_COOLDOWN_SECONDS,
        }
    )


@require_POST
@csrf_protect
@require_branch_session
def branch_staff_edit_verify_otp_view(request, staff_id):
    """
    Verify OTP and update staff name + email.
    Used only when email changed.
    """
    branch_id = request.session.get("branch_id")
    data = _json(request)

    name, email, error = _validate_staff_payload(data)
    if error:
        return error

    otp = (data.get("otp") or data.get("code") or "").strip()

    if not otp:
        return JsonResponse(
            {"ok": False, "error": "Enter OTP."},
            status=400,
        )

    if not otp.isdigit() or len(otp) != 6:
        return JsonResponse(
            {"ok": False, "error": "OTP must be 6 digits."},
            status=400,
        )

    now_ts = now()

    try:
        with transaction.atomic():
            staff = (
                BranchStaff.objects
                .select_for_update()
                .get(id=staff_id, branch_id=branch_id)
            )

            duplicate_exists = (
                BranchStaff.objects
                .filter(branch_id=branch_id, email__iexact=email)
                .exclude(id=staff.id)
                .exists()
            )

            if duplicate_exists:
                return JsonResponse(
                    {"ok": False, "error": "Email already exists in this branch."},
                    status=400,
                )

            row = (
                BranchStaffEmailOTP.objects
                .select_for_update()
                .filter(
                    branch_id=branch_id,
                    email__iexact=email,
                    used=False,
                    expires_at__gte=now_ts,
                )
                .order_by("-created_at")
                .first()
            )

            if not row:
                return JsonResponse(
                    {"ok": False, "error": "OTP expired or not found."},
                    status=400,
                )

            if (row.attempts or 0) >= MAX_VERIFY_ATTEMPTS:
                return JsonResponse(
                    {"ok": False, "error": "Too many attempts. Request a new OTP."},
                    status=429,
                )

            is_valid = codes_match(
                stored_hash=row.code_hash,
                email=email,
                code=otp,
                salt=_branch_staff_edit_otp_salt(branch_id, staff.id),
            )

            row.attempts = (row.attempts or 0) + 1

            if not is_valid:
                row.save(update_fields=["attempts"])
                return JsonResponse(
                    {"ok": False, "error": "Invalid OTP."},
                    status=400,
                )

            # ✅ Use OTP row values as verified source.
            staff.name = row.staff_name
            staff.email = row.email
            staff.save(update_fields=["name", "email", "updated_at"])

            row.used = True
            row.used_at = timezone.now()
            row.save(update_fields=["attempts", "used", "used_at"])

    except BranchStaff.DoesNotExist:
        return JsonResponse(
            {"ok": False, "error": "Staff not found."},
            status=404,
        )
    except IntegrityError:
        return JsonResponse(
            {"ok": False, "error": "Staff could not be updated. Please try again."},
            status=400,
        )

    return JsonResponse(
        {
            "ok": True,
            "updated": True,
            "otp_required": False,
            "id": staff.id,
            "staff_id": staff.staff_id,
            "name": staff.name,
            "email": staff.email,
            "message": "Staff updated successfully.",
        }
    )