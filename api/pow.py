import hashlib
import time

from django.conf import settings
from rest_framework.permissions import BasePermission

def build_pow_payload(key_hash: str, method: str, path: str, timestamp: int, nonce: str) -> str:
    return f"{key_hash}:{method.upper()}:{path}:{timestamp}:{nonce}"

def pow_digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()

def verify_pow(
    *,
    key_hash: str,
    method: str,
    path: str,
    timestamp: int,
    nonce: str,
    difficulty: int,
    max_age_seconds: int,
) -> bool:
    now = int(time.time())
    if abs(now - int(timestamp)) > max_age_seconds:
        return False

    payload = build_pow_payload(key_hash, method, path, int(timestamp), nonce)
    digest = pow_digest(payload)
    return digest.startswith("0" * difficulty)

class ProofOfWorkPermission(BasePermission):
    message = "Valid proof-of-work is required."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            self.message = "Authentication required via X-Access-Key."
            return False

        nonce = request.headers.get("X-POW-Nonce")
        timestamp = request.headers.get("X-POW-Timestamp")
        if not nonce or not timestamp:
            self.message = "Missing X-POW-Nonce or X-POW-Timestamp header."
            return False

        try:
            timestamp_int = int(timestamp)
        except (TypeError, ValueError):
            self.message = "X-POW-Timestamp must be a unix timestamp."
            return False

        difficulty = int(getattr(settings, "POW_DIFFICULTY", 4))
        max_age_seconds = int(getattr(settings, "POW_MAX_AGE_SECONDS", 120))

        is_valid = verify_pow(
            key_hash=user.key_hash,
            method=request.method,
            path=request.path,
            timestamp=timestamp_int,
            nonce=nonce,
            difficulty=difficulty,
            max_age_seconds=max_age_seconds,
        )

        if not is_valid:
            self.message = "Invalid or expired proof-of-work."

        return is_valid
