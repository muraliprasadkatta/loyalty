# restarent_application66\offers\services\auth\otp_utils.py
import hashlib
import hmac
import secrets
import re
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone

OTP_TTL_MINUTES = 5
RESEND_COOLDOWN_SECONDS = 60
RESEND_WINDOW_MINUTES = 15
MAX_RESENDS_PER_15M = 3
MAX_VERIFY_ATTEMPTS = 5

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(e: str) -> str:
    return (e or "").strip().lower()


def valid_email(e: str) -> bool:
    e = normalize_email(e)
    if not e:
        return False
    try:
        validate_email(e)
        return True
    except ValidationError:
        return False


def gen_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(email: str, code: str, salt: str = "") -> str:
    secret = getattr(settings, "OTP_HMAC_SECRET", settings.SECRET_KEY)
    msg = f"{normalize_email(email)}::{code}::{salt}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def codes_match(stored_hash: str, email: str, code: str, salt: str = "") -> bool:
    expected = hash_code(email, code, salt=salt)
    return hmac.compare_digest(stored_hash, expected)


def now():
    return timezone.now()


def expires_at():
    return now() + timedelta(minutes=OTP_TTL_MINUTES)


def in_cooldown(last_sent_at):
    if not last_sent_at:
        return False, 0
    diff = (now() - last_sent_at).total_seconds()
    wait = max(0, RESEND_COOLDOWN_SECONDS - int(diff))
    return wait > 0, wait