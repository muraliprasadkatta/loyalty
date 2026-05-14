# offers/services/qr/qr_pin_lookup.py

import hashlib
import hmac

from django.conf import settings


def normalize_manual_pin(pin: str) -> str:
    """
    Normalize customer-side manual QR PIN.
    Example: ' abcd ' -> 'ABCD'
    """
    return (pin or "").strip().upper()


def make_qr_pin_lookup(pin: str) -> str:
    """
    Secure deterministic lookup key for customer manual QR PIN search.

    Raw PIN DB lo store cheyyamu.
    Same PIN ki same lookup value ravali, so DB indexed lookup possible.
    """
    normalized = normalize_manual_pin(pin)

    key = getattr(settings, "OZ_QR_PIN_LOOKUP_SECRET", None) or settings.SECRET_KEY
    key_bytes = str(key).encode("utf-8")

    return hmac.new(
        key_bytes,
        normalized.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()