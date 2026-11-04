"""Company directory (LDAP / Microsoft Active Directory) for sign-in when AUTH_MODE=ldap.

The directory only answers "is this the right password for this Windows username?" and gives the display name.
Who may use the dashboard, with which role and stations, stays in the app (active APP_USER rows an ADMIN added).

How a sign-in is checked (authenticate):
  1. Refuse an empty password before anything is sent: many directories treat a simple bind with an empty
     password as an anonymous bind that "succeeds" (RFC 4513 5.1.2, unauthenticated bind). A password ldap3 cannot
     prepare for sending (SASLprep, RFC 4013: control characters, lone surrogates) is refused here too, as a wrong
     password: were it an outage (503, not counted by the sign-in throttle) it would tell anyone which usernames
     exist in the directory.
  2. The normalised username must match LDAP_USERNAME_PATTERN (U followed by digits).
  3. Sign in with the read-only service account and search LDAP_BASE_DN for exactly one user with that username
     (the value is escaped, so characters such as * ( ) \\ cannot change the search).
  4. Sign in again, on a NEW connection, as that user's DN with the typed password. Only this proves the password.
Network, certificate and service-account problems raise DirectoryUnavailable (HTTP 503); a wrong password, an
unknown or ambiguous user returns None.

Several servers in LDAP_SERVER are tried in order. One that fails is skipped for SERVER_RETRY_SECONDS (it is only
tried again after the others), so while dc01 is down a sign-in does not wait LDAP_TIMEOUT_SECONDS for it twice
(service connection, then the user's) on every attempt.

Every connection is encrypted (LDAPS, or STARTTLS before the password is sent), the server certificate must be
signed by the company CA in LDAP_CA_FILE, and its name must match LDAP_SERVER. Passwords are never logged.

Tests replace the network part through app.config["DIRECTORY_CONNECTION_FACTORY"]: a callable (user, password) ->
ldap3.Connection, for example over ldap3's built-in MOCK_SYNC server.
"""
from __future__ import annotations

import logging
import ssl
import threading
import time
from dataclasses import dataclass
from typing import Callable

from flask import current_app
from ldap3 import AUTO_BIND_NONE, BASE, NONE, SIMPLE, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException, LDAPPasswordIsMandatoryError, LDAPSASLPrepError
from ldap3.protocol.sasl.sasl import validate_simple_password
from ldap3.utils.conv import escape_filter_chars

from ..core.config import Settings
from ..exceptions import DirectoryUnavailable

log = logging.getLogger("cpc.directory")

ConnectionFactory = Callable[[str, str], Connection]

INVALID_CREDENTIALS = 49
NO_SUCH_OBJECT = 32
SIZE_LIMIT_EXCEEDED = 4
# Result codes that mean the directory cannot answer right now, not that the password is wrong:
# timeLimitExceeded, adminLimitExceeded, busy, unavailable, other.
_UNAVAILABLE_CODES = frozenset({3, 11, 51, 52, 80})
# A directory server that did not answer is tried last for this long (the next ones in LDAP_SERVER go first).
SERVER_RETRY_SECONDS = 60
_failed_servers: dict[tuple, float] = {}  # (host, port, security) -> time.monotonic() of the failure
_failed_lock = threading.Lock()

HINT_DNS = ("The server name was not found. Check the spelling of LDAP_SERVER, or ask IT for the full name "
            "(for example dc01.company.local).")
HINT_CERTIFICATE = ("The secure connection failed: the server's certificate is not trusted or does not carry the "
                    "name in LDAP_SERVER. Check LDAP_CA_FILE (the company CA certificate), that LDAP_SERVER is the "
                    "name on the server's certificate, and LDAP_SECURITY (ldaps uses port 636, starttls port 389).")
HINT_NETWORK = ("No answer from the server. Check LDAP_PORT (636 for ldaps, 389 for starttls) and that the firewall "
                "lets this server reach the directory on that port.")
HINT_SERVICE_ACCOUNT = ("The directory refused the service account. Check LDAP_BIND_DN and LDAP_BIND_PASSWORD (and "
                        "that the account is not disabled, locked or expired).")
HINT_BASE_DN = "The place to search does not exist. Check LDAP_BASE_DN (for example OU=Staff,DC=company,DC=local)."


@dataclass(frozen=True)
class DirectoryUser:
    username: str       # normalised, e.g. U12345
    display_name: str
    dn: str


@dataclass(frozen=True)
class CheckStep:
    """One line of the check-ldap report."""
    ok: bool
    message: str
    hint: str | None = None


def normalise_username(raw: str | None) -> str:
    """What people type -> the stored username: trim, drop a "DOMAIN\\" prefix and an "@domain" suffix, uppercase.
    "company\\u12345", " U12345@company.local " and "u12345" all become "U12345"."""
    name = (raw or "").strip()
    if "\\" in name:
        name = name.rsplit("\\", 1)[1]
    if "@" in name:
        name = name.split("@", 1)[0]
    return name.strip().upper()


def password_can_be_sent(password: str | None) -> bool:
    """May `password` be tried against the directory? Not when it is empty or blank (an anonymous bind could
    "succeed"), and not when ldap3 cannot prepare it for a simple bind (SASLprep refuses control characters and lone
    surrogates; characters it maps to nothing or to a space could leave it blank). Such a password is simply wrong."""
    if not password or not password.strip():
        return False
    try:
        prepared = validate_simple_password(password)
    except (LDAPSASLPrepError, LDAPPasswordIsMandatoryError):
        return False
    return bool(prepared.strip())


def explain(exc: BaseException) -> str:
    """A plain-words hint for a connection failure (DNS, certificate, network)."""
    text = str(exc).lower()
    if "invalid server address" in text or "getaddrinfo" in text or "name or service not known" in text \
            or "nodename" in text or "11001" in text:
        return HINT_DNS
    if isinstance(exc, ssl.SSLError) or any(w in text for w in ("certificate", "ssl", "tls", "handshake")):
        return HINT_CERTIFICATE
    return HINT_NETWORK


def _result(conn: Connection) -> tuple[int | None, str]:
    result = conn.result or {}
    return result.get("result"), f"{result.get('description') or ''} {result.get('message') or ''}".strip()


def _close(conn: Connection | None) -> None:
    if conn is None:
        return
    try:
        conn.unbind()
    except Exception:  # noqa: BLE001 - closing a broken connection must not hide the real outcome
        pass


def _first_text(value) -> str | None:
    if isinstance(value, (list, tuple)):
        value = next((v for v in value if v not in (None, "", b"")), None)
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


class Directory:
    def __init__(self, settings: Settings, connection_factory: ConnectionFactory | None = None):
        self.settings = settings
        self._factory = connection_factory

    # ---- connections ----------------------------------------------------------------------------------------------

    def _server(self, host: str) -> Server:
        s = self.settings
        tls = Tls(validate=ssl.CERT_REQUIRED, ca_certs_data=s.ldap_ca_data, sni=host)  # hostname checked by ldap3
        return Server(host, port=s.ldap_port, use_ssl=s.ldap_security == "ldaps", tls=tls,
                      connect_timeout=s.ldap_timeout_seconds, get_info=NONE)

    def _open(self, host: str, user: str, password: str) -> Connection:
        """An open, encrypted connection to one server, not yet signed in."""
        s = self.settings
        conn = Connection(self._server(host), user=user, password=password, authentication=SIMPLE,
                          auto_bind=AUTO_BIND_NONE, receive_timeout=s.ldap_timeout_seconds, read_only=True,
                          raise_exceptions=False, auto_referrals=False)
        try:
            conn.open()
            if s.ldap_security == "starttls" and not conn.start_tls():
                code, text = _result(conn)
                raise DirectoryUnavailable(f"{host}: STARTTLS refused ({text or code})", HINT_CERTIFICATE)
            return conn
        except BaseException:
            _close(conn)
            raise

    def _server_order(self) -> list[str]:
        """LDAP_SERVER in order, with the servers that failed in the last SERVER_RETRY_SECONDS moved to the end."""
        s = self.settings
        now = time.monotonic()
        with _failed_lock:
            failed = {host for host in s.ldap_servers
                      if now - _failed_servers.get((host, s.ldap_port, s.ldap_security), -1e9) < SERVER_RETRY_SECONDS}
        return [h for h in s.ldap_servers if h not in failed] + [h for h in s.ldap_servers if h in failed]

    def _remember(self, host: str, failed: bool) -> None:
        key = (host, self.settings.ldap_port, self.settings.ldap_security)
        with _failed_lock:
            if failed:
                _failed_servers[key] = time.monotonic()
            else:
                _failed_servers.pop(key, None)

    def _connect(self, user: str, password: str) -> Connection:
        """A connection to the first server in LDAP_SERVER that answers (the others are the fallback; one that just
        failed is tried last, see SERVER_RETRY_SECONDS)."""
        if self._factory is not None:
            try:
                return self._factory(user, password)
            except DirectoryUnavailable:
                raise
            except (LDAPException, OSError) as exc:
                raise DirectoryUnavailable(f"{type(exc).__name__}: {exc}", explain(exc)) from None
        failures = []
        for host in self._server_order():
            try:
                conn = self._open(host, user, password)
                self._remember(host, failed=False)
                return conn
            except DirectoryUnavailable as exc:
                failures.append((host, exc.detail, exc.hint))
            except (LDAPException, OSError) as exc:
                failures.append((host, f"{type(exc).__name__}: {exc}", explain(exc)))
            self._remember(host, failed=True)
            log.warning("directory server did not answer", extra={"fields": {"server": host, "error": failures[-1][1]}})
        detail = "; ".join(f"{host}: {error}" for host, error, _hint in failures)
        raise DirectoryUnavailable(detail or "no directory server configured", failures[-1][2] if failures else None)

    def _bind(self, conn: Connection) -> tuple[bool, int | None, str]:
        try:
            ok = conn.bind()
        except (LDAPSASLPrepError, LDAPPasswordIsMandatoryError):
            # ldap3 refused the password itself, before sending anything: a wrong password, never an outage.
            return False, None, "password cannot be sent (SASLprep)"
        except (LDAPException, OSError) as exc:
            raise DirectoryUnavailable(f"{type(exc).__name__}: {exc}", explain(exc)) from None
        code, text = _result(conn)
        return bool(ok), code, text

    def _service_connection(self) -> Connection:
        s = self.settings
        conn = self._connect(s.ldap_bind_dn, s.ldap_bind_password)
        try:
            ok, code, text = self._bind(conn)
        except BaseException:
            _close(conn)
            raise
        if not ok:
            _close(conn)
            raise DirectoryUnavailable(f"service account sign-in refused ({text or code})",
                                       HINT_SERVICE_ACCOUNT if code == INVALID_CREDENTIALS else None)
        return conn

    # ---- queries --------------------------------------------------------------------------------------------------

    def _find(self, conn: Connection, username: str) -> DirectoryUser | None:
        s = self.settings
        attr, display_attr = s.ldap_username_attribute, s.ldap_display_name_attribute
        search_filter = f"(&(objectClass=user)({attr}={escape_filter_chars(username)}))"
        try:
            conn.search(s.ldap_base_dn, search_filter, search_scope=SUBTREE, attributes=[attr, display_attr],
                        size_limit=2, time_limit=s.ldap_timeout_seconds)
        except (LDAPException, OSError) as exc:
            raise DirectoryUnavailable(f"search failed: {type(exc).__name__}: {exc}", explain(exc)) from None
        code, text = _result(conn)
        if code == NO_SUCH_OBJECT:
            raise DirectoryUnavailable(f"search base not found ({text})", HINT_BASE_DN)
        if code not in (0, SIZE_LIMIT_EXCEEDED, None):
            raise DirectoryUnavailable(f"search failed ({text or code})")
        entries = [e for e in (conn.response or []) if e.get("type") == "searchResEntry"]
        if code == SIZE_LIMIT_EXCEEDED or len(entries) != 1:
            if len(entries) > 1 or code == SIZE_LIMIT_EXCEEDED:
                log.warning("directory username is not unique", extra={"fields": {"username": username}})
            return None
        entry = entries[0]
        attributes = entry.get("attributes") or {}
        found_name = _first_text(attributes.get(attr))
        name = normalise_username(found_name) if found_name else username
        display = _first_text(attributes.get(display_attr)) or name
        return DirectoryUser(username=name, display_name=display[:160], dn=entry["dn"])

    def lookup(self, username: str) -> DirectoryUser | None:
        """Find one user by (normalised) username with the service account, without a password. For ADMINs adding a
        user and for check-ldap. None when not found, not unique or not a valid directory username."""
        username = normalise_username(username)
        if not self.settings.username_matches_pattern(username):
            return None
        conn = self._service_connection()
        try:
            return self._find(conn, username)
        finally:
            _close(conn)

    def authenticate(self, username: str, password: str) -> DirectoryUser | None:
        """The directory user when `password` is right for `username`, else None. Raises DirectoryUnavailable."""
        username = normalise_username(username)
        if not password_can_be_sent(password):
            return None  # never sent: an empty simple bind can be an anonymous bind that "succeeds"
        if not self.settings.username_matches_pattern(username):
            return None
        found = self.lookup(username)
        if found is None:
            return None
        # A new connection for the user's own sign-in: the service connection is never re-used for it.
        conn = self._connect(found.dn, password)
        try:
            ok, code, text = self._bind(conn)
        finally:
            _close(conn)
        if ok:
            return found
        if code in _UNAVAILABLE_CODES:
            raise DirectoryUnavailable(f"user sign-in could not be checked ({text or code})")
        # Active Directory explains a refusal in the message (data 52e wrong password, 533 disabled, 775 locked...).
        log.info("directory refused the sign-in", extra={"fields": {"username": username, "result": text or code}})
        return None

    # ---- check-ldap -----------------------------------------------------------------------------------------------

    def check(self, username: str | None = None) -> list[CheckStep]:
        """Step-by-step connection test for IT (flask check-ldap). Stops at the first failing step."""
        s = self.settings
        steps: list[CheckStep] = []
        if self._factory is None:
            reachable = False
            for host in s.ldap_servers:
                try:
                    _close(self._open(host, s.ldap_bind_dn, s.ldap_bind_password))
                    steps.append(CheckStep(True, f"Server {host} port {s.ldap_port} answered over {s.ldap_security}; "
                                                 f"its certificate is trusted."))
                    reachable = True
                except DirectoryUnavailable as exc:
                    steps.append(CheckStep(False, f"Server {host}: {exc.detail}", exc.hint))
                except (LDAPException, OSError) as exc:
                    steps.append(CheckStep(False, f"Server {host}: {type(exc).__name__}: {exc}", explain(exc)))
            if not reachable:
                return steps
        try:
            conn = self._service_connection()
        except DirectoryUnavailable as exc:
            steps.append(CheckStep(False, f"Service account {s.ldap_bind_dn}: {exc.detail}", exc.hint))
            return steps
        try:
            steps.append(CheckStep(True, f"Service account {s.ldap_bind_dn} signed in."))
            try:
                conn.search(s.ldap_base_dn, "(objectClass=*)", search_scope=BASE, attributes=[],
                            time_limit=s.ldap_timeout_seconds)
                code, text = _result(conn)
            except (LDAPException, OSError) as exc:
                code, text = None, f"{type(exc).__name__}: {exc}"
            if code != 0:
                steps.append(CheckStep(False, f"Search base {s.ldap_base_dn}: {text or code}", HINT_BASE_DN))
                return steps
            steps.append(CheckStep(True, f"Search base {s.ldap_base_dn} found."))
            if username:
                name = normalise_username(username)
                if not s.username_matches_pattern(name):
                    steps.append(CheckStep(False, f"{name} does not match LDAP_USERNAME_PATTERN "
                                                  f"{s.ldap_username_pattern}."))
                    return steps
                try:
                    found = self._find(conn, name)
                except DirectoryUnavailable as exc:
                    steps.append(CheckStep(False, f"Looking up {name}: {exc.detail}", exc.hint))
                    return steps
                if found is None:
                    steps.append(CheckStep(False, f"User {name} was not found under {s.ldap_base_dn} (or is not "
                                                  f"unique).", f"Check LDAP_BASE_DN and LDAP_USERNAME_ATTRIBUTE "
                                                               f"({s.ldap_username_attribute})."))
                else:
                    steps.append(CheckStep(True, f"User {found.username} found: {found.dn}, display name "
                                                 f"{found.display_name!r}."))
        finally:
            _close(conn)
        return steps


def get_directory() -> Directory:
    """The directory for the current app (tests may set app.config["DIRECTORY_CONNECTION_FACTORY"])."""
    return Directory(current_app.config["SETTINGS"], current_app.config.get("DIRECTORY_CONNECTION_FACTORY"))
