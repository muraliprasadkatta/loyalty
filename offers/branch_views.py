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
from offers.services.branch_api.branch_live_api_service import get_branch_live_api_data
from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404
from django.db.models import Q, Count
from django.utils import timezone

from .models import Branch, UserVisitEvent, UserOfferClaim
from django.template.loader import render_to_string




from offers.services.auth.otp_utils import (
    normalize_email,
    valid_email,
    gen_code,
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

    now_ts = timezone.localtime(timezone.now())
    day_start, next_day_start = get_local_day_bounds(now_ts)

    base = (
        ComplementaryOffer.objects
        .filter(kind="complementary_offer", is_active=True)
        .filter(start_at__lte=now_ts)
        .filter(models.Q(end_at__isnull=True) | models.Q(end_at__gte=now_ts))
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

    today_visits = today_stats["today_visits"] or 0
    today_qr_visits = today_stats["today_qr_visits"] or 0
    today_staff_verified = today_stats["today_staff_verified"] or 0

    today_offer_claims = UserOfferClaim.objects.filter(
        branch=branch,
        issued_at__gte=day_start,
        issued_at__lt=next_day_start,
    ).count()

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
        },
    )


def branch_logout_view(request):
    request.session.pop("branch_id", None)
    request.session.pop("branch_name", None)
    _clear_branch_staff_session(request)
    request.session.modified = True
    return redirect(reverse("offers:branch_login"))


@require_POST
@csrf_protect
@require_branch_session
def branch_staff_create_view(request):
    branch_id = request.session.get("branch_id")
    data = _json(request)

    raw_name = (data.get("staff_name") or "").strip()
    email = normalize_email(data.get("staff_email") or "")
    raw_staff_id = (data.get("staff_id") or "").strip()

    if not raw_name or not email or not raw_staff_id:
        return JsonResponse({"ok": False, "error": "Name, email, and staff ID are required."}, status=400)

    name = raw_name.upper()
    if len(name) > 12 or not all(ch.isalpha() or ch.isspace() for ch in name):
        return JsonResponse(
            {"ok": False, "error": "Staff name must be letters only (A–Z) and max 12 characters."},
            status=400,
        )

    staff_id = raw_staff_id.upper()
    if len(staff_id) > 8 or not staff_id.isalnum():
        return JsonResponse(
            {"ok": False, "error": "Staff ID must be letters/numbers only, max 8 characters."},
            status=400,
        )

    if not valid_email(email):
        return JsonResponse({"ok": False, "error": "Invalid email address."}, status=400)

    if BranchStaff.objects.filter(branch_id=branch_id, staff_id=staff_id).exists():
        return JsonResponse({"ok": False, "error": "Staff ID already exists in this branch."}, status=400)

    if BranchStaff.objects.filter(branch_id=branch_id, email__iexact=email).exists():
        return JsonResponse({"ok": False, "error": "Email already exists in this branch."}, status=400)

    staff = BranchStaff.objects.create(
        branch_id=branch_id,
        name=name,
        email=email,
        staff_id=staff_id,
    )

    return JsonResponse({"ok": True, "id": staff.id})


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



def get_today_new_repeat_customer_counts(branch, day_start, next_day_start):
    """
    Branch-wise today new/repeat customer counts.

    New customer:
      Ee branch lo user's first-ever visit today.

    Repeat customer:
      Ee branch lo user today visit chesadu,
      but same branch lo today mundu previous visit already undi.
    """

    previous_visit_exists = UserVisitEvent.objects.filter(
        branch=branch,
        user_id=OuterRef("user_id"),
        created_at__lt=day_start,
    )

    today_users = (
        UserVisitEvent.objects
        .filter(
            branch=branch,
            user__isnull=False,
            created_at__gte=day_start,
            created_at__lt=next_day_start,
        )
        .values("user_id")
        .distinct()
        .annotate(
            had_previous_visit=Exists(previous_visit_exists)
        )
    )

    repeated_customers = today_users.filter(
        had_previous_visit=True
    ).count()

    new_customers = today_users.filter(
        had_previous_visit=False
    ).count()

    total_today_customers = new_customers + repeated_customers

    returning_rate = 0
    if total_today_customers:
        returning_rate = round(
            (repeated_customers / total_today_customers) * 100
        )

    return {
        "new_customers": new_customers,
        "repeated_customers": repeated_customers,
        "returning_rate": returning_rate,
        "total_today_customers": total_today_customers,
    }



def build_branch_visits_context(request, branch):
    q = (request.GET.get("q") or "").strip()
    method = (request.GET.get("method") or "").strip()
    date_str = (request.GET.get("date") or "").strip()

    # ✅ Today bounds once calculate chestham
    now_ts = timezone.localtime(timezone.now())
    day_start, next_day_start = get_local_day_bounds(now_ts)

    # ✅ Branch-wise all-time customer summary counts
    customer_counts = get_branch_customer_summary_counts(branch)

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

    total_visits = qs.count()

    # ✅ created_at__date avoid cheyyadam better.
    # Today count ki range filter faster and timezone-safe.
    today_visits = qs.filter(
        created_at__gte=day_start,
        created_at__lt=next_day_start,
    ).count()

    unique_users = (
        qs
        .exclude(user__isnull=True)
        .values("user_id")
        .distinct()
        .count()
    )

    qr_pin_visits = qs.filter(visit_method="qr_pin").count()

    total_claims = UserOfferClaim.objects.filter(
        visit_event__in=qs
    ).count()

    claimed_visit_count = (
        UserOfferClaim.objects
        .filter(visit_event__in=qs)
        .values("visit_event_id")
        .distinct()
        .count()
    )

    claim_rate = 0
    if total_visits:
        claim_rate = round((claimed_visit_count / total_visits) * 100) 

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

        "total_visits": total_visits,
        "today_visits": today_visits,
        "unique_users": unique_users,
        "qr_pin_visits": qr_pin_visits,
        "total_claims": total_claims,
        "claim_rate": claim_rate,

        # ✅ New / repeat customer cards
        # ✅ Branch all-time customer summary cards
        "one_time_customers": customer_counts["one_time_customers"],

        # temporary alias: template old variable use chesthe break avvakudadhu
        "new_customers": customer_counts["one_time_customers"],

        "repeated_customers": customer_counts["repeated_customers"],
        "returning_rate": customer_counts["returning_rate"],

        "q": q,
        "method": method,
        "date": date_str,
        "page_obj": page_obj,
    }


def get_branch_all_time_customer_counts(branch):
    """
    Branch-wise all-time customer counts.

    One-time customer:
      Ee branch lo exactly 1 visit unna user.

    Repeat customer:
      Ee branch lo 2 or more visits unna user.

    Repeat rate:
      repeat customers / total unique customers * 100
    """

    customer_rows = (
        UserVisitEvent.objects
        .filter(branch=branch, user__isnull=False)
        .values("user_id")
        .annotate(total_visits=Count("id"))
    )

    total_customers = customer_rows.count()

    repeated_customers = customer_rows.filter(
        total_visits__gt=1
    ).count()

    one_time_customers = customer_rows.filter(
        total_visits=1
    ).count()

    repeat_rate = 0
    if total_customers:
        repeat_rate = round(
            (repeated_customers / total_customers) * 100
        )

    return {
        "total_customers": total_customers,
        "one_time_customers": one_time_customers,
        "repeated_customers": repeated_customers,
        "returning_rate": repeat_rate,
    }


def get_branch_customer_summary_counts(branch):
    """
    Branch-wise all-time customer counts.

    One-time customer:
      Ee branch lo exactly 1 visit unna user.

    Repeat customer:
      Ee branch lo 2 or more visits unna user.

    Repeat rate:
      repeat customers / total unique customers * 100
    """

    customer_rows = (
        UserVisitEvent.objects
        .filter(branch=branch, user__isnull=False)
        .values("user_id")
        .annotate(total_visits=Count("id"))
    )

    total_customers = customer_rows.count()

    repeated_customers = customer_rows.filter(
        total_visits__gt=1
    ).count()

    one_time_customers = customer_rows.filter(
        total_visits=1
    ).count()

    repeat_rate = 0
    if total_customers:
        repeat_rate = round(
            (repeated_customers / total_customers) * 100
        )

    return {
        "total_customers": total_customers,
        "one_time_customers": one_time_customers,
        "repeated_customers": repeated_customers,
        "returning_rate": repeat_rate,
    }


@require_branch_session
def branch_all_visits_live(request):
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
def branch_all_visits(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    context = build_branch_visits_context(request, branch)

    return render(
        request,
        "branch/branch_all_visits/branch_all_visits.html",
        context,
    )


from django.shortcuts import render, get_object_or_404
from django.db.models import Q
from django.utils import timezone

from .models import Branch, UserOfferClaim

@require_branch_session
def branch_all_claims(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    qs = (
        UserOfferClaim.objects
        .filter(branch=branch)
        .select_related(
            "user",
            "user__profile",
            "offer",
            "visit_event",
        )
        .order_by("-issued_at")
    )

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    date_str = (request.GET.get("date") or "").strip()

    if q:
        qs = qs.filter(
            Q(user__email__icontains=q) |
            Q(user__first_name__icontains=q) |
            Q(user__last_name__icontains=q) |
            Q(offer__title__icontains=q) |
            Q(token__icontains=q) |
            Q(staff_name__icontains=q) |
            Q(staff_code__icontains=q)
        )

    if status:
        qs = qs.filter(status=status)

    if date_str:
        qs = qs.filter(issued_at__date=date_str)

    total_claims = qs.count()
    issued_claims = qs.filter(status="issued").count()
    redeemed_claims = qs.filter(status="redeemed").count()
    cancelled_claims = qs.filter(status="cancelled").count()
    today_claims = qs.filter(issued_at__date=timezone.localdate()).count()

    context = {
        "branch": branch,
        "claims": qs[:100],

        "total_claims": total_claims,
        "today_claims": today_claims,
        "issued_claims": issued_claims,
        "redeemed_claims": redeemed_claims,
        "cancelled_claims": cancelled_claims,

        "q": q,
        "status": status,
        "date": date_str,
    }

    return render(
        request,
        "branch/branch_all_claims/branch_all_claims.html",
        context,
    )



@require_branch_session
def branch_live_api(request):
    branch_id = request.session.get("branch_id")
    branch = get_object_or_404(Branch, id=branch_id)

    return JsonResponse({
        "ok": True,
        **get_branch_live_api_data(branch),
    })