from __future__ import annotations

import logging

from django.db import models
from django.db.utils import IntegrityError
from django.utils import timezone

from offers.models import UserOfferClaim, ComplementaryOffer, UserVisitEvent

logger = logging.getLogger(__name__)


def issue_offer_claim_if_eligible(
    *,
    user,
    branch_id,
    visit_event,
    now_ts=None,
    token="",
    desk="",
    staff_name="",
    staff_code="",
):
    """
    Common claim issue service.

    Use this AFTER a visit has been successfully recorded.

    Returns:
        {
            "claim_issued": bool,
            "claim_ids": list[int],
        }
    """
    now_ts = now_ts or timezone.now()
    claim_ids = []
    claim_issued = False

    if not user or not branch_id or not visit_event:
        return {
            "claim_issued": False,
            "claim_ids": [],
        }

    # Active offer for this branch (branch-specific OR global)
    offer = (
        ComplementaryOffer.objects
        .filter(
            kind="complementary_offer",
            is_active=True,
            start_at__lte=now_ts,
        )
        .filter(models.Q(end_at__isnull=True) | models.Q(end_at__gte=now_ts))
        .filter(
            models.Q(all_branches=True) |
            models.Q(eligible_branches__id=int(branch_id))
        )
        .order_by("-start_at", "-id")
        .distinct()
        .first()
    )

    if not offer:
        return {
            "claim_issued": False,
            "claim_ids": [],
        }

    # Count visits only inside this offer window
    visits_qs = UserVisitEvent.objects.filter(
        user=user,
        branch_id=int(branch_id),
        created_at__gte=offer.start_at,
    )

    if offer.end_at:
        visits_qs = visits_qs.filter(created_at__lte=offer.end_at)

    visit_count = visits_qs.count()

    # ----------------------------
    # Main milestone logic
    # ----------------------------
    hit_main = False
    nth = int(offer.nth or 0)

    if nth > 0:
        if offer.repeat:
            hit_main = (visit_count % nth == 0)
        else:
            hit_main = (visit_count == nth)

    # ----------------------------
    # Extra milestone logic
    # ----------------------------
    hit_extra = []

    extras = []
    for ex in (offer.extra_nths or []):
        try:
            exn = int(ex)
        except Exception:
            continue
        if exn > 0:
            extras.append(exn)

    extras = sorted(set(extras))

    for exn in extras:
        if offer.repeat and nth > 0:
            # Example:
            # nth=5, extra=2 => hits at 2, 7, 12, 17...
            if visit_count >= exn and ((visit_count - exn) % nth == 0):
                hit_extra.append(exn)
        else:
            # once-only mode
            if visit_count == exn:
                hit_extra.append(exn)

    def _create_claim(*, milestone_kind: str, milestone_n: int):
        nonlocal claim_issued

        claim = UserOfferClaim.objects.create(
            user=user,
            branch_id=int(branch_id),
            visit_event=visit_event,
            offer=offer,
            milestone_kind=milestone_kind,
            milestone_n=milestone_n,
            offer_nth=offer.nth or None,
            offer_repeat=offer.repeat,
            offer_extra_nths=offer.extra_nths or [],
            offer_start_at=offer.start_at,
            offer_end_at=offer.end_at,
            token=token or "",
            desk=desk or "",
            staff_name=staff_name or "",
            staff_code=staff_code or "",
        )
        claim_ids.append(claim.id)
        claim_issued = True

    # Create claims
    try:
        if hit_main:
            _create_claim(
                milestone_kind="main",
                milestone_n=nth,
            )

        for exn in hit_extra:
            _create_claim(
                milestone_kind="extra",
                milestone_n=exn,
            )

    except IntegrityError as e:
        logger.warning(
            "UserOfferClaim IntegrityError user=%s branch=%s visit_event=%s error=%s",
            getattr(user, "id", None),
            branch_id,
            getattr(visit_event, "id", None),
            str(e),
        )

    return {
        "claim_issued": claim_issued,
        "claim_ids": claim_ids,
    }