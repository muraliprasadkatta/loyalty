# offers/qr_generation and pin/views.py

import hashlib
from datetime import timedelta
from random import choice

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.urls import reverse
from django.shortcuts import redirect
from django.views.decorators.http import require_GET
from django.views.decorators.cache import never_cache, cache_control
from django.db import transaction
from django.utils import timezone
from django.contrib.auth.hashers import make_password

from offers.models import Branch, QRToken, YashPin, BranchStaff
from offers.services.qr.qr_token_utils import mint_qr_token, parse_qr_token


# ========= code helpers =========

CODE_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
CODE_LEN = 4


def _gen_qr_fallback_code() -> str:
    return "".join(choice(CODE_CHARS) for _ in range(CODE_LEN))


# ========= low-level helpers =========

def _short_tag(branch: Branch) -> str:
    """
    Stable 6-char tag for UI display.
    Uses branch.public_id or id or name.
    """
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

    src = (
        getattr(branch, "public_id", "")
        or str(branch.id)
        or branch.name
    ).encode("utf-8")

    h = hashlib.sha256(src).digest()
    n = int.from_bytes(h[:4], "big")

    out = []
    for _ in range(6):
        out.append(alphabet[n % len(alphabet)])
        n //= len(alphabet)

    return "".join(out)


def _abs(request, path: str) -> str:
    return request.build_absolute_uri(path)


def _branch_param_matches_session_branch(branch: Branch, branch_param: str) -> bool:
    """
    QR modal may send branch public_id/id/name.
    But backend must trust session branch as source of truth.
    """
    branch_param = (branch_param or "").strip()

    if not branch_param:
        return True

    allowed_values = {
        str(branch.id),
        (branch.name or "").lower(),
        (getattr(branch, "public_id", "") or "").lower(),
    }

    return branch_param.lower() in allowed_values


# ========= DB save helper =========

def QRTokenYashPindataSave(
    *,
    branch,
    desk,
    token,
    pin_hash,
    expires_at,
    staff_name="",
    staff_code="",
):
    """
    Single place DB save for QR + PIN.
    Staff snapshot is important for deactivate-time cleanup.
    """

    qt = QRToken.objects.create(
        branch=branch,
        desk=desk,
        token=token,
        expires_at=expires_at,
        used=False,
        staff_name=staff_name,
        staff_code=staff_code,
    )

    YashPin.objects.create(
        branch=branch,
        desk=desk,
        qr_token=qt,
        pin_hash=pin_hash,
        expires_at=expires_at,
        used=False,
        staff_name=staff_name,
        staff_code=staff_code,
    )

    return qt


# ========= views =========

@require_GET
@never_cache
@cache_control(no_cache=True, no_store=True, must_revalidate=True)
@transaction.atomic
def start_counter_qr(request):
    """
    Branch/staff-side QR generation endpoint.

    Important:
    - Requires branch session.
    - If staff session exists, staff must still be active.
    - QR/YashPin store staff snapshot for future deactivate cleanup.
    """

    # Branch auth required.
    session_branch_id = request.session.get("branch_id")

    if not session_branch_id:
        return JsonResponse(
            {"ok": False, "error": "Branch auth required."},
            status=401,
        )

    branch = (
        Branch.objects
        .filter(pk=session_branch_id)
        .only("id", "name", "public_id")
        .first()
    )

    if not branch:
        return JsonResponse(
            {"ok": False, "error": "Branch session invalid."},
            status=401,
        )

    # Do not allow generating QR for another branch using URL param.
    branch_param = (request.GET.get("branch") or "").strip()

    if not _branch_param_matches_session_branch(branch, branch_param):
        return JsonResponse(
            {"ok": False, "error": "Branch mismatch."},
            status=403,
        )

    # Staff session safety check.
    staff_id = request.session.get("branch_staff_id")
    staff_name = request.session.get("branch_staff_name") or ""
    staff_code = request.session.get("branch_staff_code") or ""

    if staff_id:
        staff = (
            BranchStaff.objects
            .filter(
                id=staff_id,
                branch=branch,
                is_active=True,
            )
            .only("id", "name", "staff_id")
            .first()
        )

        if not staff:
            return JsonResponse(
                {"ok": False, "error": "This staff account is inactive."},
                status=403,
            )

        # Session values are source for UI, DB fallback for safety.
        staff_name = staff_name or staff.name or ""
        staff_code = staff_code or staff.staff_id or ""

    desk = (request.GET.get("desk") or "A1")[:12]

    expires_in = int(getattr(settings, "QR_TTL_SECS", 180))
    expires_at = timezone.now() + timedelta(seconds=expires_in)

    # Mint signed token.
    token = mint_qr_token(branch.id, desk, expires_in)

    payload_url = request.build_absolute_uri(
        reverse("qrgen:redeem_land", args=[token])
    )

    # Fallback PIN.
    pin = _gen_qr_fallback_code()
    pin_hash = make_password(pin)

    qr_token = QRTokenYashPindataSave(
        branch=branch,
        desk=desk,
        token=token,
        pin_hash=pin_hash,
        expires_at=expires_at,
        staff_name=staff_name,
        staff_code=staff_code,
    )

    return JsonResponse({
        "ok": True,
        "payload": payload_url,
        "expires_in": expires_in,
        "branch": branch.name,
        "branch_public_id": getattr(branch, "public_id", "") or "",
        "branch_tag": _short_tag(branch),
        "desk": desk,
        "pin": pin,
        "staff_name": qr_token.staff_name,
        "staff_code": qr_token.staff_code,
        "staff_id": staff_id,
    })


def redeem_land(request, token: str):
    """
    Customer-side QR landing.

    Important:
    - Signed token parse alone is not enough.
    - DB QRToken must also be valid because staff deactivate can expire DB token.
    """

    try:
        info = parse_qr_token(token)
    except ValueError as e:
        return HttpResponseBadRequest(str(e))

    branch = (
        Branch.objects
        .filter(pk=info["bid"])
        .only("id", "name")
        .first()
    )

    if not branch:
        return HttpResponseBadRequest("Branch not found")

    now_ts = timezone.now()

    qr_token = (
        QRToken.objects
        .filter(
            branch=branch,
            token=token,
            used=False,
            expires_at__gt=now_ts,
        )
        .only("id", "branch_id", "desk", "staff_code", "expires_at", "used")
        .first()
    )

    if not qr_token:
        return HttpResponseBadRequest("QR expired or no longer valid")

    # If QR was created by staff, staff should still be active.
    # This is only on QR scan/landing action, not every request.
    if qr_token.staff_code:
        staff_still_active = BranchStaff.objects.filter(
            branch=branch,
            staff_id=qr_token.staff_code,
            is_active=True,
        ).exists()

        if not staff_still_active:
            return HttpResponseBadRequest("QR no longer valid")

    request.session["branch_id"] = branch.id
    request.session["branch_name"] = branch.name
    request.session["branch_desk"] = info.get("desk") or qr_token.desk
    request.session.modified = True

    return redirect(reverse("offers:user_home"))