# offers/branch_views.py

import json
import re
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.db import models
from django.db.models import Max
from django.http import HttpRequest, JsonResponse, HttpResponseRedirect
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache, cache_control
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from offers.models import ComplementaryOffer
from offers.services.auth.otp_utils import normalize_email, gen_code, now
from offers.services.qr.qr_token_utils import mint_qr_token

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

OTP_TTL_SECS = 5 * 60           # 5 minutes
RESEND_COOLDOWN_SEC = 60        # 60s cooldown between sends
RESEND_WINDOW_MINS = 15         # lookback window
RESEND_WINDOW_MAX = 3           # max sends in window
MAX_VERIFY_ATTEMPTS = 5         # max wrong tries for a single OTP
NEXT_URL_AFTER_LOGIN = "/branch_home/"


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
    """
    Tries exact name match first.
    Fallback: compares cleaned input vs cleaned branch names in Python.
    Best long-term fix: dedicated normalized/branch_code field.
    """
    raw_value = (raw_value or "").strip()
    if not raw_value:
        return None

    branch = Branch.objects.filter(name__iexact=raw_value).only("id", "email", "name", "public_id").first()
    if branch:
        return branch

    cleaned = _clean_branch(raw_value)
    if not cleaned:
        return None

    candidates = Branch.objects.only("id", "email", "name", "public_id")
    for b in candidates:
        if _clean_branch(b.name) == cleaned:
            return b
    return None


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
            created_at__gte=now_ts - timedelta(seconds=RESEND_COOLDOWN_SEC),
        )
        .order_by("-created_at")
        .first()
    )
    if recent:
        remaining = RESEND_COOLDOWN_SEC - int((now_ts - recent.created_at).total_seconds())
        return JsonResponse(
            {"ok": False, "error": f"Please wait {max(1, remaining)}s before requesting again."},
            status=429,
        )

    since = now_ts - timedelta(minutes=RESEND_WINDOW_MINS)
    if BranchOTP.objects.filter(identifier=identifier, created_at__gte=since).count() >= RESEND_WINDOW_MAX:
        return JsonResponse({"ok": False, "error": "Too many requests. Try later."}, status=429)

    code = gen_code()
    row = BranchOTP.objects.create(
        identifier=identifier,
        code_hash=make_password(code),
        expires_at=now_ts + timedelta(seconds=OTP_TTL_SECS),
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

    visit_unit_label = "QR scan + PIN" if visit_unit == "qr_pin" else "QR code"

    return render(
        request,
        "branch/branch_homepage/branch_homepage.html",
        {
            "branch": branch,
            "visit_unit": visit_unit,
            "visit_unit_label": visit_unit_label,
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

    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse(
            {"ok": False, "error": "Invalid email address."},
            status=400,
        )

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
    filter_type = (request.GET.get("filter") or "all").lower()

    base = UserVisitEvent.objects.filter(branch_id=branch_id)

    if filter_type == "today":
        base = base.filter(created_at__date=today)

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