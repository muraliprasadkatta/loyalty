from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model
from django.db.models import QuerySet
from django.utils import timezone

from offers.models import UserPendingVisitAttempt

User = get_user_model()


def upsert_pending_visit_attempt(
    *,
    user,
    branch,
    qr_token=None,
    yashpin=None,
    method: str = "scan",
    desk: str = "",
    state: str = UserPendingVisitAttempt.STATE_STARTED,
    note: str = "",
) -> Optional[UserPendingVisitAttempt]:
    """
    Create or update a single active pending attempt per user + branch.

    Same branch lo user retry chesthe new pending create cheyyakunda
    existing active row ni latest token/pin values tho update chestundi.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None

    if not branch or not qr_token:
        return None

    method = (method or UserPendingVisitAttempt.METHOD_SCAN).strip().lower()
    if method not in {
        UserPendingVisitAttempt.METHOD_SCAN,
        UserPendingVisitAttempt.METHOD_PIN,
    }:
        method = UserPendingVisitAttempt.METHOD_SCAN

    state = (state or UserPendingVisitAttempt.STATE_STARTED).strip().lower()
    allowed_states = {
        UserPendingVisitAttempt.STATE_STARTED,
        UserPendingVisitAttempt.STATE_AWAITING_BRANCH,
        UserPendingVisitAttempt.STATE_COMPLETED,
        UserPendingVisitAttempt.STATE_EXPIRED,
        UserPendingVisitAttempt.STATE_CANCELLED,
    }
    if state not in allowed_states:
        state = UserPendingVisitAttempt.STATE_STARTED

    active_states = [
        UserPendingVisitAttempt.STATE_STARTED,
        UserPendingVisitAttempt.STATE_AWAITING_BRANCH,
    ]

    existing = (
        UserPendingVisitAttempt.objects
        .filter(
            user=user,
            branch=branch,
            state__in=active_states,
        )
        .order_by("-id")
        .first()
    )

    if existing:
        existing.qr_token = qr_token
        existing.yashpin = yashpin
        existing.method = method
        existing.state = state
        existing.desk = desk or ""
        existing.note = note or ""
        existing.save(update_fields=[
            "qr_token",
            "yashpin",
            "method",
            "state",
            "desk",
            "note",
        ])
        return existing

    return UserPendingVisitAttempt.objects.create(
        user=user,
        branch=branch,
        qr_token=qr_token,
        yashpin=yashpin,
        method=method,
        state=state,
        desk=desk or "",
        note=note or "",
    )

def mark_pending_visit_attempt_completed(
    *,
    user,
    qr_token=None,
    note: str = "",
    completed_at=None,
) -> int:
    """
    Mark active pending attempts as completed for this exact user + qr_token.
    Returns updated row count.
    """
    if not user or not qr_token:
        return 0

    completed_at = completed_at or timezone.now()

    return (
        UserPendingVisitAttempt.objects
        .filter(
            user=user,
            qr_token=qr_token,
            state__in=[
                UserPendingVisitAttempt.STATE_STARTED,
                UserPendingVisitAttempt.STATE_AWAITING_BRANCH,
            ],
        )
        .update(
            state=UserPendingVisitAttempt.STATE_COMPLETED,
            completed_at=completed_at,
            note=note or "completed",
        )
    )


def mark_pending_visit_attempt_cancelled(
    *,
    user,
    qr_token=None,
    note: str = "",
    cancelled_at=None,
) -> int:
    """
    Mark active pending attempts as cancelled for this exact user + qr_token.
    Returns updated row count.
    """
    if not user or not qr_token:
        return 0

    cancelled_at = cancelled_at or timezone.now()

    return (
        UserPendingVisitAttempt.objects
        .filter(
            user=user,
            qr_token=qr_token,
            state__in=[
                UserPendingVisitAttempt.STATE_STARTED,
                UserPendingVisitAttempt.STATE_AWAITING_BRANCH,
            ],
        )
        .update(
            state=UserPendingVisitAttempt.STATE_CANCELLED,
            cancelled_at=cancelled_at,
            note=note or "cancelled",
        )
    )


def mark_pending_visit_attempt_expired(
    *,
    user=None,
    qr_token=None,
    note: str = "",
    expired_at=None,
) -> int:
    """
    Mark active pending attempts as expired.

    Can be used either:
    - for one exact user + qr_token
    - or broader expiry jobs later by adjusting filters
    """
    expired_at = expired_at or timezone.now()

    qs = UserPendingVisitAttempt.objects.filter(
        state__in=[
            UserPendingVisitAttempt.STATE_STARTED,
            UserPendingVisitAttempt.STATE_AWAITING_BRANCH,
        ],
    )

    if user is not None:
        qs = qs.filter(user=user)

    if qr_token is not None:
        qs = qs.filter(qr_token=qr_token)

    return qs.update(
        state=UserPendingVisitAttempt.STATE_EXPIRED,
        expired_at=expired_at,
        note=note or "expired",
    )


def get_user_active_pending_attempts(*, user) -> QuerySet[UserPendingVisitAttempt]:
    """
    Fetch active pending attempts for status page / dashboards.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return UserPendingVisitAttempt.objects.none()

    return (
        UserPendingVisitAttempt.objects
        .filter(
            user=user,
            state__in=[
                UserPendingVisitAttempt.STATE_STARTED,
                UserPendingVisitAttempt.STATE_AWAITING_BRANCH,
            ],
        )
        .select_related("branch", "qr_token", "yashpin")
        .order_by("-started_at")
    )