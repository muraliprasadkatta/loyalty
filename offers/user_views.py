# offers/user_views.py

from __future__ import annotations

import json
import re
import urllib.parse
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.db import models
from django.conf import settings
from django.contrib.auth import get_user_model, login, logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import check_password
from django.core import signing
from django.core.mail import send_mail
from django.db import transaction, models
from django.db.models import Q, Case, When, Value, IntegerField,Max
from django.db.models.functions import Lower
from django.http import JsonResponse, HttpResponseBadRequest
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache, cache_control
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST
from offers.services.common.time_helpers import get_local_day_bounds
from offers.services.offer_claim.claim_issue_service import issue_offer_claim_if_eligible
from offers.services.qr.qr_token_utils import parse_qr_token as verify_qr_token
from offers.services.offer_eligibility.offer_eligibility_service import build_offer_eligibility_context
import offers.services.offer_eligibility.offers_progress_modal_helper as progress_helper
from django.template.loader import render_to_string
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache
from django.db.models import Case, When, Value, IntegerField
from django.db.models.functions import Lower
import math
from .models import UserOfferClaim
from .models import (
    QRToken,
    YashPin,
    BranchGenerateVisitPin,
    UserVerifyVisitPin,
    UserVisitEvent,
    Profile,
    Branch,
    LoginOTP,
    UserLocationPing,
    ComplementaryOffer,
    LoginVisit,
    UserPendingVisitAttempt,
)

from offers.services.visit_unit.visit_unit import get_active_visit_unit
from offers.services.visit_unit.visit_confirm import (
    confirm_qr_code_visit,
    confirm_qr_code_visit_with_yashpin,
    clear_pending_qr_session,
    set_last_branch_session,
)
from offers.services.pending_visit_attempt.pending_visit_attempt_service import (
    upsert_pending_visit_attempt,
    mark_pending_visit_attempt_completed,
    mark_pending_visit_attempt_cancelled,
    mark_pending_visit_attempt_expired,
    get_user_active_pending_attempts,
)




from offers.services.auth.otp_utils import (
    normalize_email,
    valid_email,
    gen_code,
    hash_code,
    expires_at,
    in_cooldown,
    now,
    MAX_RESENDS_PER_15M,
)


# =========================
# Location save helpers
# =========================

def _dec(v, places=6):
    """Convert to Decimal with fixed places; raises on bad input."""
    d = Decimal(str(v))
    return d.quantize(Decimal("1." + "0" * places))


def _in_range(lat, lon):
    return (-90 <= float(lat) <= 90) and (-180 <= float(lon) <= 180)


@login_required
@require_POST
@csrf_protect
def save_location(request):
    """
    JSON Body:
      { "latitude": 17.3850, "longitude": 78.4867, "accuracy": 12, "source": "browser" }
    Stores a ping row; also (optionally) updates Profile last_* if present.
    """
    try:
        body = json.loads(request.body.decode() or "{}")
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    lat = body.get("latitude")
    lon = body.get("longitude")
    acc = body.get("accuracy")  # optional
    src = (body.get("source") or "browser")[:32]

    if lat is None or lon is None:
        return JsonResponse({"ok": False, "error": "latitude & longitude required"}, status=400)

    try:
        dlat = _dec(lat, 6)
        dlon = _dec(lon, 6)
    except (InvalidOperation, ValueError):
        return JsonResponse({"ok": False, "error": "Invalid coordinates"}, status=400)

    if not _in_range(dlat, dlon):
        return JsonResponse({"ok": False, "error": "Out-of-range coordinates"}, status=400)

    try:
        acc_f = float(acc) if acc is not None else None
        if acc_f is not None and acc_f < 0:
            acc_f = None
    except (TypeError, ValueError):
        acc_f = None

    # 1) Save history row
    row = UserLocationPing.objects.create(
        user=request.user,
        latitude=dlat,
        longitude=dlon,
        accuracy_m=acc_f,
        source=src,
    )

    # 2) (Optional) Update Profile “last_*” if those fields exist
    prof = getattr(request.user, "profile", None)
    if prof is None:
        prof, _ = Profile.objects.get_or_create(user=request.user)

    for fld in ("last_latitude", "last_longitude", "last_loc_accuracy_m", "last_loc_at"):
        if not hasattr(prof, fld):
            break
    else:
        prof.last_latitude = dlat
        prof.last_longitude = dlon
        prof.last_loc_accuracy_m = acc_f
        prof.last_loc_at = timezone.now()
        prof.save(
            update_fields=[
                "last_latitude",
                "last_longitude",
                "last_loc_accuracy_m",
                "last_loc_at",
            ]
        )

    return JsonResponse(
        {
            "ok": True,
            "id": row.id,
            "lat": float(dlat),
            "lon": float(dlon),
            "accuracy_m": acc_f,
            "saved_at": row.created_at.isoformat(),
        }
    )


# =========================
# Public pages
# =========================


@cache_control(no_store=True, no_cache=True, must_revalidate=True)
@never_cache
def user_login_page(request):
    # Branch session active → branch home ki
    if request.session.get("branch_id"):
        return redirect("offers:branch_home")

    # Already authenticated ayithe direct redirect
    if request.user.is_authenticated:
        if request.user.is_superuser:
            return redirect("offers:admin_home")
        return redirect("offers:user_home")

    # Normal GET → login form
    return render(request, "user_registration/user_login.html")


# =========================
# User Home + Name modal flow
# =========================

NAME_RE = re.compile(r"^[^\s].{1,39}$")  # 2–40 chars, Unicode-friendly


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip




@never_cache
def user_home_page(request):
    # Superusers shouldn’t see user home
    if request.user.is_authenticated and request.user.is_superuser:
        return redirect("offers:admin_home")

    client_ip = get_client_ip(request)
    ua = request.META.get("HTTP_USER_AGENT", "")
    today = timezone.localdate()

    now_ts = timezone.now()
    day_start, next_day_start = get_local_day_bounds(now_ts)

    # defaults for guest users
    already_claimed_today = False
    disp = ""
    need_name = False

    # only for authenticated users
    if request.user.is_authenticated:
        LoginVisit.objects.update_or_create(
            user=request.user,
            visit_date=today,
            defaults={
                "source": "login",
                "ip_address": client_ip,
                "user_agent": ua,
            },
        )

        already_claimed_today = UserVisitEvent.objects.filter(
            user=request.user,
            created_at__gte=day_start,
            created_at__lt=next_day_start,
        ).exists()

        prof = getattr(request.user, "profile", None)
        if prof is None:
            prof, _ = Profile.objects.get_or_create(user=request.user)

        disp = (prof.display_name or "").strip()
        need_name = (disp == "")

    # Branch card data only
    branch_card_data = get_home_branch_list_card_data(limit=12)

    return render(
        request,
        "user_interface/user_homepage/user_homepage.html",
        {
            "need_name": need_name,
            "display_name": disp,

            "branch_count": branch_card_data["branch_count"],
            "branches": branch_card_data["branches"],
            "branches_has_more": branch_card_data["branches_has_more"],

            "client_ip": client_ip,
            "oz_already_claimed_today": already_claimed_today,
        },
    )



NEARBY_RADIUS_KM = 50


def get_bounding_box(lat, lon, radius_km):
    """
    Rough lat/lon bounding box before exact distance calculation.
    This reduces branches before Python distance calculation.
    """
    lat = float(lat)
    lon = float(lon)

    lat_delta = radius_km / 111.0
    lon_delta = radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.01))

    return {
        "min_lat": lat - lat_delta,
        "max_lat": lat + lat_delta,
        "min_lon": lon - lon_delta,
        "max_lon": lon + lon_delta,
    }


def calculate_distance_km(lat1, lon1, lat2, lon2):
    radius_km = 6371

    lat1 = math.radians(float(lat1))
    lon1 = math.radians(float(lon1))
    lat2 = math.radians(float(lat2))
    lon2 = math.radians(float(lon2))

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(radius_km * c, 1)


def get_latest_user_location(user):
    if not user or not user.is_authenticated:
        return None

    ping = (
        UserLocationPing.objects
        .filter(user=user)
        .only("latitude", "longitude", "created_at")
        .order_by("-created_at")
        .first()
    )

    if not ping:
        return None

    if ping.latitude is None or ping.longitude is None:
        return None

    return float(ping.latitude), float(ping.longitude)



def get_home_branch_list_card_data(limit=12, offset=0, q="", location="", user=None):
    now_ts = timezone.now()

    q = (q or "").strip()
    location = (location or "").strip()

    try:
        offset = int(offset or 0)
    except (TypeError, ValueError):
        offset = 0
    offset = max(0, offset)

    if limit is not None:
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 12
        limit = max(1, limit)

    user_coords = get_latest_user_location(user)

    branches_qs = Branch.objects.all()

    # Nearby mode optimization:
    # First reduce DB rows using rough lat/lon box, then exact 50km filter later.
    if location == "nearby" and not q and user_coords:
        user_lat, user_lon = user_coords
        box = get_bounding_box(user_lat, user_lon, NEARBY_RADIUS_KM)

        branches_qs = branches_qs.filter(
            latitude__isnull=False,
            longitude__isnull=False,
            latitude__gte=box["min_lat"],
            latitude__lte=box["max_lat"],
            longitude__gte=box["min_lon"],
            longitude__lte=box["max_lon"],
        )

    if q:
        branches_qs = branches_qs.filter(
            Q(name__icontains=q)
            | Q(display_title__icontains=q)
            | Q(location_title__icontains=q)
        )

    # Important:
    # Do NOT DB-slice here, because offer attach / distance / active-first sorting happens below.
    branches = list(branches_qs.order_by(Lower("name")))

    branch_ids = [b.id for b in branches]
    branch_ids_set = set(branch_ids)
    offers_by_branch = {}

    if branch_ids:
        global_offer = (
            ComplementaryOffer.objects
            .filter(
                kind="complementary_offer",
                is_active=True,
                all_branches=True,
                start_at__lte=now_ts,
            )
            .filter(models.Q(end_at__isnull=True) | models.Q(end_at__gte=now_ts))
            .only("id", "title", "offer_image", "start_at", "end_at", "all_branches")
            .order_by("-start_at", "-id")
            .first()
        )

        if global_offer:
            for bid in branch_ids:
                offers_by_branch[bid] = global_offer

        specific_offers = (
            ComplementaryOffer.objects
            .filter(
                kind="complementary_offer",
                is_active=True,
                all_branches=False,
                start_at__lte=now_ts,
                eligible_branches__id__in=branch_ids,
            )
            .filter(models.Q(end_at__isnull=True) | models.Q(end_at__gte=now_ts))
            .only("id", "title", "offer_image", "start_at", "end_at", "all_branches")
            .prefetch_related("eligible_branches")
            .distinct()
            .order_by("-start_at", "-id")
        )

        seen_specific = set()

        for offer in specific_offers:
            for eb in offer.eligible_branches.all():
                bid = eb.id

                if bid not in branch_ids_set:
                    continue

                if bid in seen_specific:
                    continue

                offers_by_branch[bid] = offer
                seen_specific.add(bid)

    for b in branches:
        offer = offers_by_branch.get(b.id)

        if offer:
            b.offer_title = offer.title or ""
            b.offer_start = offer.start_at
            b.offer_end = offer.end_at
            b.offer_image_url = offer.offer_image.url if offer.offer_image else ""
        else:
            b.offer_title = ""
            b.offer_start = None
            b.offer_end = None
            b.offer_image_url = ""

        b.distance_km = None

        if user_coords and b.latitude is not None and b.longitude is not None:
            user_lat, user_lon = user_coords
            b.distance_km = calculate_distance_km(
                user_lat,
                user_lon,
                b.latitude,
                b.longitude,
            )

    # Active offers filter
    if location == "active":
        branches = [b for b in branches if b.offer_start]

    # Nearby exact filter
    is_nearby_mode = False
    nearby_error = ""

    if location == "nearby" and not q:
        if user_coords:
            branches = [
                b for b in branches
                if b.distance_km is not None and b.distance_km <= NEARBY_RADIUS_KM
            ]
            is_nearby_mode = True
        else:
            nearby_error = "Location not saved yet. Use current location first."

    # Ordering
    is_default_all_mode = (not q) and (location in ("", "all"))

    if is_nearby_mode:
        branches.sort(
            key=lambda b: (
                not bool(getattr(b, "offer_start", None)),
                b.distance_km if b.distance_km is not None else 999999,
                b.name.lower(),
            )
        )

    elif is_default_all_mode and user_coords:
        branches.sort(
            key=lambda b: (
                not bool(getattr(b, "offer_start", None)),
                b.distance_km if b.distance_km is not None else 999999,
                b.name.lower(),
            )
        )

    else:
        active_branches = [b for b in branches if b.offer_start]
        inactive_branches = [b for b in branches if not b.offer_start]
        branches = active_branches + inactive_branches

    branch_count = len(branches)

    if limit is not None:
        branches = branches[offset:offset + limit]

    return {
        "branch_count": branch_count,
        "branches": branches,
        "branches_has_more": (offset + len(branches)) < branch_count if limit is not None else False,
        "offset": offset,
        "limit": limit,
        "q": q,
        "location": location,
        "is_nearby_mode": is_nearby_mode,
        "nearby_radius_km": NEARBY_RADIUS_KM,
        "nearby_error": nearby_error,
    }


@login_required
def user_all_branches_view(request):
    q = (request.GET.get("q") or "").strip()
    location = (request.GET.get("location") or "").strip()

    LOAD_STEP = 12

    try:
        offset = int(request.GET.get("offset") or 0)
    except (TypeError, ValueError):
        offset = 0

    offset = max(0, offset)

    branch_card_data = get_home_branch_list_card_data(
        limit=LOAD_STEP,
        offset=offset,
        q=q,
        location=location,
        user=request.user,
    )

    branch_count = branch_card_data["branch_count"]
    branches = branch_card_data["branches"]

    loaded_count = offset + len(branches)
    has_more = loaded_count < branch_count
    next_offset = loaded_count

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        html = render_to_string(
            "user_interface/user_homepage/partials/all_branch_card_append.html",
            {"branches": branches},
            request=request,
        )

        return JsonResponse({
            "ok": True,
            "html": html,
            "loaded_count": loaded_count,
            "branch_count": branch_count,
            "has_more": has_more,
            "next_offset": next_offset,
        })

    return render(
        request,
        "user_interface/user_homepage/partials/branch_all_list.html",
        {
            "branches": branches,
            "branch_count": branch_count,
            "loaded_count": loaded_count,
            "has_more": has_more,
            "offset": offset,
            "next_offset": next_offset,

            "q": branch_card_data["q"],
            "location": branch_card_data["location"],
            "is_nearby_mode": branch_card_data["is_nearby_mode"],
            "nearby_radius_km": branch_card_data["nearby_radius_km"],
            "nearby_error": branch_card_data["nearby_error"],
        },
    )




@login_required
@require_POST
@csrf_protect
def save_display_name(request):
    try:
        body = json.loads(request.body.decode() or "{}")
    except Exception:
        return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)

    name = (body.get("display_name") or "").strip()
    if not (2 <= len(name) <= 40) or not NAME_RE.match(name):
        return JsonResponse({"ok": False, "error": "Enter a valid name (2–40 chars)."}, status=400)

    prof = getattr(request.user, "profile", None)
    if prof is None:
        prof, _ = Profile.objects.get_or_create(user=request.user)

    prof.display_name = name
    prof.save(update_fields=["display_name"])
    request.user.first_name = name
    request.user.save(update_fields=["first_name"])

    return JsonResponse({"ok": True, "name": name})


# =========================
# Email OTP send
# =========================

@require_POST
@csrf_protect
@never_cache
def otp_send(request):
    # Expect JSON: {"email": "..."}
    try:
        body = json.loads(request.body.decode() or "{}")
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    email = normalize_email(body.get("email"))
    if not valid_email(email):
        return JsonResponse({"ok": False, "error": "Invalid email."}, status=400)

    # most recent in last 15m
    recent = (
        LoginOTP.objects.filter(email=email, created_at__gte=now() - timedelta(minutes=15))
        .order_by("-created_at")
        .first()
    )

    if recent:
        cooling, wait = in_cooldown(recent.last_sent_at)
        if cooling:
            return JsonResponse(
                {"ok": False, "error": f"Too many requests. Try again in {wait}s."},
                status=429,
            )
        if recent.sent_count >= MAX_RESENDS_PER_15M:
            return JsonResponse(
                {"ok": False, "error": "Too many requests. Try again later."},
                status=429,
            )

        code = gen_code()
        recent.code_hash = hash_code(email, code)
        recent.expires_at = expires_at()
        recent.sent_count += 1
        recent.last_sent_at = now()
        recent.used = False
        recent.attempts = 0
        recent.save()

        _send_email_otp(email, code)
        return JsonResponse({"ok": True, "message": "OTP sent", "resend_after_sec": 60})

    # fresh row
    code = gen_code()
    LoginOTP.objects.create(
        email=email,
        code_hash=hash_code(email, code),
        expires_at=expires_at(),
        attempts=0,
        used=False,
        sent_count=1,
        last_sent_at=now(),
    )
    _send_email_otp(email, code)
    return JsonResponse({"ok": True, "message": "OTP sent", "resend_after_sec": 60})


def _send_email_otp(email: str, code: str):
    subject = "Your sign-in code"
    body = (
        f"Hi,\n\nYour one-time sign-in code is {code}.\n"
        f"It expires in 5 minutes. Do not share this code.\n\n"
        f"If you didn’t request this, please ignore this email."
    )
    send_mail(subject, body, None, [email], fail_silently=False)


# =========================
# Email OTP verify
# =========================

MAX_VERIFY_ATTEMPTS = 5


def _safe_next_from_request(request, body=None):
    default = reverse("offers:user_home")
    candidate = (
        (body or {}).get("next")
        or request.POST.get("next")
        or request.GET.get("next")
        or default
    )

    if not url_has_allowed_host_and_scheme(
        url=candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return default

    # Only superusers can be sent to /admin...
    if (not request.user.is_superuser) and str(candidate).startswith("/admin"):
        return default

    return candidate


@require_POST
@csrf_protect
@never_cache
def otp_verify(request):
    try:
        body = json.loads(request.body.decode() or "{}")
    except Exception:
        return HttpResponseBadRequest("Invalid JSON")

    email = normalize_email(body.get("email"))
    code = (body.get("code") or "").strip()

    if not valid_email(email):
        return JsonResponse({"ok": False, "error": "Invalid email."}, status=400)
    if not (len(code) == 6 and code.isdigit()):
        return JsonResponse({"ok": False, "error": "Enter a valid 6-digit code."}, status=400)

    row = (
        LoginOTP.objects.filter(email=email, created_at__gte=now() - timedelta(minutes=15))
        .order_by("-created_at")
        .first()
    )
    if not row:
        return JsonResponse({"ok": False, "error": "No active code. Please resend."}, status=400)

    if row.used:
        return JsonResponse({"ok": False, "error": "Code already used. Please resend."}, status=400)
    if row.expires_at <= now():
        return JsonResponse({"ok": False, "error": "Code expired. Please resend."}, status=400)
    if row.attempts >= MAX_VERIFY_ATTEMPTS:
        return JsonResponse(
            {"ok": False, "error": "Too many attempts. Please resend a new code."},
            status=429,
        )

    if row.code_hash != hash_code(email, code):
        row.attempts += 1
        row.save(update_fields=["attempts"])
        return JsonResponse({"ok": False, "error": "Incorrect code."}, status=400)

    # success → consume + login
    row.used = True
    row.save(update_fields=["used"])

    User = get_user_model()
    username_default = email.split("@")[0]
    user, _ = User.objects.get_or_create(
        email=email,
        defaults={"username": username_default},
    )
    login(request, user)

    # ensure profile exists on first user login
    Profile.objects.get_or_create(user=user, defaults={"display_name": ""})

    dest = _safe_next_from_request(request, body=body)
    return JsonResponse({"ok": True, "next": dest})


# =========================
# Logout (user)
# =========================

def user_logout_view(request):
    auth_logout(request)
    return redirect("offers:user_home")


# =========================
# QR token generaton helpers (scan / visit count)
# =========================


TOKEN_PATH_RE = re.compile(r"/qrg/(?:redeem|t)/(?P<tok>[^/?#]+)")


def extract_qr_token_from_raw(raw):
    """
    Try to extract the actual token from a raw string:
    - full URL with /qrg/redeem/<token> or /qrg/t/<token>
    - or plain token-looking string.
    """
    raw = (raw or "").strip()
    if not raw:
        return None

    # 1) If it's a full URL, parse path
    try:
        u = urllib.parse.urlparse(raw)
        if u.scheme and u.netloc:
            m = TOKEN_PATH_RE.search(u.path)
            if m:
                return m.group("tok")
            if "/qrg/redeem/" in u.path:
                return u.path.split("/qrg/redeem/", 1)[1].split("/", 1)[0]
    except Exception:
        pass

    # 2) Otherwise, if it looks like a token already, accept it
    if re.fullmatch(r"[A-Za-z0-9._\-:]+", raw):
        return raw

    return None


SIGN_SALT = "oz.complementary.qr"   # renamed from oz.freeplate.qr


from django.conf import settings

def verify_legacy_colon_token(token: str):
    try:
        ttl = getattr(settings, "QR_TTL_SECS", 180)
        data = signing.loads(
            token,
            salt=SIGN_SALT,
            max_age=ttl + 30
        )
        return {
            "bid": int(data.get("branch")),
            "desk": str(data.get("desk") or "A1"),
            "exp": int(data.get("iat", 0)) + int(data.get("ttl", 0)),
        }
    except Exception as e:
        raise ValueError(f"Legacy token invalid: {e}")


# =========================
# PIN verify (QR PIN)
# =========================


PIN_LEN = 4  # 4-digit


@login_required
@require_POST
@never_cache
@csrf_protect
@cache_control(no_cache=True, no_store=True, must_revalidate=True)
def pin_verify(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        data = {}

    CODE_LEN = 4
    CODE_RE = re.compile(r"^[23456789ABCDEFGHJKMNPQRSTUVWXYZ]{4}$")

    raw_pin = str(data.get("pin") or "").strip().upper()
    pin = raw_pin[:CODE_LEN]

    if not CODE_RE.fullmatch(pin):
        return JsonResponse(
            {"ok": False, "error": "Enter a valid 4-character code."},
            status=400,
        )

    now_ts = timezone.now()
    day_start, next_day_start = get_local_day_bounds(now_ts)
    # -----------------------------------------------------
    # AUTO BRANCH RESOLUTION:
    # Manual code itself should locate the correct branch/context.
    # This is safe only when active codes are unique.
    # -----------------------------------------------------
    base_qs = (
        YashPin.objects
        .select_related("qr_token", "branch")
        .filter(
            expires_at__gte=now_ts,
            used=False,
        )
        .order_by("-created_at")
    )

    def _find_match(qs, limit=120):
        for row in qs[:limit]:
            if check_password(pin, row.pin_hash):
                return row
        return None

    matched = _find_match(base_qs, limit=120)

    if not matched:
        return JsonResponse(
            {"ok": False, "error": "Invalid or expired code."},
            status=400,
        )

    # extra safety: linked QR token must belong to same branch
    if not matched.qr_token or matched.qr_token.branch_id != matched.branch_id:
        return JsonResponse(
            {"ok": False, "error": "Invalid code context. Please ask staff for a new code."},
            status=400,
        )

    # extra safety: linked QR token must still be alive
    if matched.qr_token.expires_at and matched.qr_token.expires_at <= now_ts:
        return JsonResponse(
            {"ok": False, "error": "This code is expired. Please ask staff for a new code."},
            status=400,
        )

    # QR token already used
    if matched.qr_token.used:
        return JsonResponse(
            {"ok": False, "error": "This code is already used. Please ask staff for a new code."},
            status=400,
        )

    # same-day check (per-branch)
    already = UserVisitEvent.objects.filter(
        user=request.user,
        branch=matched.branch,
        created_at__gte=day_start,
        created_at__lt=next_day_start,
    ).exists()
    if already:
        return JsonResponse({
            "ok": True,
            "already_claimed_today": True,
            "next": reverse("offers:user_status"),
        })

    # light attempt tracking
    try:
        matched.attempts = (matched.attempts or 0) + 1
        matched.last_attempt_at = now_ts
        matched.save(update_fields=["attempts", "last_attempt_at"])
    except Exception:
        pass

    # set branch context from matched code
    request.session["last_branch_id"] = matched.branch_id
    request.session["last_branch_name"] = matched.branch.name
    request.session["last_branch_desk"] = matched.desk or ""

    # =====================================================
    # if branch visit_unit is qr_code => confirm immediately
    # =====================================================
    vu = get_active_visit_unit(matched.branch_id, now_ts=now_ts)

    if vu == "qr_code":
        res = confirm_qr_code_visit_with_yashpin(
            user=request.user,
            yashpin_id=matched.id,
            now_ts=now_ts,
            used_via="pin",
        )

        if not res.ok:
            return JsonResponse(
                {"ok": False, "error": res.error or "Unable to confirm visit."},
                status=400,
            )

        if res.already_claimed_today:
            return JsonResponse({
                "ok": True,
                "already_claimed_today": True,
                "next": reverse("offers:user_status"),
            })

        clear_pending_qr_session(request)

        return JsonResponse({
            "ok": True,
            "already_claimed_today": False,
            "next": reverse("offers:user_status"),
        })

    # =====================================================
    # NORMAL FLOW: qr_pin => keep pending lock + go PIN modal
    # =====================================================
    request.session["pending_qr_token"] = matched.qr_token.token
    request.session["pending_qr_method"] = "pin"
    request.session["pending_pin_row_id"] = matched.id
    request.session["pending_qr_branch_name"] = matched.branch.name
    request.session["pending_qr_branch_id"] = matched.branch_id
    request.session["pending_qr_desk"] = matched.desk or ""
    request.session["pending_qr_started_at"] = now_ts.isoformat()

    upsert_pending_visit_attempt(
        user=request.user,
        branch=matched.branch,
        qr_token=matched.qr_token,
        yashpin=matched,
        method="pin",
        desk=matched.desk or "",
        state=UserPendingVisitAttempt.STATE_AWAITING_BRANCH,
        note="code entered; awaiting branch verification",
    )

    return JsonResponse({
        "ok": True,
        "already_claimed_today": False,
        "next": reverse("offers:user_visit_pin_page"),
    })


@login_required
@require_POST
@never_cache
@csrf_protect
@cache_control(no_cache=True, no_store=True, must_revalidate=True)
def scan_verify(request):
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        data = {}

    raw_input = str(data.get("token") or "").strip()
    if not raw_input:
        return JsonResponse({"ok": False, "error": "No token provided."}, status=400)

    token = extract_qr_token_from_raw(raw_input)
    if not token:
        return JsonResponse({"ok": False, "error": "Invalid QR token format."}, status=400)

    # verify signed token validity
    try:
        _ = verify_qr_token(token)
    except ValueError as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=400)

    now_ts = timezone.now()

    qt = (
        QRToken.objects
        .select_related("branch")
        .filter(token=token)
        .first()
    )
    if not qt:
        return JsonResponse({"ok": False, "error": "QR not found. Please generate again."}, status=400)

    if qt.expires_at and qt.expires_at <= now_ts:
        return JsonResponse({"ok": False, "error": "QR expired."}, status=400)

    # ✅ NEW: early used check so dead QR does not continue into pending flow
    if qt.used:
        return JsonResponse({"ok": False, "error": "QR already used."}, status=400)

    # quick same-day check (still final confirm does it again)
    if request.user.is_authenticated:
        day_start, next_day_start = get_local_day_bounds(now_ts)
        already = UserVisitEvent.objects.filter(
            user=request.user,
            branch_id=qt.branch_id,
            created_at__gte=day_start,
            created_at__lt=next_day_start,
        ).exists()
        if already:
            return JsonResponse({
                "ok": True,
                "already_claimed_today": True,
                "next": reverse("offers:user_status"),
            })

    # Decide mode from DB (offer.visit_unit)
    vu = get_active_visit_unit(qt.branch_id, now_ts=now_ts)

    # =====================================================
    # QR CODE MODE => Confirm immediately (skip PIN modal)
    # =====================================================
    if vu == "qr_code":
        res = confirm_qr_code_visit(
            user=request.user,
            token=qt.token,
            used_via="scan",
            now_ts=now_ts,
        )
        if not res.ok:
            return JsonResponse({"ok": False, "error": res.error}, status=400)

        # session updates
        clear_pending_qr_session(request)
        set_last_branch_session(
            request,
            branch_id=qt.branch_id,
            branch_name=qt.branch.name,
            token=qt.token,
            desk=qt.desk or "",
        )

        return JsonResponse({
            "ok": True,
            "already_claimed_today": res.already_claimed_today,
            "next": reverse("offers:user_status"),
        })

    # =====================================================
    # QR PIN MODE => Keep existing pending lock flow
    # =====================================================
    request.session["pending_qr_token"] = qt.token
    request.session["pending_qr_method"] = "scan"
    request.session["pending_qr_branch_id"] = qt.branch_id
    request.session["pending_qr_desk"] = qt.desk or ""
    request.session["pending_qr_started_at"] = now_ts.isoformat()
    request.session["pending_qr_branch_name"] = qt.branch.name

    # ✅ store pending attempt in DB
    upsert_pending_visit_attempt(
        user=request.user,
        branch=qt.branch,
        qr_token=qt,
        yashpin=None,
        method="scan",
        desk=qt.desk or "",
        state=UserPendingVisitAttempt.STATE_STARTED,
        note="scan started",
    )

    # optional UI helpers
    request.session["last_branch_id"] = qt.branch_id
    request.session["last_branch_name"] = qt.branch.name
    request.session["last_branch_desk"] = qt.desk or ""

    return JsonResponse({
        "ok": True,
        "already_claimed_today": False,
        "next": reverse("offers:user_visit_pin_page"),
    })


@login_required
@require_POST
@csrf_protect
@never_cache
@cache_control(no_cache=True, no_store=True, must_revalidate=True)
def confirm_branch_visit(request):
    """
    FINAL step:
    - For scan flow: called after screenshot upload success.
    - For pin flow: call this when user confirms (no screenshot needed) OR you can call same endpoint.
    """
    try:
        data = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        data = {}

    now_ts = timezone.now()

    def _mark_pending_failure(state, note="", qr_token=None, branch=None):
        """
        Close matching pending row on terminal failure so stale pending cards don't remain active.
        state: cancelled | expired
        """
        try:
            qs = (
                UserPendingVisitAttempt.objects
                .select_for_update()
                .filter(
                    user=request.user,
                    state__in=[
                        UserPendingVisitAttempt.STATE_STARTED,
                        UserPendingVisitAttempt.STATE_AWAITING_BRANCH,
                    ],
                )
                .order_by("-id")
            )

            # strongest match first
            if qr_token is not None:
                qs = qs.filter(qr_token=qr_token)
            elif token:
                qs = qs.filter(models.Q(qr_token__token=token) | models.Q(token=token))

            if branch is not None:
                qs = qs.filter(branch=branch)
            else:
                branch_id_hint = request.session.get("pending_qr_branch_id") or request.session.get("last_branch_id")
                if branch_id_hint:
                    qs = qs.filter(branch_id=branch_id_hint)

            pending = qs.first()
            if not pending:
                return

            pending.state = state
            update_fields = ["state"]

            field_names = {f.name for f in pending._meta.fields}

            if state == UserPendingVisitAttempt.STATE_CANCELLED and "cancelled_at" in field_names:
                pending.cancelled_at = now_ts
                update_fields.append("cancelled_at")

            if state == UserPendingVisitAttempt.STATE_EXPIRED and "expired_at" in field_names:
                pending.expired_at = now_ts
                update_fields.append("expired_at")

            if note and "note" in field_names:
                pending.note = note
                update_fields.append("note")

            if "updated_at" in field_names:
                pending.updated_at = now_ts
                update_fields.append("updated_at")

            pending.save(update_fields=update_fields)
        except Exception:
            # never let cleanup failure hide the real response
            pass

    token = (data.get("token") or "").strip() or request.session.get("pending_qr_token")
    if not token:
        _mark_pending_failure(
            UserPendingVisitAttempt.STATE_CANCELLED,
            note="confirm_branch_visit: no pending token",
        )
        return JsonResponse({"ok": False, "error": "No pending QR. Please scan again."}, status=400)

    # hard session match
    if token != request.session.get("pending_qr_token"):
        _mark_pending_failure(
            UserPendingVisitAttempt.STATE_CANCELLED,
            note="confirm_branch_visit: token/session mismatch",
        )
        return JsonResponse({"ok": False, "error": "Session mismatch. Please scan again."}, status=400)

    pending_method = request.session.get("pending_qr_method") or "scan"
    pending_pin_row_id = request.session.get("pending_pin_row_id")  # only for pin-flow

    with transaction.atomic():
        qt = (
            QRToken.objects
            .select_for_update()
            .select_related("branch")
            .filter(token=token)
            .first()
        )
        if not qt:
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_EXPIRED,
                note="confirm_branch_visit: qr token not found",
            )
            return JsonResponse({"ok": False, "error": "QR not found. Please scan again."}, status=400)

        if qt.expires_at <= now_ts:
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_EXPIRED,
                note="confirm_branch_visit: qr expired",
                qr_token=qt,
                branch=qt.branch,
            )
            return JsonResponse({"ok": False, "error": "QR expired. Please scan again."}, status=400)

        if qt.used:
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_EXPIRED,
                note="confirm_branch_visit: qr already used",
                qr_token=qt,
                branch=qt.branch,
            )
            return JsonResponse({"ok": False, "error": "QR already used."}, status=400)

        # final one-per-day enforcement
        day_start, next_day_start = get_local_day_bounds(now_ts)
        already = UserVisitEvent.objects.filter(
            user=request.user,
            branch=qt.branch,
            created_at__gte=day_start,
            created_at__lt=next_day_start,
        ).exists()
        if already:
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_CANCELLED,
                note="confirm_branch_visit: already counted today",
                qr_token=qt,
                branch=qt.branch,
            )
            clear_pending_qr_session(request)
            return JsonResponse({
                "ok": True,
                "already_claimed_today": True,
                "redirect_url": reverse("offers:user_visit_pin_page"),
            })

        staff_name = (qt.staff_name or "").strip() or qt.branch.name
        staff_code = (qt.staff_code or "").strip()
        desk = qt.desk or ""
        # If PIN flow → burn YashPin also, and take staff/desk from pin row
        if pending_method == "pin":
            if not pending_pin_row_id:
                _mark_pending_failure(
                    UserPendingVisitAttempt.STATE_CANCELLED,
                    note="confirm_branch_visit: missing pin session row id",
                    qr_token=qt,
                    branch=qt.branch,
                )
                clear_pending_qr_session(request)
                return JsonResponse({"ok": False, "error": "PIN session expired. Please re-enter PIN."}, status=400)

            pin_row = (
                YashPin.objects
                .select_for_update()
                .select_related("branch")
                .filter(pk=pending_pin_row_id)
                .first()
            )
            if not pin_row:
                _mark_pending_failure(
                    UserPendingVisitAttempt.STATE_CANCELLED,
                    note="confirm_branch_visit: pin row missing",
                    qr_token=qt,
                    branch=qt.branch,
                )
                clear_pending_qr_session(request)
                return JsonResponse({"ok": False, "error": "PIN session expired. Please re-enter PIN."}, status=400)

            # safety: same token + not expired + not used
            if pin_row.used or pin_row.expires_at < now_ts:
                _mark_pending_failure(
                    UserPendingVisitAttempt.STATE_EXPIRED,
                    note="confirm_branch_visit: pin expired or already used",
                    qr_token=qt,
                    branch=qt.branch,
                )
                clear_pending_qr_session(request)
                return JsonResponse({"ok": False, "error": "PIN expired. Please re-enter PIN."}, status=400)

            if pin_row.qr_token_id != qt.id:
                _mark_pending_failure(
                    UserPendingVisitAttempt.STATE_CANCELLED,
                    note="confirm_branch_visit: pin/qr mismatch",
                    qr_token=qt,
                    branch=qt.branch,
                )
                clear_pending_qr_session(request)
                return JsonResponse({"ok": False, "error": "PIN mismatch. Please re-enter PIN."}, status=400)

            # burn pin
            pin_row.used = True
            pin_row.used_at = now_ts
            pin_row.save(update_fields=["used", "used_at"])

            # prefer staff/desk from pin row
            staff_name = pin_row.staff_name or staff_name
            staff_code = pin_row.staff_code or staff_code
            desk = pin_row.desk or desk

        # burn QRToken
        qt.used = True
        qt.used_at = now_ts
        qt.used_via = "pin" if pending_method == "pin" else "scan"
        qt.used_by = request.user
        qt.save(update_fields=["used", "used_at", "used_via", "used_by"])

        # create visit 
        ve = UserVisitEvent.objects.create(
            user=request.user,
            branch=qt.branch,
            token=qt.token,
            desk=desk,
            visit_method="qr_pin" if pending_method == "pin" else "qr_code",    
            staff_name=staff_name,
            staff_code=staff_code,
        )

        # NEW: auto-issue claim if milestone reached
        claim_result = issue_offer_claim_if_eligible(
            user=request.user,
            branch_id=qt.branch_id,
            visit_event=ve,
            now_ts=now_ts,
            token=qt.token or "",
            desk=desk or "",
            staff_name=staff_name,
            staff_code=staff_code,
        )

    # confirmed session for status page
    set_last_branch_session(
        request,
        branch_id=qt.branch_id,
        branch_name=qt.branch.name,
        token=qt.token,
        desk=desk,
        confirmed_at=now_ts,
    )

    # success -> complete pending row
    mark_pending_visit_attempt_completed(
        user=request.user,
        qr_token=qt,
        completed_at=now_ts,
        note="completed from confirm_branch_visit",
    )

    # clear pending session locks
    clear_pending_qr_session(request)

    return JsonResponse({
        "ok": True,
        "already_claimed_today": False,
        "redirect_url": reverse("offers:user_visit_pin_page"),
        "claim_issued": bool(claim_result.get("claim_issued")),
        "claim_ids": list(claim_result.get("claim_ids") or []),
    })

# ============================================
# branch offers  view in user interface
# =============================================


def offer_progress(request, branch_id):
    branch = get_object_or_404(Branch, id=branch_id)

    # force context for pin page / eligibility
    request.session["last_branch_id"] = branch.id
    request.session["last_branch_name"] = branch.name

    now_ts = timezone.now()
    day_start, next_day_start = get_local_day_bounds(now_ts)

    base_qs = (
        ComplementaryOffer.objects
        .filter(
            is_active=True,
            start_at__lte=now_ts,
        )
        .filter(
            models.Q(end_at__isnull=True) | models.Q(end_at__gte=now_ts)
        )
        .filter(
            models.Q(all_branches=True) | models.Q(eligible_branches=branch)
        )
        .distinct()
    )

    active_offer_count = base_qs.count()

    free_plate_offer = (
        base_qs
        .filter(kind="complementary_offer")
        .order_by("-start_at", "-id")
        .first()
    )

    # This branch visit stats (only this branch)
    branch_total_visits = 0
    branch_today_visits = 0
    branch_last_visit = None
    branch_has_visited = False
    claimed_offer_count = 0

    if request.user.is_authenticated:
        vqs = UserVisitEvent.objects.filter(user=request.user, branch=branch)
        branch_total_visits = vqs.count()
        branch_today_visits = vqs.filter(
            created_at__gte=day_start,
            created_at__lt=next_day_start,
        ).count()
        branch_last_visit = vqs.aggregate(last=Max("created_at"))["last"]
        branch_has_visited = branch_total_visits > 0

        claimed_offer_count = UserOfferClaim.objects.filter(
            user=request.user,
            branch=branch,
        ).count()

    context = {
        "branch": branch,
        "active_offer_count": active_offer_count,
        "claimed_offer_count": claimed_offer_count,
        "is_open_now": True,
        "free_plate_offer": free_plate_offer,
        "branch_total_visits": branch_total_visits,
        "branch_today_visits": branch_today_visits,
        "branch_last_visit": branch_last_visit,
        "branch_has_visited": branch_has_visited,

        # hero defaults
        "current_progress": branch_total_visits,
        "progress_total": None,
        "next_reward_title": "Next Reward",
        "next_reward_subtitle": "Next treat",
    }

    # Progress / calendar logic
    max_preview = 60
    if free_plate_offer and free_plate_offer.start_at and free_plate_offer.end_at:
        window_days = (free_plate_offer.end_at.date() - free_plate_offer.start_at.date()).days + 1
        max_preview = max(15, min(60, window_days))

        progress = progress_helper.offers_progress_modal_context(
            total_visits=branch_total_visits,
            nth=getattr(free_plate_offer, "nth", None),
            repeat=bool(getattr(free_plate_offer, "repeat", True)),
            extra_nths=list(getattr(free_plate_offer, "extra_nths", []) or []),
            max_preview=max_preview,
            include_repeat_multiples=True,
        )
        context.update(progress)

        rows = list(progress.get("rows") or [])
        active_row = next((r for r in rows if r.get("state") == "active"), None)
        next_lock_row = next((r for r in rows if r.get("state") == "lock"), None)
        next_row = active_row or next_lock_row

        if next_row:
            context["next_reward_title"] = next_row.get("label") or "Next Reward"
            context["next_reward_subtitle"] = next_row.get("title") or "Next treat"

        context["current_progress"] = progress.get("current_progress", branch_total_visits)
        context["progress_total"] = progress.get("progress_total")

    return render(
        request,
        "user_interface/offer_progress/offer_progress.html",
        context,
    )


# =========================
# Visit count page after sucefull pin or scan redirect view 
# =========================



@cache_control(no_store=True, no_cache=True, must_revalidate=True)
@never_cache
def user_visit_intake_redirect_view(request):
    token = request.GET.get("token")
    if not token:
        return redirect("offers:user_visit_pin_page")

    try:
        # verify token format (signed token check)
        if "." in token:
            info = verify_qr_token(token)
        elif ":" in token:
            info = verify_legacy_colon_token(token)
        else:
            raise ValueError("Bad token format")

        branch = (
            Branch.objects
            .filter(pk=info["bid"])
            .only("id", "name")
            .first()
        )
        if not branch:
            raise ValueError("Branch not found")

        desk = info.get("desk")

        # ✅ ONLY PENDING context (NOT confirmed)
        request.session["pending_qr_branch_id"] = branch.id
        request.session["pending_qr_desk"] = str(desk or "")
        request.session["pending_qr_started_at"] = timezone.now().isoformat()
        request.session["pending_qr_token"] = token  # keep token

        # show same page/modal again (user will confirm next)
        return redirect("offers:user_visit_pin_page")

    except ValueError:
        return redirect("offers:user_home")


@cache_control(no_store=True, no_cache=True, must_revalidate=True)
@never_cache
def user_visit_pin_page_view(request):
    # ✅ Allow both confirmed + pending branch context
    branch_id = request.session.get("last_branch_id") or request.session.get("pending_qr_branch_id")
    if not branch_id:
        return redirect("offers:user_home")

    branch_name = (
        request.session.get("last_branch_name")
        or request.session.get("pending_qr_branch_name")
        or "Unknown Branch"
    )

    # ✅ Pending indicator (scan/pin start?)
    pending_token = (request.session.get("pending_qr_token") or "").strip()
    pending_started = bool(pending_token)

    # ✅ Core offer+eligibility context (single source of truth)
    offer_ctx = build_offer_eligibility_context(
        user=request.user,
        branch_id=branch_id,
        pending_started=pending_started,
    )

    ctx = {
        "branch_name": branch_name,
        "token": request.session.get("last_visit_token") or pending_token,
        "pending_started": pending_started,
        **offer_ctx,
    }

    return render(
        request,
        "user_interface/user_visit_count/user_visit_pin_verify_modal.html",
        ctx,
    )




def _parse_iso_dt(v):
    """
    Safe ISO parse for session stored datetime string.
    Returns aware datetime or None.
    """
    if not v:
        return None
    try:
        dt = timezone.datetime.fromisoformat(v)
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt
    except Exception:
        return None


def user_status_view(request):
    branch_id = request.session.get("last_branch_id")
    branch_name = request.session.get("last_branch_name") or "All"

    # defaults
    this_branch_total = 0
    this_branch_today = 0
    this_branch_last = None

    today_total_all = 0
    today_unique_branches = 0
    per_branch_today = []

    total_all = 0
    last_visit_anywhere = "—"

    pending_items = []
    history_days = []

    # offer claim defaults
    offers_claimed_total = 0
    offers_claimed_today = 0
    offers_claimed_label = "Total claimed offers"

    # local day start
    now_ts = timezone.now()
    day_start, next_day_start = get_local_day_bounds(now_ts)

    method_label_map = {
        "qr_pin": "QR scan + PIN at outlet",
        "qr_code": "QR code",
        "offer_day_pin": "Offer Day PIN",
        "qr_screenshot": "QR Screenshot Scan",
    }

    # visit stats + history
    if request.user.is_authenticated:
        base_all = UserVisitEvent.objects.filter(user=request.user)
        total_all = base_all.count()

        # today across all branches
        base_today = base_all.filter(
            created_at__gte=day_start,
            created_at__lt=next_day_start,
        )
        today_total_all = base_today.count()
        today_unique_branches = base_today.values("branch_id").distinct().count()

        # per-branch today breakdown
        per_branch_today = list(
            base_today
            .values("branch_id", "branch__name")
            .annotate(today_visits=Count("id"), last_visit=Max("created_at"))
            .order_by("-last_visit")
        )

        # this branch stats
        if branch_id:
            qs = base_all.filter(branch_id=branch_id)
            this_branch_total = qs.count()
            this_branch_today = qs.filter(
                created_at__gte=day_start,
                created_at__lt=next_day_start,
            ).count()
            last_obj = qs.order_by("-created_at").first()
            this_branch_last = last_obj.created_at if last_obj else None

        # last visit anywhere
        last_any = base_all.order_by("-created_at").first()
        if last_any:
            last_visit_anywhere = timezone.localtime(last_any.created_at).strftime("%d %b %Y, %I:%M %p")

        # real offer claim stats
        claim_qs = (
            UserOfferClaim.objects
            .filter(user=request.user)
            .exclude(status="cancelled")
        )
        offers_claimed_total = claim_qs.count()
        offers_claimed_today = claim_qs.filter(
            issued_at__gte=day_start,
            issued_at__lt=next_day_start,
        ).count()

        # history timeline
        events = (
            base_all
            .select_related("branch")
            .order_by("-created_at")[:120]
        )

        buckets = {}
        for e in events:
            d = timezone.localdate(e.created_at)
            buckets.setdefault(d, []).append(e)

        for d in sorted(buckets.keys(), reverse=True):
            items = []
            for e in buckets[d]:
                method_raw = (e.visit_method or "").strip()
                items.append({
                    "created_at": timezone.localtime(e.created_at),
                    "branch_id": e.branch_id,
                    "branch_name": getattr(e.branch, "name", "Branch"),
                    "desk": e.desk or "",
                    "visit_method": method_raw,
                    "visit_method_label": method_label_map.get(method_raw) or (method_raw or "—"),
                    "staff_name": e.staff_name or "",
                    "staff_code": e.staff_code or "",
                    "state": "done",
                })
            history_days.append({
                "date": d,
                "count": len(items),
                "items": items,
            })

        # pending status (from DB)
        pending_rows = get_user_active_pending_attempts(user=request.user)

        for row in pending_rows:
            pending_items.append({
                "branch_id": row.branch_id,
                "branch_name": getattr(row.branch, "name", "Branch"),
                "desk": row.desk or "",
                "method": row.method,
                "method_label": "QR + PIN" if row.method == "pin" else "QR Scan",
                "started_at": row.started_at,
                "state": row.state,
                "state_label": dict(UserPendingVisitAttempt.STATE_CHOICES).get(row.state, row.state),
                "note": getattr(row, "note", "") or "",
            })

    # active visit_unit
    visit_unit = get_active_visit_unit(branch_id) if branch_id else "qr_pin"

    ctx = {
        "branch_name": branch_name,
        "total_visits": this_branch_total,
        "today_visits": this_branch_today,
        "last_visit": timezone.localtime(this_branch_last).strftime("%Y-%m-%d %H:%M") if this_branch_last else "—",
        "visit_unit": visit_unit,
        "total_all": total_all,

        "today_total_all": today_total_all,
        "today_unique_branches": today_unique_branches,
        "per_branch_today": per_branch_today,

        "last_visit_anywhere": last_visit_anywhere,
        "pending_items": pending_items,
        "history_days": history_days,

        "offers_claimed_total": offers_claimed_total,
        "offers_claimed_today": offers_claimed_today,
        "offers_claimed_label": offers_claimed_label,
    }

    return render(
        request,
        "user_interface/user_status_view/user_status.html",
        ctx,
    )

# from .models import BranchGenerateVisitPin, UserVerifyVisitPin, UserVisitEvent


# offers/user_views.py


# models imports (make sure these are present)
# from .models import BranchGenerateVisitPin, UserVisitEvent, UserVerifyVisitPin, QRToken, YashPin


@require_POST
@csrf_protect
@never_cache
@cache_control(no_cache=True, no_store=True, must_revalidate=True)
def user_verify_visit_pin(request):
    """
    USER enters STAFF-GENERATED VISIT PIN (BranchGenerateVisitPin)

    ✅ ONE PLACE tracking:
      1) verify staff visit PIN (BranchGenerateVisitPin)
      2) confirm pending QR (QRToken) which user came from (scan/pin flow)
      3) if qr-pin flow -> also burn YashPin
      4) create UserVisitEvent (ONLY once)
      5) create UserVerifyVisitPin audit row (admin)
      6) mark QRToken.used / used_via / used_by
      7) clear pending session locks
      8) auto-issue claim if milestone reached
    """

    # -------------------------
    # 0) read input
    # -------------------------
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        payload = {}

    pin = str(payload.get("pin", "")).strip()
    if not (pin.isdigit() and len(pin) == 4):
        return JsonResponse({"ok": False, "error": "Enter a valid 4-digit PIN."}, status=400)

    now_ts = timezone.now()

    def _mark_pending_failure(state, note="", qr_token=None, branch=None):
        """
        Close matching pending row on terminal failure so stale pending rows do not remain active.
        state: cancelled | expired
        """
        try:
            qs = (
                UserPendingVisitAttempt.objects
                .select_for_update()
                .filter(
                    user=request.user,
                    state__in=[
                        UserPendingVisitAttempt.STATE_STARTED,
                        UserPendingVisitAttempt.STATE_AWAITING_BRANCH,
                    ],
                )
                .order_by("-id")
            )

            if qr_token is not None:
                qs = qs.filter(qr_token=qr_token)
            else:
                token_hint = (request.session.get("pending_qr_token") or "").strip()
                if token_hint:
                    try:
                        qs = qs.filter(models.Q(qr_token__token=token_hint) | models.Q(token=token_hint))
                    except Exception:
                        qs = qs.filter(qr_token__token=token_hint)

            if branch is not None:
                qs = qs.filter(branch=branch)
            else:
                branch_id_hint = request.session.get("pending_qr_branch_id") or request.session.get("last_branch_id")
                if branch_id_hint:
                    qs = qs.filter(branch_id=branch_id_hint)

            pending = qs.first()
            if not pending:
                return

            pending.state = state
            update_fields = ["state"]

            field_names = {f.name for f in pending._meta.fields}

            if state == UserPendingVisitAttempt.STATE_CANCELLED and "cancelled_at" in field_names:
                pending.cancelled_at = now_ts
                update_fields.append("cancelled_at")

            if state == UserPendingVisitAttempt.STATE_EXPIRED and "expired_at" in field_names:
                pending.expired_at = now_ts
                update_fields.append("expired_at")

            if note and "note" in field_names:
                pending.note = note
                update_fields.append("note")

            if "updated_at" in field_names:
                pending.updated_at = now_ts
                update_fields.append("updated_at")

            pending.save(update_fields=update_fields)
        except Exception:
            pass

    # -------------------------
    # 1) MUST have pending QR context (scan_verify / pin_verify set these)
    # -------------------------
    token = (request.session.get("pending_qr_token") or "").strip()
    if not token:
        _mark_pending_failure(
            UserPendingVisitAttempt.STATE_CANCELLED,
            note="user_verify_visit_pin: no pending qr token",
        )
        return JsonResponse(
            {"ok": False, "error": "No pending QR found. Please scan again."},
            status=400,
        )

    pending_method = request.session.get("pending_qr_method") or "scan"  # "scan" | "pin"
    pending_pin_row_id = request.session.get("pending_pin_row_id")       # only for qr-pin flow

    # ✅ staff visit pin MUST be verified for same branch user came from
    branch_id = request.session.get("pending_qr_branch_id") or request.session.get("last_branch_id")
    if not branch_id:
        _mark_pending_failure(
            UserPendingVisitAttempt.STATE_CANCELLED,
            note="user_verify_visit_pin: branch context missing",
        )
        clear_pending_qr_session(request)
        return JsonResponse({"ok": False, "error": "Branch context missing. Please scan QR again."}, status=400)

    # -------------------------
    # 2) mark expired visit pins globally (optional)
    # -------------------------
    BranchGenerateVisitPin.objects.filter(
        expired=False,
        expires_at__lte=now_ts,
    ).update(expired=True, expired_at=now_ts)

    # -------------------------
    # 3) find matching BranchGenerateVisitPin row (branch-scoped!)
    # -------------------------
    qs = (
        BranchGenerateVisitPin.objects
        .select_related("branch")
        .filter(branch_id=branch_id, used=False, expired=False, expires_at__gt=now_ts)
        .order_by("-created_at")
    )

    candidates = list(qs[:120])  # small recent window
    matched_visit_pin = None
    for row in candidates:
        if check_password(pin, row.pin_hash):
            matched_visit_pin = row
            break

    if not matched_visit_pin:
        return JsonResponse({"ok": False, "error": "Invalid or expired visit PIN."}, status=400)

    # -------------------------
    # 4) ATOMIC: lock & update everything consistently
    # -------------------------
    with transaction.atomic():
        now_ts = timezone.now()

        # 4A) lock visit pin row
        matched_visit_pin = (
            BranchGenerateVisitPin.objects
            .select_for_update()
            .select_related("branch")
            .get(pk=matched_visit_pin.pk)
        )

        if matched_visit_pin.used:
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_EXPIRED,
                note="user_verify_visit_pin: staff visit pin already used",
                branch=matched_visit_pin.branch,
            )
            clear_pending_qr_session(request)
            return JsonResponse({"ok": False, "error": "PIN already used."}, status=409)

        if matched_visit_pin.expired or matched_visit_pin.expires_at <= now_ts:
            matched_visit_pin.expired = True
            matched_visit_pin.expired_at = now_ts
            matched_visit_pin.save(update_fields=["expired", "expired_at"])
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_EXPIRED,
                note="user_verify_visit_pin: staff visit pin expired",
                branch=matched_visit_pin.branch,
            )
            clear_pending_qr_session(request)
            return JsonResponse({"ok": False, "error": "PIN expired."}, status=410)

        # 4B) lock QR token (pending token)
        qt = (
            QRToken.objects
            .select_for_update()
            .select_related("branch")
            .filter(token=token)
            .first()
        )
        if not qt:
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_EXPIRED,
                note="user_verify_visit_pin: qr token not found",
                branch=matched_visit_pin.branch,
            )
            clear_pending_qr_session(request)
            return JsonResponse({"ok": False, "error": "QR not found. Please scan again."}, status=400)

        if qt.expires_at <= now_ts:
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_EXPIRED,
                note="user_verify_visit_pin: qr expired",
                qr_token=qt,
                branch=qt.branch,
            )
            clear_pending_qr_session(request)
            return JsonResponse({"ok": False, "error": "QR expired. Please scan again."}, status=400)

        if qt.used:
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_EXPIRED,
                note="user_verify_visit_pin: qr already used",
                qr_token=qt,
                branch=qt.branch,
            )
            clear_pending_qr_session(request)
            return JsonResponse({"ok": False, "error": "QR already used. Please generate again."}, status=400)

        # ✅ STRICT: QR branch and VisitPin branch must match
        if int(qt.branch_id) != int(matched_visit_pin.branch_id):
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_CANCELLED,
                note="user_verify_visit_pin: branch mismatch between qr and visit pin",
                qr_token=qt,
                branch=qt.branch,
            )
            clear_pending_qr_session(request)
            return JsonResponse(
                {"ok": False, "error": "Branch mismatch. Please scan correct branch QR and try again."},
                status=400,
            )

        # 4C) final one-per-day enforcement (per-branch)
        day_start, next_day_start = get_local_day_bounds(now_ts)
        already = UserVisitEvent.objects.filter(
            user=request.user,
            branch=qt.branch,
            created_at__gte=day_start,
            created_at__lt=next_day_start,
        ).exists()
        if already:
            _mark_pending_failure(
                UserPendingVisitAttempt.STATE_CANCELLED,
                note="user_verify_visit_pin: already counted today",
                qr_token=qt,
                branch=qt.branch,
            )
            clear_pending_qr_session(request)
            return JsonResponse({
                "ok": True,
                "already_claimed_today": True,
                "redirect_url": reverse("offers:user_status"),
            })

        # 4D) If user came via qr-pin flow → burn YashPin also
        staff_name = (qt.staff_name or "").strip() or qt.branch.name
        staff_code = (qt.staff_code or "").strip()
        desk = qt.desk or ""

        if pending_method == "pin":
            # must have row id
            if not pending_pin_row_id:
                _mark_pending_failure(
                    UserPendingVisitAttempt.STATE_CANCELLED,
                    note="user_verify_visit_pin: qr pin session missing",
                    qr_token=qt,
                    branch=qt.branch,
                )
                clear_pending_qr_session(request)
                return JsonResponse({"ok": False, "error": "PIN session missing. Please re-enter QR PIN."}, status=400)

            pin_row = (
                YashPin.objects
                .select_for_update()
                .select_related("branch", "qr_token")
                .filter(pk=pending_pin_row_id)
                .first()
            )
            if not pin_row:
                _mark_pending_failure(
                    UserPendingVisitAttempt.STATE_CANCELLED,
                    note="user_verify_visit_pin: qr pin row missing",
                    qr_token=qt,
                    branch=qt.branch,
                )
                clear_pending_qr_session(request)
                return JsonResponse({"ok": False, "error": "QR PIN session expired. Please re-enter."}, status=400)

            if pin_row.used or pin_row.expires_at <= now_ts:
                _mark_pending_failure(
                    UserPendingVisitAttempt.STATE_EXPIRED,
                    note="user_verify_visit_pin: qr pin expired or already used",
                    qr_token=qt,
                    branch=qt.branch,
                )
                clear_pending_qr_session(request)
                return JsonResponse({"ok": False, "error": "QR PIN expired. Please re-enter."}, status=400)

            if pin_row.qr_token_id != qt.id:
                _mark_pending_failure(
                    UserPendingVisitAttempt.STATE_CANCELLED,
                    note="user_verify_visit_pin: qr pin mismatch",
                    qr_token=qt,
                    branch=qt.branch,
                )
                clear_pending_qr_session(request)
                return JsonResponse({"ok": False, "error": "QR PIN mismatch. Please re-enter."}, status=400)

            # burn qr-pin row
            pin_row.used = True
            pin_row.used_at = now_ts
            pin_row.used_by = request.user
            pin_row.save(update_fields=["used", "used_at", "used_by"])

            # prefer staff/desk from qr-pin row (if set)
            staff_name = (pin_row.staff_name or "").strip() or staff_name or qt.branch.name
            staff_code = (pin_row.staff_code or "").strip() or staff_code
            desk = pin_row.desk or desk

        # 4E) burn QRToken now
        qt.used = True
        qt.used_at = now_ts
        qt.used_by = request.user
        qt.used_via = "pin" if pending_method == "pin" else "scan"
        qt.save(update_fields=["used", "used_at", "used_by", "used_via"])

        # 4F) burn STAFF visit pin (BranchGenerateVisitPin)
        matched_visit_pin.used = True
        matched_visit_pin.used_at = now_ts
        matched_visit_pin.save(update_fields=["used", "used_at"])

        # choose desk/staff snapshots (prefer VisitPin snapshots if present)
        final_desk = (matched_visit_pin.desk or desk or "")
        final_staff_name = ((getattr(matched_visit_pin, "staff_name", "") or "").strip() or staff_name or qt.branch.name)
        final_staff_code = (getattr(matched_visit_pin, "staff_code", "") or "").strip() or staff_code

        # 4G) create audit row (admin table)
        UserVerifyVisitPin.objects.create(
            branch=matched_visit_pin.branch,
            desk=final_desk,
            token=qt.token,
            pin_hash=matched_visit_pin.pin_hash,
            expires_at=matched_visit_pin.expires_at,
            used=True,
            expired=False,
            used_by=request.user if request.user.is_authenticated else None,
            used_at=now_ts,
            staff_name=final_staff_name,
            staff_code=final_staff_code,
        )

        # 4H) create visit event (ONLY ONCE)
        ve = UserVisitEvent.objects.create(
            user=request.user,
            branch=qt.branch,
            token=qt.token,
            desk=final_desk,
            visit_method="qr_pin" if pending_method == "pin" else "qr_code",
            staff_name=final_staff_name,
            staff_code=final_staff_code,
        )

        # NEW: auto-issue claim if milestone reached
        claim_result = issue_offer_claim_if_eligible(
            user=request.user,
            branch_id=qt.branch_id,
            visit_event=ve,
            now_ts=now_ts,
            token=qt.token or "",
            desk=final_desk or "",
            staff_name=final_staff_name,
            staff_code=final_staff_code,
        )

    # -------------------------
    # 5) session update + clear pending locks
    # -------------------------
    set_last_branch_session(
        request,
        branch_id=qt.branch_id,
        branch_name=qt.branch.name,
        token=qt.token,
        desk=final_desk,
        confirmed_at=now_ts,
    )

    mark_pending_visit_attempt_completed(
        user=request.user,
        qr_token=qt,
        completed_at=now_ts,
        note="completed from user_verify_visit_pin",
    )

    clear_pending_qr_session(request)

    return JsonResponse({
        "ok": True,
        "message": "Visit verified successfully ✅",
        "branch_name": qt.branch.name,
        "redirect_url": reverse("offers:user_status"),
        "claim_issued": bool(claim_result.get("claim_issued")),
        "claim_ids": list(claim_result.get("claim_ids") or []),
    })


@never_cache
@require_GET
def user_branch_search_suggestions(request):
    q = (request.GET.get("q") or "").strip()

    if len(q) < 1:
        return JsonResponse({
            "ok": True,
            "suggestions": [],
        })

    suggestions = []
    seen = set()

    # 1) FIRST priority: city / location_title suggestions only
    location_rows = (
        Branch.objects
        .filter(location_title__icontains=q)
        .exclude(location_title="")
        .order_by(Lower("location_title"))
        .values("location_title")
        .distinct()[:8]
    )

    for row in location_rows:
        location_title = (row.get("location_title") or "").strip()
        if not location_title:
            continue

        key = location_title.lower()
        if key in seen:
            continue

        seen.add(key)
        suggestions.append({
            "type": "location",
            "label": location_title,
            "value": location_title,
            "location": "",
        })

    # If city/location matched, stop here.
    # City search ki branch titles dropdown lo chupinchakudadhu.
    if suggestions:
        return JsonResponse({
            "ok": True,
            "suggestions": suggestions,
        })

    # 2) SECOND priority: subtitle / landmark / area suggestions
    subtitle_rows = (
        Branch.objects
        .filter(location_subtitle__icontains=q)
        .exclude(location_subtitle="")
        .order_by(Lower("location_title"), Lower("location_subtitle"))
        .values("location_title", "location_subtitle")
        .distinct()[:8]
    )

    for row in subtitle_rows:
        location_title = (row.get("location_title") or "").strip()
        location_subtitle = (row.get("location_subtitle") or "").strip()

        label = location_title or location_subtitle
        extra = location_subtitle if location_title else ""

        if not label:
            continue

        key = (label + "|" + extra).lower()
        if key in seen:
            continue

        seen.add(key)
        suggestions.append({
            "type": "location",
            "label": label,
            "value": label,
            "location": extra,
        })

    if suggestions:
        return JsonResponse({
            "ok": True,
            "suggestions": suggestions,
        })

    # 3) LAST priority: branch name/title suggestions
    branches = (
        Branch.objects
        .filter(
            Q(name__icontains=q) |
            Q(display_title__icontains=q)
        )
        .annotate(
            match_rank=Case(
                When(display_title__istartswith=q, then=Value(0)),
                When(name__istartswith=q, then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        )
        .order_by("match_rank", Lower("name"))
        .values("id", "name", "display_title", "location_title")[:8]
    )

    for branch in branches:
        label = (branch.get("display_title") or branch.get("name") or "").strip()
        value = label
        location_title = branch.get("location_title") or ""

        if not label:
            continue

        key = label.lower()
        if key in seen:
            continue

        seen.add(key)
        suggestions.append({
            "type": "branch",
            "label": label,
            "value": value,
            "location": location_title,
        })

    return JsonResponse({
        "ok": True,
        "suggestions": suggestions,
    })