# D:\restarent_application66\locust_qr_scan_verify_precreated.py

"""
QR Scan Verify endpoint-only load test.

Goal:
- Pre-create users, sessions, QRToken rows before Locust sends requests.
- During Locust stats, measure mostly POST /qrg/scan-verify/ only.
- 50 Locust users = 50 pre-created customers = 50 actual visits.

Run only on loadtest DB.
"""

import os
import json
import uuid
import threading
from collections import deque
from datetime import timedelta
from urllib.parse import urlparse

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "offerzone.settings")

import django
django.setup()

from locust import HttpUser, task, between

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY
from django.contrib.sessions.backends.db import SessionStore
from django.db import close_old_connections
from django.utils import timezone
from django.utils.crypto import get_random_string

from offers.models import (
    Branch,
    ComplementaryOffer,
    QRToken,
    UserVisitEvent,
    UserOfferClaim,
)
from offers.services.qr.qr_token_utils import mint_qr_token


# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------
TEST_BRANCH_NAME = "loadtestqr"
TEST_BRANCH_EMAIL = "loadtestqr@example.com"
QR_TTL_SECONDS = 180

SCAN_VERIFY_URL = "/qrg/scan-verify/"

# PowerShell override optional:
# $env:QR_PRECREATE_COUNT="50"
PRECREATE_COUNT = int(os.getenv("QR_PRECREATE_COUNT", "50"))

# Clean old precreated test data before preparing new pool.
# PowerShell override:
# $env:QR_PRECREATE_CLEAN="0"
CLEAN_BEFORE_PREPARE = os.getenv("QR_PRECREATE_CLEAN", "1").strip() != "0"

USER_PREFIX = "qrpre_user_"
RUN_ID = os.getenv("QR_PRECREATE_RUN_ID", uuid.uuid4().hex[:8])


# -------------------------------------------------------------------
# TEST DATA HELPERS
# -------------------------------------------------------------------
def ensure_test_branch():
    branch, _ = Branch.objects.get_or_create(
        name=TEST_BRANCH_NAME,
        defaults={
            "display_title": "Load Test QR Branch",
            "location_title": "Load Test",
            "email": TEST_BRANCH_EMAIL,
        },
    )
    return branch


def ensure_qr_code_offer(branch):
    """
    Force this branch into visit_unit='qr_code',
    so /qrg/scan-verify/ confirms visit immediately.
    """
    now_ts = timezone.now()

    offer = (
        ComplementaryOffer.objects
        .filter(
            kind="complementary_offer",
            is_active=True,
            all_branches=False,
            eligible_branches=branch,
            visit_unit="qr_code",
        )
        .order_by("-id")
        .first()
    )

    if offer:
        changed = False

        if offer.start_at > now_ts:
            offer.start_at = now_ts - timedelta(minutes=5)
            changed = True

        if offer.end_at and offer.end_at <= now_ts:
            offer.end_at = now_ts + timedelta(days=1)
            changed = True

        if not offer.is_active:
            offer.is_active = True
            changed = True

        if changed:
            offer.save(update_fields=["start_at", "end_at", "is_active", "updated_at"])

        return offer

    offer = ComplementaryOffer.objects.create(
        kind="complementary_offer",
        title="Load Test QR Code Offer",
        is_active=True,
        count_start="campaign_start",
        nth=999999,              # avoid offer claim creation for this test
        repeat=True,
        extra_nths=[],
        visit_unit="qr_code",
        all_branches=False,
        start_at=now_ts - timedelta(minutes=5),
        end_at=now_ts + timedelta(days=1),
        issuance_mode="auto",
        redeem_type="code",
    )
    offer.eligible_branches.add(branch)
    return offer


def create_logged_in_session(user):
    """
    Create authenticated Django session manually.
    This avoids OTP/login flow during endpoint load testing.
    """
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    return session.session_key


def create_fresh_qr_token(branch):
    """
    Create signed QR payload + matching QRToken DB row.
    """
    desk = f"PRE{uuid.uuid4().hex[:8]}"

    token = mint_qr_token(
        branch_id=branch.id,
        desk=desk,
        ttl_seconds=QR_TTL_SECONDS,
    )

    QRToken.objects.create(
        branch=branch,
        desk=desk,
        token=token,
        expires_at=timezone.now() + timedelta(seconds=QR_TTL_SECONDS),
        used=False,
        staff_name="LOADTEST",
        staff_code="PRE001",
    )

    return token


def make_csrf_token():
    return get_random_string(32)


def clean_precreated_data(branch):
    """
    Clean only this loadtest branch + qrpre users.
    Safe for loadtest DB. Do not run on production.
    """
    User = get_user_model()

    UserOfferClaim.objects.filter(branch=branch).delete()
    UserVisitEvent.objects.filter(branch=branch).delete()
    QRToken.objects.filter(branch=branch).delete()
    User.objects.filter(username__startswith=USER_PREFIX).delete()


def prepare_pool():
    """
    Pre-create all data before Locust sends POST requests.
    This setup time is not counted in request stats.
    """
    close_old_connections()

    branch = ensure_test_branch()
    ensure_qr_code_offer(branch)

    if CLEAN_BEFORE_PREPARE:
        clean_precreated_data(branch)

    User = get_user_model()
    items = []

    for i in range(1, PRECREATE_COUNT + 1):
        username = f"{USER_PREFIX}{RUN_ID}_{i:04d}"

        user = User.objects.create(
            username=username,
            email=f"{username}@loadtest.local",
            is_active=True,
            is_staff=False,
            is_superuser=False,
        )
        user.set_unusable_password()
        user.save(update_fields=["password"])

        session_key = create_logged_in_session(user)
        csrf_token = make_csrf_token()
        qr_token = create_fresh_qr_token(branch)

        items.append(
            {
                "username": username,
                "user_id": user.id,
                "session_key": session_key,
                "csrf_token": csrf_token,
                "qr_token": qr_token,
            }
        )

    close_old_connections()

    print(
        f"[PREPARED] users={len(items)} branch={branch.name} "
        f"run_id={RUN_ID} clean={CLEAN_BEFORE_PREPARE}"
    )

    return deque(items)


_POOL = None
_POOL_LOCK = threading.Lock()


def get_next_precreated_item():
    global _POOL

    with _POOL_LOCK:
        if _POOL is None:
            _POOL = prepare_pool()

        if not _POOL:
            return None

        return _POOL.popleft()


# -------------------------------------------------------------------
# LOCUST USER
# -------------------------------------------------------------------
class QRScanVerifyPrecreatedUser(HttpUser):
    wait_time = between(10, 20)

    def on_start(self):
        close_old_connections()

        self.item = get_next_precreated_item()
        self.did_visit = False

        if not self.item:
            print("[NO ITEM] More Locust users than pre-created users.")
            return

        parsed = urlparse(self.host or "")
        cookie_domain = parsed.hostname or "127.0.0.1"

        self.client.cookies.clear()

        self.client.cookies.set(
            settings.SESSION_COOKIE_NAME,
            self.item["session_key"],
            domain=cookie_domain,
            path="/",
        )
        self.client.cookies.set(
            settings.CSRF_COOKIE_NAME,
            self.item["csrf_token"],
            domain=cookie_domain,
            path="/",
        )

        close_old_connections()

    @task
    def scan_verify_precreated_first_visit(self):
        if not self.item:
            return

        # One pre-created customer should create exactly one visit.
        if self.did_visit:
            return

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-CSRFToken": self.item["csrf_token"],
            "X-Requested-With": "XMLHttpRequest",
        }

        payload = {
            "token": self.item["qr_token"],
        }

        with self.client.post(
            SCAN_VERIFY_URL,
            data=json.dumps(payload),
            headers=headers,
            name="POST /qrg/scan-verify/ precreated first visit",
            catch_response=True,
        ) as response:
            try:
                data = response.json()
            except Exception:
                response.failure(
                    f"Non-JSON response status={response.status_code} "
                    f"body={response.text[:200]}"
                )
                return

            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}: {data}")

            elif data.get("already_claimed_today"):
                response.failure(f"Unexpected duplicate for precreated user: {data}")

            elif not data.get("ok"):
                response.failure(f"Backend ok=false: {data}")

            else:
                self.did_visit = True
                response.success()

        close_old_connections()