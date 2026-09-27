"""Password hashing with stdlib scrypt (memory-hard), so accounts add no native dependency."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

_N, _R, _P = 2**14, 8, 1
_DKLEN = 32


def hash_password(password: str) -> str:
    """Returns `scrypt$N$r$p$salt$hash` (base64). The parameters travel with the hash so they can be
    raised later without invalidating existing accounts."""
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, dklen=_DKLEN)
    return "$".join(
        ["scrypt", str(_N), str(_R), str(_P), base64.b64encode(salt).decode(), base64.b64encode(digest).decode()]
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = encoded.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(hash_b64)
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p), dklen=len(expected),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest, expected)


# A real hash to verify against when the email is unknown, so a login for a missing account takes
# as long as a wrong password and response timing doesn't reveal which emails are registered.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))
