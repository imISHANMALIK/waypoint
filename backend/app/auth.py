"""Single-operator access control for a hosted sandbox; not a tenancy system."""
import hashlib
import hmac
import time

SESSION_SECONDS = 8 * 60 * 60


def sign_session(secret: str, now: int | None = None) -> str:
    stamp = str(int(time.time()) if now is None else now)
    digest = hmac.new(secret.encode(), f"waypoint:{stamp}".encode(), hashlib.sha256).hexdigest()
    return f"{stamp}.{digest}"


def valid_session(value: str, secret: str) -> bool:
    try:
        stamp = int(value.split('.')[0])
        age = int(time.time()) - stamp
        return 0 <= age <= SESSION_SECONDS and hmac.compare_digest(value, sign_session(secret, stamp))
    except (ValueError, TypeError, AttributeError):
        return False
