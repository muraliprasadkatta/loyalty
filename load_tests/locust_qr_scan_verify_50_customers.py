# D:\restarent_application66\locust_qr_scan_verify.py

"""
QR Scan Verify backend load test.

Goal:
- Test /qrg/scan-verify/ backend speed.
- Camera speed is NOT tested here.
- Each request creates:
  1) a fresh test user
  2) a fresh signed QR token
  3) a QRToken DB row
  4) a logged-in Django session
  5) POST /qrg/scan-verify/ with that token

Important:
- Run only on local/test database.
- This creates test Users, QRToken rows, UserVisitEvent rows, and maybe UserOfferClaim rows.
"""

import os
import json
import uuid
from datetime import timedelta

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

from offers.models import Branch, ComplementaryOffer, QRToken
from offers.services.qr.qr_token_utils import mint_qr_token


TEST_BRANCH_NAME = "loadtestqr"
TEST_BRANCH_EMAIL = "loadtestqr@example.com"
TEST_DESK = "LT1"
QR_TTL_SECONDS = 180

SCAN_VERIFY_URL = "/qrg/scan-verify/"


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
    Force this test branch into visit_unit='qr_code',
    so /qrg/scan-verify/ confirms visit immediately.

    This avoids qr_pin pending flow for this load test.
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
        # keep it active and valid
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
        nth=999999,              # avoid claim creation most of the time
        repeat=True,
        extra_nths=[],
        visit_unit="qr_code",    # IMPORTANT
        all_branches=False,
        start_at=now_ts - timedelta(minutes=5),
        end_at=now_ts + timedelta(days=1),
        issuance_mode="auto",
        redeem_type="code",
    )
    offer.eligible_branches.add(branch)
    return offer


def create_test_user():
    """
    One Locust virtual user ki one unique customer.
    So 50 Locust users = 50 different customers.
    """
    User = get_user_model()

    uid = uuid.uuid4().hex[:12]
    user = User.objects.create(
        username=f"qrload_visit_{uid}",
        email=f"qrload_visit_{uid}@loadtest.local",
        is_active=True,
        is_staff=False,
        is_superuser=False,
    )
    user.set_unusable_password()
    user.save(update_fields=["password"])

    return user



def create_logged_in_session(user):
    """
    Create a Django authenticated session manually for Locust.
    This avoids OTP/email login during backend verify load test.
    """
    session = SessionStore()
    session[SESSION_KEY] = str(user.pk)
    session[BACKEND_SESSION_KEY] = "django.contrib.auth.backends.ModelBackend"
    session[HASH_SESSION_KEY] = user.get_session_auth_hash()
    session.save()
    return session.session_key


def create_fresh_qr_token(branch):
    """
    Create a signed token + matching QRToken DB row.
    Unique desk is used so every token becomes unique during load test.
    """
    desk = f"LT{uuid.uuid4().hex[:8]}"

    token = mint_qr_token(
        branch_id=branch.id,
        desk=desk,
        ttl_seconds=QR_TTL_SECONDS,
    )

    expires_at = timezone.now() + timedelta(seconds=QR_TTL_SECONDS)

    QRToken.objects.create(
        branch=branch,
        desk=desk,
        token=token,
        expires_at=expires_at,
        used=False,
        staff_name="LOADTEST",
        staff_code="LT001",
    )

    return token

def make_csrf_token():
    # Django accepts matching cookie/header token for normal CSRF middleware.
    return get_random_string(32)


class QRScanVerifyUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        close_old_connections()

        self.branch = ensure_test_branch()
        ensure_qr_code_offer(self.branch)

        self.user = create_test_user()
        self.session_key = create_logged_in_session(self.user)

        self.did_first_visit = False

        close_old_connections()

    @task
    def scan_verify_valid_qr_code_flow(self):
        # One customer one actual visit only.
        # Visit create ayyaka ee virtual user idle mode lo untadu.
        if self.did_first_visit:
            return

        close_old_connections()

        token = create_fresh_qr_token(self.branch)
        csrf_token = make_csrf_token()

        self.client.cookies.clear()

        self.client.cookies.set(
            settings.SESSION_COOKIE_NAME,
            self.session_key,
            domain="127.0.0.1",
            path="/",
        )
        self.client.cookies.set(
            settings.CSRF_COOKIE_NAME,
            csrf_token,
            domain="127.0.0.1",
            path="/",
        )

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-CSRFToken": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
        }

        payload = {
            "token": token,
        }

        with self.client.post(
            SCAN_VERIFY_URL,
            data=json.dumps(payload),
            headers=headers,
            name="POST /qrg/scan-verify/ first visit create",
            catch_response=True,
        ) as response:
            try:
                data = response.json()
            except Exception:
                response.failure(
                    f"Non-JSON response status={response.status_code} body={response.text[:200]}"
                )
                close_old_connections()
                return

            if response.status_code != 200:
                response.failure(f"HTTP {response.status_code}: {data}")

            elif data.get("already_claimed_today"):
                response.failure(f"Unexpected duplicate visit for fresh customer: {data}")

            elif not data.get("ok"):
                response.failure(f"Backend ok=false: {data}")

            else:
                self.did_first_visit = True
                response.success()

        close_old_connections()