from __future__ import annotations

from django.db import models
from django.db.utils import IntegrityError
from django.utils import timezone

from offers.models import UserOfferClaim, ComplementaryOffer, UserVisitEvent


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

    # Active offer for this branch (global OR eligible)
    offer = (
        ComplementaryOffer.objects
        .filter(is_active=True, start_at__lte=now_ts)
        .filter(models.Q(end_at__isnull=True) | models.Q(end_at__gte=now_ts))
        .filter(
            models.Q(all_branches=True) |
            models.Q(eligible_branches__id=int(branch_id))
        )
        .order_by("-id")
        .distinct()
        .first()
    )

    if not offer:
        return {
            "claim_issued": False,
            "claim_ids": [],
        }

    # Count visits AFTER current visit_event has been created
    visit_count = UserVisitEvent.objects.filter(
        user=user,
        branch_id=int(branch_id),
    ).count()

    hit_main = bool(
        offer.nth and offer.nth > 0 and (visit_count % offer.nth == 0)
    )

    hit_extra = []
    for ex in (offer.extra_nths or []):
        try:
            exn = int(ex)
        except Exception:
            continue
        if exn > 0 and visit_count == exn:
            hit_extra.append(exn)

    try:
        if hit_main:
            c = UserOfferClaim.objects.create(
                user=user,
                branch_id=int(branch_id),
                visit_event=visit_event,
                offer=offer,
                milestone_kind="main",
                milestone_n=offer.nth,
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
            claim_ids.append(c.id)
            claim_issued = True

        for exn in hit_extra:
            c = UserOfferClaim.objects.create(
                user=user,
                branch_id=int(branch_id),
                visit_event=visit_event,
                offer=offer,
                milestone_kind="extra",
                milestone_n=exn,
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
            claim_ids.append(c.id)
            claim_issued = True

    except IntegrityError:
        # Duplicate-claim race safe
        pass

    return {
        "claim_issued": claim_issued,
        "claim_ids": claim_ids,
    }