"""The company directory (LDAP / Active Directory) as a Settings connection (ported from the Asset Availability project).

The fields are exactly what security/directory.py uses; nothing is shown that the code would ignore. Roles are not
taken from directory groups: who may come in, with which role and groups, is given in Settings > Users, so there
are no group mappings and a newly found directory user never gets any access by itself.

Tests run against a candidate (a Settings copy with the candidate's values), never the active configuration, and
stop at the first failing stage:
  NETWORK_TLS    each server is approved (egress), answers, and its certificate is trusted by the chosen CA
  SERVICE_BIND   the read-only service account signs in
  SEARCH_BASE    a bounded search of the base finds it
  SAMPLE_LOOKUP  optional: find one username (no password) and show the role it has in the app
  SIGN_IN        optional: a real sign-in with a username and password typed for this test only (never stored),
                 and the app account it would open: needed before the directory becomes the sign-in method
Encryption: LDAPS or StartTLS, checked against the chosen CA certificate; a TLS failure never falls back to plain text.
Plain, unencrypted LDAP ("ldap") is offered too, only as an explicit choice (as in the reference project): its
network stage is always a WARNING (passwords cross the network in clear text), so the connection shows as Degraded
everywhere until it is changed to LDAPS or StartTLS. It needs no CA certificate. ldap.env still refuses it.
"""
from __future__ import annotations

import dataclasses
import time

from ldap3 import BASE
from ldap3.core.exceptions import LDAPException

from ...core.config import DEFAULT_USERNAME_PATTERN, Settings
from ...exceptions import DirectoryUnavailable
from ...security.directory import Directory, _close, _result, explain, normalise_username
from . import egress
from .registry import SUPPORTED, Field, Provider, register

NETWORK_TLS, SERVICE_BIND, SEARCH_BASE, SAMPLE_LOOKUP, SIGN_IN = (
    "NETWORK_TLS", "SERVICE_BIND", "SEARCH_BASE", "SAMPLE_LOOKUP", "SIGN_IN")


def _check(values: dict, complete: bool) -> list[dict]:
    problems = []
    if values.get("security") == "ldaps" and values.get("port") == 389:
        problems.append({"field": "port", "message": "ldaps normally uses port 636 (389 is for starttls)."})
    if values.get("security") == "ldap" and values.get("port") == 636:
        problems.append({"field": "port", "message": "Plain LDAP normally uses port 389 (636 is for ldaps)."})
    if complete and not values.get("caCertIds") and values.get("security") != "ldap":
        problems.append({"field": "caCertIds", "message": "Choose the company CA certificate (upload it under "
                                                          "Network and certificates)."})
    return problems


PROVIDER = register(Provider(
    kind="LDAP", id="ldap", purposes=("SIGN_IN",), status=SUPPORTED, schema_version=1,
    fields=(
        Field("servers", "hosts", required=True),
        Field("port", "int", default=636, low=1, high=65535),
        Field("security", "choice", default="ldaps", choices=("ldaps", "starttls", "ldap")),
        Field("caCertIds", "certs"),  # required for ldaps and starttls (_check)
        Field("baseDn", "dn", required=True, max_len=500),
        Field("bindDn", "text", required=True, max_len=500),
        Field("usernamePattern", "pattern", default=DEFAULT_USERNAME_PATTERN, max_len=200),
        Field("searchScope", "choice", default="subtree", choices=("subtree", "level"), advanced=True),
        Field("userObjectClass", "attribute", default="user", advanced=True),
        Field("usernameAttribute", "attribute", default="sAMAccountName", advanced=True),
        Field("displayNameAttribute", "attribute", default="displayName", advanced=True),
        Field("timeoutSeconds", "int", default=5, low=1, high=60, advanced=True),
    ),
    secrets=("bindPassword",), required_secrets=("bindPassword",),
    stages=(NETWORK_TLS, SERVICE_BIND, SEARCH_BASE, SAMPLE_LOOKUP, SIGN_IN),
    required_stages=(NETWORK_TLS, SERVICE_BIND, SEARCH_BASE),
    check=_check,
))


def destinations(values: dict) -> list[tuple[str, int]]:
    return [(host, values.get("port", 636)) for host in values.get("servers", [])]


def settings_values(values: dict, secrets: dict, ca_pems: list[str]) -> dict:
    """The Settings fields this connection sets (the same ones ldap.env sets)."""
    return dict(
        ldap_servers=tuple(values.get("servers", ())),
        ldap_port=values.get("port", 636),
        ldap_security=values.get("security", "ldaps"),
        ldap_ca_file=None,
        ldap_ca_data="\n".join(ca_pems) or None,
        ldap_base_dn=values.get("baseDn"),
        ldap_bind_dn=values.get("bindDn"),
        ldap_bind_password=secrets.get("bindPassword"),
        ldap_username_attribute=values.get("usernameAttribute", "sAMAccountName"),
        ldap_display_name_attribute=values.get("displayNameAttribute", "displayName"),
        ldap_username_pattern=values.get("usernamePattern", DEFAULT_USERNAME_PATTERN),
        ldap_timeout_seconds=values.get("timeoutSeconds", 5),
        ldap_search_scope=values.get("searchScope", "subtree"),
        ldap_user_object_class=values.get("userObjectClass", "user"),
    )


@dataclasses.dataclass
class StageResult:
    stage: str
    outcome: str              # PASSED | WARNING | FAILED | SKIPPED
    message: str
    code: str | None = None
    latency_ms: int | None = None
    hint: str | None = None
    detail: dict | None = None  # e.g. the sample user's role preview (never a directory record dump)


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _redact(text: str | None) -> str:
    """Upstream text, short and one line (ldap3 messages hold no credentials, but never more than 300 chars)."""
    return " ".join((text or "").split())[:300]


def run_tests(base: Settings, candidate: dict, factory=None, sample: dict | None = None,
              account_role: callable = None) -> list[StageResult]:
    """Run the stages against `candidate` (settings_values() of the candidate, with egress_rules set). Stops at the
    first FAILED stage; the later ones are SKIPPED. `sample` = {"username", "password"?}: the optional stages.
    `account_role(username)` -> the app account's role preview (a dict) or None."""
    s = dataclasses.replace(base, **candidate)
    directory = Directory(s, factory)
    results: list[StageResult] = []

    def skip_rest(after: str):
        for stage in PROVIDER.stages[PROVIDER.stages.index(after) + 1:]:
            results.append(StageResult(stage, "SKIPPED", "Not run: an earlier stage failed."))
        return results

    # NETWORK_TLS
    start, reached, failures = time.perf_counter(), [], []
    for host in s.ldap_servers:
        try:
            directory.check_destination(host)
            if factory is None:
                _close(directory._open(host, s.ldap_bind_dn or "", ""))
            reached.append(host)
        except egress.EgressDenied as exc:
            failures.append((host, exc.code, exc.message, None))
        except DirectoryUnavailable as exc:
            failures.append((host, "UNREACHABLE", _redact(exc.detail), exc.hint))
        except (LDAPException, OSError) as exc:
            failures.append((host, "UNREACHABLE", _redact(f"{type(exc).__name__}: {exc}"), explain(exc)))
    if not reached:
        host, code, text, hint = failures[0] if failures else ("-", "NO_SERVER", "No server is set.", None)
        message = text if text.startswith(host) else f"{host}: {text}"  # an egress message already names the host
        results.append(StageResult(NETWORK_TLS, "FAILED", message, code, _ms(start), hint))
        return skip_rest(NETWORK_TLS)
    if s.ldap_security == "ldap":
        down = "; not reached: " + ", ".join(f"{h} ({t})" for h, _c, t, _hint in failures) if failures else ""
        results.append(StageResult(NETWORK_TLS, "WARNING", f"Reached {', '.join(reached)} without encryption: "
                                                         f"passwords cross the network in clear text{down}.",
                                   "PLAINTEXT", _ms(start), "Use LDAPS (636) or StartTLS (389) when the directory "
                                                            "allows it."))
    elif failures:
        down = ", ".join(f"{h} ({t})" for h, _c, t, _hint in failures)
        results.append(StageResult(NETWORK_TLS, "WARNING", f"Reached {', '.join(reached)} over {s.ldap_security} "
                                                         f"with a trusted certificate; not reached: {down}.",
                                   failures[0][1], _ms(start), failures[0][3]))
    else:
        results.append(StageResult(NETWORK_TLS, "PASSED", f"Reached {', '.join(reached)} over {s.ldap_security} "
                                                        f"with a trusted certificate.", None, _ms(start)))

    # SERVICE_BIND
    start = time.perf_counter()
    try:
        conn = directory._service_connection()
    except DirectoryUnavailable as exc:
        code = "CREDENTIALS_REJECTED" if "refused" in (exc.detail or "") else "UNAVAILABLE"
        results.append(StageResult(SERVICE_BIND, "FAILED", f"Service account {s.ldap_bind_dn}: {_redact(exc.detail)}",
                                   code, _ms(start), exc.hint))
        return skip_rest(SERVICE_BIND)
    try:
        results.append(StageResult(SERVICE_BIND, "PASSED", f"Service account {s.ldap_bind_dn} signed in.", None,
                                   _ms(start)))
        # SEARCH_BASE: the base entry itself, one result at most, bounded in time.
        start = time.perf_counter()
        try:
            conn.search(s.ldap_base_dn, "(objectClass=*)", search_scope=BASE, attributes=[], size_limit=1,
                        time_limit=s.ldap_timeout_seconds)
            code, text = _result(conn)
        except (LDAPException, OSError) as exc:
            code, text = None, f"{type(exc).__name__}: {exc}"
        if code != 0:
            results.append(StageResult(SEARCH_BASE, "FAILED", f"Search base {s.ldap_base_dn}: {_redact(text) or code}",
                                       "BASE_NOT_FOUND" if code == 32 else "SEARCH_FAILED", _ms(start)))
            return skip_rest(SEARCH_BASE)
        results.append(StageResult(SEARCH_BASE, "PASSED", f"Search base {s.ldap_base_dn} found.", None, _ms(start)))

        # SAMPLE_LOOKUP (optional)
        username = normalise_username((sample or {}).get("username"))
        if not username:
            results.append(StageResult(SAMPLE_LOOKUP, "SKIPPED", "No sample username was given."))
            results.append(StageResult(SIGN_IN, "SKIPPED", "No sample username was given."))
            return results
        start = time.perf_counter()
        if not s.username_matches_pattern(username):
            results.append(StageResult(SAMPLE_LOOKUP, "FAILED", f"{username} does not match the username pattern "
                                                               f"{s.ldap_username_pattern}.", "PATTERN", _ms(start)))
            return skip_rest(SAMPLE_LOOKUP)
        try:
            found = directory._find(conn, username)
        except DirectoryUnavailable as exc:
            results.append(StageResult(SAMPLE_LOOKUP, "FAILED", f"Looking up {username}: {_redact(exc.detail)}",
                                       "SEARCH_FAILED", _ms(start), exc.hint))
            return skip_rest(SAMPLE_LOOKUP)
        if found is None:
            results.append(StageResult(SAMPLE_LOOKUP, "FAILED", f"{username} was not found under {s.ldap_base_dn} "
                                                               f"(or is not unique).", "USER_NOT_FOUND", _ms(start)))
            return skip_rest(SAMPLE_LOOKUP)
        role = account_role(found.username) if account_role else None
        role_text = (f"In the app: {role['roleLabel']}{'' if role['active'] else ' (inactive)'}." if role
                     else "Not added in Settings > Users, so this person cannot sign in.")
        results.append(StageResult(SAMPLE_LOOKUP, "PASSED", f"{found.username} found ({found.display_name}). "
                                                            f"{role_text}", None, _ms(start),
                                   detail={"username": found.username, "displayName": found.display_name,
                                           "appAccount": role}))
    finally:
        _close(conn)

    # SIGN_IN (optional): a real bind as that person; the password is used once and forgotten.
    password = (sample or {}).get("password")
    if not password:
        results.append(StageResult(SIGN_IN, "SKIPPED", "No password was typed for a test sign-in."))
        return results
    start = time.perf_counter()
    try:
        user = directory.authenticate(username, password)
    except DirectoryUnavailable as exc:
        results.append(StageResult(SIGN_IN, "FAILED", f"Sign-in could not be checked: {_redact(exc.detail)}",
                                   "UNAVAILABLE", _ms(start), exc.hint))
        return results
    if user is None:
        results.append(StageResult(SIGN_IN, "FAILED", f"The directory refused the password for {username}.",
                                   "CREDENTIALS_REJECTED", _ms(start)))
        return results
    if not role or not role["active"]:
        results.append(StageResult(SIGN_IN, "FAILED", f"The directory accepted {user.username}, but the app has no "
                                                      f"active account for this username, so the sign-in would be "
                                                      f"refused.", "NO_APP_ACCOUNT", _ms(start)))
        return results
    results.append(StageResult(SIGN_IN, "PASSED", f"{user.username} signed in with the directory and would open "
                                                  f"the app as {role['roleLabel']}.", None, _ms(start),
                               detail={"username": user.username, "appAccount": role}))
    return results
