# D:\restarent_application66\load_tests\locust_qr_pin_verify_precreated.py

"""
Manual PIN Verify endpoint-only load test.

Goal:
- Pre-create users, sessions, QRToken rows, YashPin rows before Locust sends requests.
- During Locust stats, measure mostly POST /qrg/pin-verify/ only.
- 50 Locust users = 50 pre-created customers = 50 manual PIN visits.

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
from django.contrib.auth.hashers import make_password
from django.db import close_old_connections
from django.utils import timezone
from django.utils.crypto import get_random_string

from offers.models import (
    Branch,
    ComplementaryOffer,
    QRToken,
    YashPin,
    UserVisitEvent,
    UserOfferClaim,
)
from offers.services.qr.qr_token_utils import mint_qr_token
from offers.services.qr.qr_pin_lookup import make_qr_pin_lookup


# -------------------------------------------------------------------
# CONFIG
# -------------------------------------------------------------------
TEST_BRANCH_NAME = "loadtestqr"
TEST_BRANCH_EMAIL = "loadtestqr@example.com"
QR_TTL_SECONDS = 180

PIN_VERIFY_URL = "/qrg/pin-verify/"

# PowerShell override optional:
# $env:PIN_PRECREATE_COUNT="50"
PRECREATE_COUNT = int(os.getenv("PIN_PRECREATE_COUNT", "50"))

# Clean old test data before preparing new pool.
# PowerShell override:
# $env:PIN_PRECREATE_CLEAN="0"
CLEAN_BEFORE_PREPARE = os.getenv("PIN_PRECREATE_CLEAN", "1").strip() != "0"

USER_PREFIX = "pinpre_user_"
RUN_ID = os.getenv("PIN_PRECREATE_RUN_ID", uuid.uuid4().hex[:8])


# -------------------------------------------------------------------
# TEST DATA HELPERS
# -------------------------------------------------------------------
def ensure_test_branch():
    branch, _ = Branch.objects.get_or_create(
        name=TEST_BRANCH_NAME,
        defaults={
            "display_title": "Load Test QR/PIN Branch",
            "location_title": "Load Test",
            "email": TEST_BRANCH_EMAIL,
        },
    )
    return branch


def ensure_qr_code_offer(branch):
    """
    Force this branch into visit_unit='qr_code',
    so /qrg/pin-verify/ can confirm visit immediately
    after YashPin resolves to QRToken.
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
        title="Load Test Manual PIN Offer",
        is_active=True,
        count_start="campaign_start",
        nth=999999,          # avoid offer claim creation for this test
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
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    return session.session_key


def make_csrf_token():
    return get_random_string(32)


def make_raw_pin(i):
    """
    4-character manual PIN using allowed chars only.
    Avoids invalid/ambiguous chars like 0, 1, I, L, O.
    """
    alphabet = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

    n = i
    chars = []
    for _ in range(4):
        chars.append(alphabet[n % len(alphabet)])
        n //= len(alphabet)

    return "".join(chars)
    

def create_fresh_qr_and_yashpin(branch, raw_pin):
    """
    Create signed QR payload + QRToken row + linked YashPin row.
    """
    desk = f"PIN{uuid.uuid4().hex[:8]}"
    expires_at = timezone.now() + timedelta(seconds=QR_TTL_SECONDS)

    token = mint_qr_token(
        branch_id=branch.id,
        desk=desk,
        ttl_seconds=QR_TTL_SECONDS,
    )

    qr = QRToken.objects.create(
        branch=branch,
        desk=desk,
        token=token,
        expires_at=expires_at,
        used=False,
        staff_name="LOADTEST",
        staff_code="PIN001",
    )

    YashPin.objects.create(
        branch=branch,
        desk=desk,
        qr_token=qr,
        pin_hash=make_password(raw_pin),
        pin_lookup=make_qr_pin_lookup(raw_pin),
        expires_at=expires_at,
        used=False,
        attempts=0,
        staff_name="LOADTEST",
        staff_code="PIN001",
    )

    return raw_pin


def clean_precreated_data(branch):
    """
    Clean only this loadtest branch + pinpre users.
    Safe for loadtest DB. Do not run on production.
    """
    User = get_user_model()

    UserOfferClaim.objects.filter(branch=branch).delete()
    UserVisitEvent.objects.filter(branch=branch).delete()
    YashPin.objects.filter(branch=branch).delete()
    QRToken.objects.filter(branch=branch).delete()
    User.objects.filter(username__startswith=USER_PREFIX).delete()


def prepare_pool():
    """
    Pre-create all data before Locust sends POST requests.
    Setup time is not counted in request stats.
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
        raw_pin = create_fresh_qr_and_yashpin(branch, make_raw_pin(i))

        items.append(
            {
                "username": username,
                "user_id": user.id,
                "session_key": session_key,
                "csrf_token": csrf_token,
                "pin": raw_pin,
            }
        )

    close_old_connections()

    print(
        f"[PIN PREPARED] users={len(items)} branch={branch.name} "
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
class QRPinVerifyPrecreatedUser(HttpUser):
    wait_time = between(10, 20)

    def on_start(self):
        close_old_connections()

        self.item = get_next_precreated_item()
        self.did_visit = False

        if not self.item:
            print("[NO ITEM] More Locust users than pre-created PIN users.")
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
    def pin_verify_precreated_first_visit(self):
        if not self.item:
            return

        if self.did_visit:
            return

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-CSRFToken": self.item["csrf_token"],
            "X-Requested-With": "XMLHttpRequest",
        }

        payload = {
            "pin": self.item["pin"],
        }

        with self.client.post(
            PIN_VERIFY_URL,
            data=json.dumps(payload),
            headers=headers,
            name="POST /qrg/pin-verify/ precreated first visit",
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
                response.failure(f"Unexpected duplicate for precreated PIN user: {data}")

            elif not data.get("ok"):
                response.failure(f"Backend ok=false: {data}")

            else:
                self.did_visit = True
                response.success()

        close_old_connections()