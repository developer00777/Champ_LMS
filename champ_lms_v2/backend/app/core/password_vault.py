"""
Reversible storage for employee passwords, readable by admins only.

WHY THIS EXISTS
---------------
Champ LMS is an internal tool with no public sign-up: admins provision every
employee account. The product requirement is that an admin can read an
employee's *current* password (not just reset it), so support staff can hand a
password back to someone who has lost it.

That is a deliberate trade-off against the usual advice, and it is contained as
tightly as possible:

  * Authentication NEVER uses this module. Login verifies the submitted
    password against `User.hashed_password` (bcrypt, one-way) exactly as
    before. A bug in this file cannot weaken, bypass, or short-circuit the
    login check — the worst it can do is make the admin roster show a
    placeholder instead of a password.
  * Values are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256), so a
    stolen database dump alone does not reveal passwords — SECRET_KEY is also
    required.
  * Decryption is only ever called from admin-guarded endpoints.

Because the key is derived from SECRET_KEY, rotating SECRET_KEY makes existing
ciphertexts unreadable. That is treated as a non-event: `decrypt()` returns
None instead of raising, the admin UI shows the password as unavailable, and
the admin resets it. Login is unaffected by rotation.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

# Marks strings this module produced, so a value that was written before
# encryption existed (or by hand) is recognised as legacy plaintext rather
# than being fed to Fernet and discarded.
_PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    """
    Build the Fernet key from SECRET_KEY.

    SECRET_KEY is an arbitrary-length string, while Fernet needs exactly 32
    url-safe-base64 bytes, so it is run through SHA-256 first. A fixed
    application-specific salt keeps this key distinct from any other use of
    SECRET_KEY (JWT signing, in particular).
    """
    secret = get_settings().secret_key.encode()
    digest = hashlib.sha256(b"champ-lms/password-vault/v1|" + secret).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plain: str) -> str | None:
    """Encrypt a password for storage. Returns None for an empty value."""
    if not plain:
        return None
    token = _fernet().encrypt(plain.encode()).decode()
    return _PREFIX + token


def decrypt(stored: str | None) -> str | None:
    """
    Recover a stored password for an admin view.

    Returns None when there is nothing readable — no value, a value written
    under a previous SECRET_KEY, or a corrupted one. Callers treat None as
    "unavailable, reset it" and must not surface it as an error, since a
    rotated SECRET_KEY is a legitimate reason to land here.
    """
    if not stored:
        return None
    if not stored.startswith(_PREFIX):
        # Legacy plaintext from before this module existed — pass it through so
        # the roster keeps working; it gets re-encrypted on the next change.
        return stored
    try:
        return _fernet().decrypt(stored[len(_PREFIX) :].encode()).decode()
    except (InvalidToken, ValueError):
        return None
