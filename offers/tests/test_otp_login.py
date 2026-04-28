import json

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse
from datetime import timedelta
from django.utils import timezone

from offers.models import LoginOTP, Profile
import offers.user_views as user_views


def post_json(client, url_name, payload):
    return client.post(
        reverse(url_name),
        data=json.dumps(payload),
        content_type="application/json",
    )


@pytest.fixture(autouse=True)
def email_test_settings(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEFAULT_FROM_EMAIL = "noreply@example.com"


@pytest.mark.django_db
def test_otp_send_creates_login_otp_and_sends_email(client, monkeypatch):
    monkeypatch.setattr(user_views, "gen_code", lambda: "123456")

    response = post_json(client, "offers:otp_send", {
        "email": "TestUser@Example.com",
    })

    assert response.status_code == 200
    assert response.json()["ok"] is True

    row = LoginOTP.objects.get(email="testuser@example.com")

    assert row.used is False
    assert row.attempts == 0
    assert row.sent_count == 1
    assert len(mail.outbox) == 1
    assert "123456" in mail.outbox[0].body


@pytest.mark.django_db
def test_otp_verify_rejects_wrong_code_and_increments_attempts(client, monkeypatch):
    monkeypatch.setattr(user_views, "gen_code", lambda: "123456")

    post_json(client, "offers:otp_send", {
        "email": "testuser@example.com",
    })

    response = post_json(client, "offers:otp_verify", {
        "email": "testuser@example.com",
        "code": "000000",
    })

    assert response.status_code == 400
    assert response.json()["ok"] is False

    row = LoginOTP.objects.get(email="testuser@example.com")
    assert row.used is False
    assert row.attempts == 1


@pytest.mark.django_db
def test_otp_verify_correct_code_logs_user_in(client, monkeypatch):
    monkeypatch.setattr(user_views, "gen_code", lambda: "123456")

    post_json(client, "offers:otp_send", {
        "email": "testuser@example.com",
    })

    response = post_json(client, "offers:otp_verify", {
        "email": "testuser@example.com",
        "code": "123456",
    })

    assert response.status_code == 200

    data = response.json()
    assert data["ok"] is True
    assert "next" in data

    row = LoginOTP.objects.get(email="testuser@example.com")
    row.refresh_from_db()
    assert row.used is True

    User = get_user_model()
    user = User.objects.get(email="testuser@example.com")

    assert client.session.get("_auth_user_id") == str(user.pk)
    assert Profile.objects.filter(user=user).exists()


@pytest.mark.django_db
def test_otp_cannot_be_used_twice(client, monkeypatch):
    monkeypatch.setattr(user_views, "gen_code", lambda: "123456")

    post_json(client, "offers:otp_send", {
        "email": "testuser@example.com",
    })

    first = post_json(client, "offers:otp_verify", {
        "email": "testuser@example.com",
        "code": "123456",
    })

    assert first.status_code == 200
    assert first.json()["ok"] is True

    second = post_json(client, "offers:otp_verify", {
        "email": "testuser@example.com",
        "code": "123456",
    })

    assert second.status_code == 400
    assert second.json()["ok"] is False
    assert "already used" in second.json()["error"].lower()


@pytest.mark.django_db
def test_otp_send_rejects_invalid_email(client):
    response = post_json(client, "offers:otp_send", {
        "email": "wrong-email"
    })

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "invalid email" in response.json()["error"].lower()


@pytest.mark.django_db
def test_otp_verify_rejects_invalid_code_format(client):
    response = post_json(client, "offers:otp_verify", {
        "email": "testuser@example.com",
        "code": "123"
    })

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "valid 6-digit" in response.json()["error"].lower()

@pytest.mark.django_db
def test_otp_verify_rejects_expired_code(client, monkeypatch):
    monkeypatch.setattr(user_views, "gen_code", lambda: "123456")

    post_json(client, "offers:otp_send", {
        "email": "testuser@example.com",
    })

    row = LoginOTP.objects.get(email="testuser@example.com")
    row.expires_at = timezone.now() - timedelta(minutes=1)
    row.save(update_fields=["expires_at"])

    response = post_json(client, "offers:otp_verify", {
        "email": "testuser@example.com",
        "code": "123456",
    })

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "expired" in response.json()["error"].lower()


@pytest.mark.django_db
def test_otp_send_respects_resend_cooldown(client, monkeypatch):
    monkeypatch.setattr(user_views, "gen_code", lambda: "123456")

    first = post_json(client, "offers:otp_send", {
        "email": "testuser@example.com",
    })

    assert first.status_code == 200
    assert first.json()["ok"] is True

    second = post_json(client, "offers:otp_send", {
        "email": "testuser@example.com",
    })

    assert second.status_code == 429
    assert second.json()["ok"] is False
    assert "too many requests" in second.json()["error"].lower()

@pytest.mark.django_db
def test_otp_verify_blocks_after_max_wrong_attempts(client, monkeypatch):
    monkeypatch.setattr(user_views, "gen_code", lambda: "123456")

    post_json(client, "offers:otp_send", {
        "email": "testuser@example.com",
    })

    for _ in range(5):
        response = post_json(client, "offers:otp_verify", {
            "email": "testuser@example.com",
            "code": "000000",
        })
        assert response.status_code == 400

    blocked = post_json(client, "offers:otp_verify", {
        "email": "testuser@example.com",
        "code": "123456",
    })

    assert blocked.status_code == 429
    assert blocked.json()["ok"] is False
    assert "too many attempts" in blocked.json()["error"].lower()

@pytest.mark.django_db
def test_otp_verify_blocks_external_next_redirect(client, monkeypatch):
    monkeypatch.setattr(user_views, "gen_code", lambda: "123456")

    post_json(client, "offers:otp_send", {
        "email": "testuser@example.com",
    })

    response = post_json(client, "offers:otp_verify", {
        "email": "testuser@example.com",
        "code": "123456",
        "next": "https://evil.com/phishing-page",
    })

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["next"] == reverse("offers:user_home")


@pytest.mark.django_db
def test_otp_verify_blocks_admin_next_for_normal_user(client, monkeypatch):
    monkeypatch.setattr(user_views, "gen_code", lambda: "123456")

    post_json(client, "offers:otp_send", {
        "email": "testuser@example.com",
    })

    response = post_json(client, "offers:otp_verify", {
        "email": "testuser@example.com",
        "code": "123456",
        "next": "/admin/",
    })

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["next"] == reverse("offers:user_home")


@pytest.mark.django_db
def test_otp_verify_rejects_when_no_active_code_exists(client):
    response = post_json(client, "offers:otp_verify", {
        "email": "newuser@example.com",
        "code": "123456",
    })

    assert response.status_code == 400
    assert response.json()["ok"] is False
    assert "no active code" in response.json()["error"].lower()