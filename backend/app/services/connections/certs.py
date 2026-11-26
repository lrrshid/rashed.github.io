"""CA certificates the app trusts for its connections (Settings > Network and certificates; ported from the Asset
Availability project).

A system administrator uploads the company CA certificate (the one that signed the directory's or the database's
server certificate):
PEM or DER, one certificate, at most MAX_BYTES. It is parsed with `cryptography`; its subject, issuer, validity and
SHA-256 fingerprint are kept, and the stored form is PEM. A certificate is public, so nothing here is secret; private
keys are never accepted (a file containing one is refused). Connections name the certificates they trust by id
(the LDAP profile's caCertIds); the bundle is built from those rows only, never from a path on the server.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding

MAX_BYTES = 64 * 1024


class CertificateProblem(ValueError):
    pass


def parse(data: bytes) -> dict:
    """The facts of one uploaded certificate, or CertificateProblem with a message for the admin."""
    if not data:
        raise CertificateProblem("The file is empty.")
    if len(data) > MAX_BYTES:
        raise CertificateProblem("A certificate file is at most 64 KB.")
    if b"PRIVATE KEY" in data:
        raise CertificateProblem("This file contains a private key. Upload only the CA certificate (.cer, .crt or "
                                 ".pem); a private key must never leave its server.")
    try:
        if b"-----BEGIN CERTIFICATE-----" in data:
            if data.count(b"-----BEGIN CERTIFICATE-----") > 1:
                raise CertificateProblem("The file holds several certificates. Upload them one by one.")
            cert = x509.load_pem_x509_certificate(data)
        else:
            cert = x509.load_der_x509_certificate(data)
    except CertificateProblem:
        raise
    except ValueError:
        raise CertificateProblem("This is not a certificate (PEM or DER). Ask IT for the company CA certificate "
                                 "(.cer, .crt or .pem).") from None
    try:
        is_ca = cert.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    except x509.ExtensionNotFound:
        is_ca = False
    der = cert.public_bytes(Encoding.DER)
    return {
        "pem": cert.public_bytes(Encoding.PEM).decode("ascii"),
        "sha256": hashlib.sha256(der).hexdigest(),
        "subject": cert.subject.rfc4514_string()[:500],
        "issuer": cert.issuer.rfc4514_string()[:500],
        "not_before": cert.not_valid_before_utc,
        "not_after": cert.not_valid_after_utc,
        "is_ca": is_ca,
    }


def state(not_after: datetime, now: datetime, warn_days: int = 30) -> str:
    """VALID, EXPIRING (within warn_days) or EXPIRED."""
    if not_after.tzinfo is None:
        not_after = not_after.replace(tzinfo=timezone.utc)
    if not_after <= now:
        return "EXPIRED"
    return "EXPIRING" if (not_after - now).days < warn_days else "VALID"
