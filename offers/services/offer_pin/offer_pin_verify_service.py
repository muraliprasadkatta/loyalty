from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.cache import never_cache, cache_control
from django.contrib.auth.hashers import check_password
from django.db import transaction
from offers.services.common.time_helpers import get_local_day_bounds

from offers.models import (
    OfferDayPin,
    UserVisitEvent,
    UserPendingVisitAttempt,
    QRToken,
    YashPin,
)

from offers.services.offer_claim.claim_issue_service import (
    issue_offer_claim_if_eligible,
)


def _close_matching_pending_attempt(
    *,
    user,
    branch_id,
    desk,
    now_ts,
    staff_name="",
    staff_code="",
    visit_event=None,
):
    qs = (
        UserPendingVisitAttempt.objects
        .select_for_update()
        .filter(
            user=user,
            branch_id=int(branch_id),
            state__in=[
                UserPendingVisitAttempt.STATE_STARTED,
                UserPendingVisitAttempt.STATE_AWAITING_BRANCH,
            ],
        )
        .order_by("-id")
    )

    if desk:
        qs = qs.filter(desk=desk)

    pending = qs.first()
    if not pending:
        return None

    model_field_names = {f.name for f in pending._meta.fields}
    update_fields = []

    pending.state = UserPendingVisitAttempt.STATE_COMPLETED
    update_fields.append("state")

    if "completed_at" in model_field_names:
        pending.completed_at = now_ts
        update_fields.append("completed_at")

    if "verified_at" in model_field_names:
        pending.verified_at = now_ts
        update_fields.append("verified_at")

    if visit_event is not None and "visit_event" in model_field_names:
        pending.visit_event = visit_event
        update_fields.append("visit_event")

    if "verified_by_staff_name" in model_field_names:
        pending.verified_by_staff_name = staff_name
        update_fields.append("verified_by_staff_name")

    if "verified_by_staff_code" in model_field_names:
        pending.verified_by_staff_code = staff_code
        update_fields.append("verified_by_staff_code")

    if "updated_at" in model_field_names:
        pending.updated_at = now_ts
        update_fields.append("updated_at")

    pending.save(update_fields=update_fields)
    return pending


def _validate_and_burn_related_visit_artifacts(
    *,
    user,
    branch_id,
    token,
    now_ts,
):
    """
    Ensure related QRToken / YashPin are still unused.
    If valid, burn them atomically.
    If already used/invalid, return an error string.
    """
    token = (token or "").strip()
    if not token:
        return "missing_qr_token"

    qt = (
        QRToken.objects
        .select_for_update()
        .filter(token=token, branch_id=int(branch_id))
        .first()
    )
    if not qt:
        return "qr_not_found"

    if qt.expires_at and qt.expires_at <= now_ts:
        return "qr_expired"

    if qt.used:
        return "qr_already_used"

    pin_row = (
        YashPin.objects
        .select_for_update()
        .filter(
            branch_id=int(branch_id),
            qr_token=qt,
        )
        .order_by("-created_at")
        .first()
    )

    if pin_row:
        if pin_row.expires_at and pin_row.expires_at <= now_ts:
            return "qr_pin_expired"

        if pin_row.used:
            return "qr_pin_already_used"

    # burn QRToken
    qt_update_fields = ["used", "used_at", "used_via"]
    qt.used = True
    qt.used_at = now_ts
    qt.used_via = "offer_day_pin"

    if hasattr(qt, "used_by_id"):
        qt.used_by = user
        qt_update_fields.append("used_by")

    qt.save(update_fields=qt_update_fields)

    # burn linked YashPin if present
    if pin_row:
        pin_update_fields = ["used", "used_at"]
        pin_row.used = True
        pin_row.used_at = now_ts

        if hasattr(pin_row, "used_by_id"):
            pin_row.used_by = user
            pin_update_fields.append("used_by")

        pin_row.save(update_fields=pin_update_fields)

    return None


@require_POST
@csrf_protect
@never_cache
@cache_control(no_cache=True, no_store=True, must_revalidate=True)
def branch_verify_offer_pin(request):
    """
    BRANCH SIDE:
      - Staff enters 4-digit OfferDay PIN
      - Validates & burns related QRToken / YashPin first
      - Burns OfferDayPin only after related artifacts are valid
      - Creates UserVisitEvent (offer_day_pin)
      - Issues claim through shared claim service
      - Closes matching UserPendingVisitAttempt
    """
    branch_id = request.session.get("branch_id")
    if not branch_id:
        return JsonResponse({"ok": False, "error": "branch_login_required"}, status=401)

    # read pin (POST or JSON)
    pin = (request.POST.get("pin") or "").strip()

    if (not pin) and request.content_type and ("application/json" in request.content_type.lower()):
        try:
            import json
            payload = json.loads(request.body.decode("utf-8") or "{}")
            pin = (payload.get("pin") or "").strip()
        except Exception:
            pin = ""

    if not (pin.isdigit() and len(pin) == 4):
        return JsonResponse({"ok": False, "error": "invalid_pin"}, status=400)

    now_ts = timezone.now()

    # small window scan
    cand = (
        OfferDayPin.objects
        .filter(branch_id=branch_id, used=False, expires_at__gt=now_ts)
        .order_by("-id")[:80]
    )

    match = None
    for r in cand:
        if check_password(pin, r.pin_hash):
            match = r
            break

    if not match:
        return JsonResponse({"ok": False, "error": "pin_not_found_or_expired"}, status=404)

    branch_name = request.session.get("branch_name") or ""
    staff_name = (request.session.get("branch_staff_name") or "").strip() or branch_name
    staff_code = (request.session.get("branch_staff_code") or "").strip()
    
    claim_issued = False
    claim_ids = []

    # local day start
    day_start, next_day_start = get_local_day_bounds(now_ts)

    with transaction.atomic():
        # lock pin row
        row = OfferDayPin.objects.select_for_update().filter(pk=match.pk).first()
        if not row:
            return JsonResponse({"ok": False, "error": "pin_not_found_or_expired"}, status=404)

        # re-check
        if row.used or row.expires_at <= now_ts:
            return JsonResponse({"ok": False, "error": "already_used_or_expired"}, status=409)

        # one-per-day per branch enforcement
        already_today = UserVisitEvent.objects.filter(
            user=row.user,
            branch_id=int(branch_id),
            created_at__gte=day_start,
            created_at__lt=next_day_start,
        ).exists()

        # validate + burn related QR / YashPin first
        artifact_error = _validate_and_burn_related_visit_artifacts(
            user=row.user,
            branch_id=int(branch_id),
            token=row.token,
            now_ts=now_ts,
        )
        if artifact_error:
            return JsonResponse(
                {"ok": False, "error": artifact_error},
                status=409,
            )

        # burn OfferDayPin only after related artifacts passed
        row.used = True
        row.used_at = now_ts
        row.used_by_staff_name = staff_name
        row.used_by_staff_code = staff_code
        row.save(update_fields=["used", "used_at", "used_by_staff_name", "used_by_staff_code"])

        if already_today:
            _close_matching_pending_attempt(
                user=row.user,
                branch_id=int(branch_id),
                desk=row.desk,
                now_ts=now_ts,
                staff_name=staff_name,
                staff_code=staff_code,
                visit_event=None,
            )

            return JsonResponse({
                "ok": True,
                "already_claimed_today": True,
                "user_id": row.user_id,
                "branch_id": int(branch_id),
                "desk": row.desk,
                "claim_issued": False,
                "claim_ids": [],
                "msg": "Already counted today ✅ (PIN consumed, QR/PIN closed)",
            })

        # create visit event only after QR/YashPin exclusivity passed
        ve = UserVisitEvent.objects.create(
            user=row.user,
            branch_id=int(branch_id),
            token=row.token,
            desk=row.desk,
            visit_method="offer_day_pin",
            staff_name=staff_name,
            staff_code=staff_code,
        )

        _close_matching_pending_attempt(
            user=row.user,
            branch_id=int(branch_id),
            desk=row.desk,
            now_ts=now_ts,
            staff_name=staff_name,
            staff_code=staff_code,
            visit_event=ve,
        )

        # shared claim issue service
        claim_result = issue_offer_claim_if_eligible(
            user=row.user,
            branch_id=int(branch_id),
            visit_event=ve,
            now_ts=now_ts,
            token=row.token or "",
            desk=row.desk or "",
            staff_name=staff_name,
            staff_code=staff_code,
        )
        claim_issued = bool(claim_result.get("claim_issued"))
        claim_ids = list(claim_result.get("claim_ids") or [])

    return JsonResponse({
        "ok": True,
        "already_claimed_today": False,
        "visit_event_id": ve.id,
        "user_id": row.user_id,
        "branch_id": int(branch_id),
        "desk": row.desk,
        "claim_issued": claim_issued,
        "claim_ids": claim_ids,
        "msg": "Offer PIN verified ✅ visit recorded",
    })