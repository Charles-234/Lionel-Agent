"""Pure MFA groundwork for Lionel's owner, collaborators, and dashboard.

Standard RFC 6238 TOTP implemented with the standard library only, so the
future admin dashboard has a real, testable second factor without adding
dependencies. This module is deliberately pure like the rest of identity/:
no I/O, no persistence, no secrets storage, no policy, no audit. Secret
generation uses the secrets module; verification uses constant-time
comparison; codes are accepted only inside a small, explicit window.
"""

import base64
import hashlib
import hmac
import secrets as _secrets
import time
import urllib.parse
from typing import Optional

_DIGIT_MODULUS = {6: 1000000, 7: 10000000, 8: 100000000}
_ALGORITHMS = {"sha1": hashlib.sha1, "sha256": hashlib.sha256, "sha512": hashlib.sha512}
_SECRET_BYTES = 20
_BASE32_CHUNK = 8


def _decode_secret(secret: str) -> bytes:
    if not isinstance(secret, str):
        raise ValueError("The shared secret must be a string.")
    cleaned = secret.strip().replace(" ", "").upper()
    if not cleaned:
        raise ValueError("The shared secret must not be empty.")
    padding = (-len(cleaned)) % _BASE32_CHUNK
    try:
        raw = base64.b32decode(cleaned + "=" * padding)
    except Exception:
        raise ValueError("The shared secret is not valid base32.")
    if not raw:
        raise ValueError("The shared secret decodes to nothing.")
    return raw


def _code_at(raw_secret: bytes, counter: int, digits: int, algorithm: str) -> str:
    if digits not in _DIGIT_MODULUS:
        raise ValueError("Digits must be 6, 7, or 8.")
    hasher = _ALGORITHMS.get(algorithm)
    if hasher is None:
        raise ValueError("Algorithm must be sha1, sha256, or sha512.")
    message = counter.to_bytes(8, "big")
    digest = hmac.new(raw_secret, message, hasher).digest()
    offset = digest[-1] & 0x0F
    binary = (
        (digest[offset] & 0x7F) << 24
        | (digest[offset + 1] & 0xFF) << 16
        | (digest[offset + 2] & 0xFF) << 8
        | (digest[offset + 3] & 0xFF)
    )
    return str(binary % _DIGIT_MODULUS[digits]).zfill(digits)


def generate_secret() -> str:
    """Create one fresh base32 shared secret (160 bits, no padding)."""
    raw = _secrets.token_bytes(_SECRET_BYTES)
    encoded = base64.b32encode(raw).decode("ascii")
    return encoded.rstrip("=")


def totp_at(
    secret: str,
    timestamp: float,
    *,
    step: int = 30,
    digits: int = 6,
    algorithm: str = "sha1",
) -> str:
    """Compute the one-time code for one Unix timestamp."""
    if not isinstance(step, int) or step < 1:
        raise ValueError("Step must be a positive integer of seconds.")
    raw = _decode_secret(secret)
    counter = int(timestamp // step)
    return _code_at(raw, counter, digits, algorithm)


def verify(
    secret: str,
    code: str,
    timestamp: Optional[float] = None,
    *,
    step: int = 30,
    digits: int = 6,
    algorithm: str = "sha1",
    window: int = 1,
) -> bool:
    """Check one code against a small window of neighbouring time steps.

    Returns True only for an exact, constant-time-matched code inside the
    window. Never raises for a wrong code; raises only for malformed input.
    """
    if not isinstance(code, str) or not code.strip().isdigit():
        return False
    code = code.strip()
    if len(code) != digits:
        return False
    if not isinstance(window, int) or window < 0 or window > 5:
        raise ValueError("Window must be an integer from 0 to 5.")
    if timestamp is None:
        timestamp = time.time()
    raw = _decode_secret(secret)
    counter = int(timestamp // step)
    for offset in range(-window, window + 1):
        candidate = _code_at(raw, counter + offset, digits, algorithm)
        if hmac.compare_digest(candidate, code):
            return True
    return False


def provisioning_uri(
    secret: str,
    account_name: str,
    issuer: str = "Lionel",
    *,
    digits: int = 6,
    period: int = 30,
    algorithm: str = "sha1",
) -> str:
    """Build the otpauth:// URI a phone authenticator app can scan."""
    decoded = _decode_secret(secret)
    encoded = base64.b32encode(decoded).decode("ascii").rstrip("=")
    label = urllib.parse.quote(f"{issuer}:{account_name}", safe="")
    query = urllib.parse.urlencode({
        "secret": encoded,
        "issuer": issuer,
        "algorithm": algorithm_name(algorithm),
        "digits": digits,
        "period": period,
    })
    return f"otpauth://totp/{label}?{query}"


def algorithm_name(algorithm: str = "sha1") -> str:
    if algorithm not in _ALGORITHMS:
        raise ValueError("Algorithm must be sha1, sha256, or sha512.")
    return algorithm.upper()


def digits_default() -> int:
    return 6


def period_default() -> int:
    return 30
