"""Secrets saved in Settings (the directory's service password, a database password), encrypted at rest.

AES-256-GCM (authenticated encryption, `cryptography`). The key is SETTINGS_KEY (or the file SETTINGS_KEY_FILE): 32
random bytes, base64. It lives with the deployment's other secrets, never in the database, so a copy of the database
alone reveals no secret. A token is "<key id>:<base64 of nonce + ciphertext>"; the key id (the first 8 hex digits of
the key's SHA-256) says which key made it, so the key can be rotated: put the old key in SETTINGS_KEY_PREVIOUS, the
new one in SETTINGS_KEY, then `flask settings-rotate-key` re-encrypts every saved secret with the new key.
Each secret is bound to its connection and field (the associated data), so a token copied to another field does not
decrypt. Plaintext never goes to logs, errors, audits or the browser. (Ported from the Asset Availability project.)
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import secrets
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12
NEW_KEY_COMMAND = 'python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"'


class SecretUnavailable(Exception):
    """A saved secret cannot be decrypted: its key is not configured, or the token is damaged."""


def parse_key(text: str, what: str = "SETTINGS_KEY") -> bytes:
    """A key from its base64 text (standard or URL-safe, padding optional). Raises ValueError naming `what`."""
    raw = text.strip()
    try:
        key = base64.urlsafe_b64decode(raw.replace("+", "-").replace("/", "_") + "=" * (-len(raw) % 4))
    except (binascii.Error, ValueError):
        raise ValueError(f"{what} is not base64.") from None
    if len(key) != KEY_BYTES:
        raise ValueError(f"{what} must be {KEY_BYTES} random bytes in base64 (44 characters); make one with: "
                         f"{NEW_KEY_COMMAND}")
    return key


def new_key_text() -> str:
    return base64.b64encode(secrets.token_bytes(KEY_BYTES)).decode("ascii")


def key_id(key: bytes) -> str:
    return hashlib.sha256(key).hexdigest()[:8]


def local_key(path: Path) -> bytes:
    """Demo and test profiles only: a key file made on first use (git-ignored), so a laptop needs no setup."""
    if not path.is_file():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:  # another process made it a moment ago
            pass
        else:
            with os.fdopen(fd, "w", encoding="ascii") as handle:
                handle.write(new_key_text() + "\n")
    return parse_key(path.read_text(encoding="ascii"), str(path))


def encrypt(keys: tuple[bytes, ...], plaintext: str, context: str) -> str:
    """With the current key (the first). `context` is the associated data, e.g. "profile 4 bindPassword"."""
    if not keys:
        raise SecretUnavailable("No SETTINGS_KEY is configured, so secrets cannot be saved.")
    key = keys[0]
    nonce = secrets.token_bytes(NONCE_BYTES)
    sealed = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), context.encode("utf-8"))
    return f"{key_id(key)}:{base64.b64encode(nonce + sealed).decode('ascii')}"


def decrypt(keys: tuple[bytes, ...], token: str, context: str) -> str:
    kid, _, body = token.partition(":")
    key = next((k for k in keys if key_id(k) == kid), None)
    if key is None:
        raise SecretUnavailable(f"The key {kid} that saved this secret is not configured (SETTINGS_KEY / "
                                f"SETTINGS_KEY_PREVIOUS). Enter the secret again.")
    try:
        data = base64.b64decode(body, validate=True)
        return AESGCM(key).decrypt(data[:NONCE_BYTES], data[NONCE_BYTES:], context.encode("utf-8")).decode("utf-8")
    except (InvalidTag, binascii.Error, ValueError, UnicodeDecodeError):
        raise SecretUnavailable("A saved secret could not be decrypted. Enter it again.") from None


def current_key_id(keys: tuple[bytes, ...]) -> str | None:
    return key_id(keys[0]) if keys else None


def token_key_id(token: str) -> str:
    return token.partition(":")[0]
