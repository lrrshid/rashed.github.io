"""Application configuration, read from environment variables (optionally the project-root files ldap.env and .env).

Precedence: real environment variables, then ldap.env (company directory sign-in, edited by IT on the server; see
ldap.env.example), then .env. A value set earlier is never replaced by a later file.

Profiles:
  demo   - local SQLite file, schema migrations and demo seeding run on startup.
  oracle - Oracle via python-oracledb; schema is applied by the DBA and only validated here.
  test   - isolated SQLite file per test run; nothing is seeded automatically.

Sign-in (AUTH_MODE):
  local - passwords stored in APP_USER (today's behaviour; the demo).
  ldap  - passwords checked by the company directory (LDAP / Active Directory) over TLS; the app still decides who
          may use the system (active APP_USER rows) and with which role and department scope.
"""
from __future__ import annotations

import os
import re
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values, load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_DIR = PROJECT_ROOT / "frontend"
SQLITE_MIGRATIONS_DIR = PROJECT_ROOT / "db" / "sqlite"
DATA_DIR = PROJECT_ROOT / "data"
LDAP_ENV_FILE = PROJECT_ROOT / "ldap.env"

PROFILES = ("demo", "oracle", "test")
AUTH_MODES = ("local", "ldap")
LDAP_SECURITY_MODES = ("ldaps", "starttls")  # plain, unencrypted LDAP is deliberately not offered
DEFAULT_USERNAME_PATTERN = r"^U[0-9]+$"
# A host name or an IPv4 address: no scheme, port or path (those have their own settings).
_HOST_RE = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
_ATTRIBUTE_RE = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,63}")
# The break-glass name is typed on the sign-in page and stored as a username: plain ASCII, no "@" or "\" (those are
# stripped from what people type as a domain part).
_BREAK_GLASS_RE = re.compile(r"[A-Za-z0-9._-]{2,120}")
_LDAP_FILE_HINT = "Set it in ldap.env (see ldap.env.example)."


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid. The message names the variable."""


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    value = raw.lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    # A typo such as SESSION_COOKIE_SECURE=ture must not silently switch a security setting off.
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


@dataclass
class Settings:
    profile: str
    timezone: str
    database_url: str
    session_idle_minutes: int = 30
    session_absolute_hours: int = 12
    cookie_secure: bool = True
    trusted_proxy_count: int = 0
    max_content_length: int = 64 * 1024
    login_max_failures: int = 5             # per (client IP, username)
    login_max_failures_per_ip: int = 20     # per client IP across all usernames (password spraying)
    login_window_seconds: int = 300
    auto_migrate: bool = False
    auto_seed: bool = False
    oracle_connect_args: dict = field(default_factory=dict)
    oracle_schema: str | None = None
    oracle_pool_max: int = 5
    oracle_thick_mode: bool = False
    oracle_client_lib_dir: str | None = None
    log_level: str = "INFO"
    local_env: bool = True                  # APP_ENV=local: the only place the shared-password mock accounts are seeded
    # ---- sign-in (see ldap.env.example) ----
    auth_mode: str = "local"                # local | ldap
    ldap_servers: tuple[str, ...] = ()      # tried in order: the first that answers is used
    ldap_port: int = 636
    ldap_security: str = "ldaps"            # ldaps | starttls
    ldap_ca_file: str | None = None
    ldap_ca_data: str | bytes | None = field(default=None, repr=False)  # the CA certificate(s), read at start-up
    ldap_base_dn: str | None = None
    ldap_bind_dn: str | None = None
    ldap_bind_password: str | None = field(default=None, repr=False)
    ldap_username_attribute: str = "sAMAccountName"
    ldap_display_name_attribute: str = "displayName"
    ldap_username_pattern: str = DEFAULT_USERNAME_PATTERN
    ldap_timeout_seconds: int = 5
    break_glass_username: str | None = None  # the one local emergency ADMIN in ldap mode; None = switched off
    # Where scheduled reports are written (a local folder or a shared folder on the local network; the system is
    # air-gapped and never sends e-mail). REPORTS_OUTPUT_DIR; relative paths are relative to the project folder.
    reports_dir: str = str(DATA_DIR / "reports")

    @property
    def data_mode(self) -> str:
        return "oracle" if self.profile == "oracle" else "demo"

    @property
    def is_ldap(self) -> bool:
        return self.auth_mode == "ldap"

    def username_matches_pattern(self, username: str) -> bool:
        """Does a normalised username look like a directory username (LDAP_USERNAME_PATTERN, ignoring case)?"""
        return re.fullmatch(self.ldap_username_pattern, username, re.IGNORECASE) is not None

    def is_break_glass(self, username: str) -> bool:
        name = self.break_glass_username
        return bool(name) and username.strip().lower() == name.lower()

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


def _check_timezone(name: str) -> None:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ConfigError(
            f"APP_TIMEZONE {name!r} is not a known IANA time zone (is the 'tzdata' package installed?)"
        ) from exc


def _read_ca_file(raw: str) -> tuple[str, str | bytes]:
    """LDAP_CA_FILE: the company CA certificate, PEM (text) or DER (binary .cer/.crt). Returns (path, data for
    ssl cadata). Checked here so a wrong file stops the start-up instead of every sign-in."""
    path = Path(raw.strip().strip('"'))
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise ConfigError(
            f"LDAP_CA_FILE {str(path)!r} cannot be read ({exc.strerror or exc}). Put the company CA certificate file "
            f"there or correct the path. {_LDAP_FILE_HINT}") from None
    data: str | bytes = content.decode("ascii", "replace") if b"-----BEGIN CERTIFICATE-----" in content else content
    try:
        ssl.create_default_context(cadata=data)
    except (ssl.SSLError, ValueError, TypeError) as exc:
        raise ConfigError(
            f"LDAP_CA_FILE {str(path)!r} is not a certificate file (PEM or DER): {exc}. Ask IT for the company CA "
            f"certificate (.cer, .crt or .pem). {_LDAP_FILE_HINT}") from None
    return str(path), data


def _ldap_int(name: str, default: int, low: int, high: int, what: str) -> int:
    raw = _env(name)
    if raw is None:
        return default
    if not re.fullmatch(r"[0-9]{1,6}", raw) or not (low <= int(raw) <= high):
        raise ConfigError(f"{name} must be a whole number from {low} to {high} ({what}); got {raw!r}. {_LDAP_FILE_HINT}")
    return int(raw)


def ldap_settings_from_env() -> dict:
    """The directory settings (AUTH_MODE=ldap), checked. Returns Settings field values. Every message names the key
    and the file to edit, for IT."""
    def need(name: str, what: str) -> str:
        value = _env(name)
        if value is None:
            raise ConfigError(f"AUTH_MODE=ldap needs {name} ({what}). {_LDAP_FILE_HINT}")
        if value.startswith("<") and value.endswith(">"):
            raise ConfigError(f"{name} is still the example placeholder {value}: fill in {what}. {_LDAP_FILE_HINT}")
        return value

    servers = tuple(s.strip() for s in need("LDAP_SERVER", "the directory server name").split(",") if s.strip())
    if not servers:
        raise ConfigError(f"AUTH_MODE=ldap needs LDAP_SERVER (the directory server name). {_LDAP_FILE_HINT}")
    for host in servers:
        if "://" in host or ":" in host or "/" in host:
            raise ConfigError(
                f"LDAP_SERVER {host!r}: write only the server name, e.g. dc01.company.local (no ldap:// or ldaps://; "
                f"the port goes in LDAP_PORT). {_LDAP_FILE_HINT}")
        if not _HOST_RE.fullmatch(host):
            raise ConfigError(f"LDAP_SERVER {host!r} is not a valid server name. {_LDAP_FILE_HINT}")
    port = _ldap_int("LDAP_PORT", 636, 1, 65535, "the directory port, usually 636 for ldaps or 389 for starttls")
    security = (_env("LDAP_SECURITY", "ldaps") or "ldaps").lower()
    if security not in LDAP_SECURITY_MODES:
        raise ConfigError(
            f"LDAP_SECURITY must be ldaps or starttls; got {security!r}. Plain, unencrypted LDAP is not supported: "
            f"passwords must never cross the network in clear text. {_LDAP_FILE_HINT}")
    ca_file, ca_data = _read_ca_file(need("LDAP_CA_FILE", "the path of the company CA certificate file"))
    base_dn = need("LDAP_BASE_DN", "where the user accounts are, e.g. OU=Staff,DC=company,DC=local")
    if "=" not in base_dn:
        raise ConfigError(f"LDAP_BASE_DN {base_dn!r} does not look like a directory path such as "
                          f"OU=Staff,DC=company,DC=local. {_LDAP_FILE_HINT}")
    bind_dn = need("LDAP_BIND_DN", "the read-only service account, e.g. svc-cpc@company.local")
    bind_password = os.environ.get("LDAP_BIND_PASSWORD") or ""  # not trimmed: a password may end with a space
    if not bind_password.strip():
        raise ConfigError(f"AUTH_MODE=ldap needs LDAP_BIND_PASSWORD (the service account's password). {_LDAP_FILE_HINT}")
    if bind_password.startswith("<") and bind_password.endswith(">"):
        raise ConfigError(f"LDAP_BIND_PASSWORD is still the example placeholder: fill in the service account's "
                          f"password. {_LDAP_FILE_HINT}")
    attributes = {}
    for name, default in (("LDAP_USERNAME_ATTRIBUTE", "sAMAccountName"),
                          ("LDAP_DISPLAY_NAME_ATTRIBUTE", "displayName")):
        value = _env(name, default)
        if not _ATTRIBUTE_RE.fullmatch(value):
            raise ConfigError(f"{name} must be a directory attribute name such as {default}; got {value!r}. "
                              f"{_LDAP_FILE_HINT}")
        attributes[name] = value
    pattern = _env("LDAP_USERNAME_PATTERN", DEFAULT_USERNAME_PATTERN)
    try:
        compiled = re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ConfigError(f"LDAP_USERNAME_PATTERN {pattern!r} is not a valid pattern ({exc}). {_LDAP_FILE_HINT}") from None
    if compiled.fullmatch("") is not None or compiled.fullmatch(" ") is not None:
        raise ConfigError(f"LDAP_USERNAME_PATTERN {pattern!r} would accept an empty username; use e.g. "
                          f"{DEFAULT_USERNAME_PATTERN} (U followed by digits). {_LDAP_FILE_HINT}")
    timeout = _ldap_int("LDAP_TIMEOUT_SECONDS", 5, 1, 60, "seconds to wait for the directory")
    return dict(
        ldap_servers=servers,
        ldap_port=port,
        ldap_security=security,
        ldap_ca_file=ca_file,
        ldap_ca_data=ca_data,
        ldap_base_dn=base_dn,
        ldap_bind_dn=bind_dn,
        ldap_bind_password=bind_password,
        ldap_username_attribute=attributes["LDAP_USERNAME_ATTRIBUTE"],
        ldap_display_name_attribute=attributes["LDAP_DISPLAY_NAME_ATTRIBUTE"],
        ldap_username_pattern=pattern,
        ldap_timeout_seconds=timeout,
    )


def _break_glass_username(pattern: str) -> str | None:
    name = _env("BREAK_GLASS_USERNAME")
    if name is None:
        return None
    if not _BREAK_GLASS_RE.fullmatch(name):
        raise ConfigError(f"BREAK_GLASS_USERNAME {name!r} must be 2 to 120 characters: letters A-Z, digits and . _ - "
                          f"only (for example cpc.breakglass). {_LDAP_FILE_HINT}")
    if name.lower().startswith("mock."):
        raise ConfigError("BREAK_GLASS_USERNAME must not be a mock account (their password is public). "
                          f"Choose another name, e.g. cpc.breakglass. {_LDAP_FILE_HINT}")
    try:
        looks_like_directory_user = re.fullmatch(pattern, name, re.IGNORECASE) is not None
    except re.error:
        looks_like_directory_user = False  # the pattern itself is reported by ldap_settings_from_env
    if looks_like_directory_user:
        raise ConfigError(f"BREAK_GLASS_USERNAME {name!r} looks like a Windows username: choose a name nobody has in "
                          f"the directory, e.g. cpc.breakglass. {_LDAP_FILE_HINT}")
    return name


def _load_settings_files() -> None:
    """Put ldap.env, then .env, into the environment: a variable set earlier is never replaced by a later file.
    One exception: every `flask --app wsgi ...` command has already copied .env into the environment (Flask's CLI
    does that before the app is imported), so a value there that is exactly the .env value came from .env, and
    ldap.env replaces it, as it does for the server. (A real environment variable that happens to equal the .env
    value is replaced the same way; give it in ldap.env instead.)"""
    dot_env = PROJECT_ROOT / ".env"
    if LDAP_ENV_FILE.is_file():
        from_dot_env = dotenv_values(dot_env) if dot_env.is_file() else {}
        for key, value in dotenv_values(LDAP_ENV_FILE).items():
            if value is not None and key in from_dot_env and os.environ.get(key) == from_dot_env[key]:
                os.environ[key] = value
    load_dotenv(LDAP_ENV_FILE, override=False)
    load_dotenv(dot_env, override=False)


def load_settings(profile: str | None = None, overrides: dict | None = None) -> Settings:
    """Build Settings from the environment. `overrides` lets tests replace individual fields."""
    _load_settings_files()
    profile = (profile or _env("APP_PROFILE", "demo")).lower()
    if profile not in PROFILES:
        raise ConfigError(f"APP_PROFILE must be one of {', '.join(PROFILES)}; got {profile!r}")

    timezone = _env("APP_TIMEZONE", "Asia/Dubai")
    _check_timezone(timezone)
    local = _env("APP_ENV", "local") == "local"
    # Secure session cookies by default outside local development, and always on the production (oracle)
    # profile, which runs behind HTTPS: only an explicit SESSION_COOKIE_SECURE=false turns them off there.
    secure_default = profile == "oracle" or not local
    log_level = (_env("LOG_LEVEL", "INFO") or "INFO").upper()
    if log_level not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        raise ConfigError(f"LOG_LEVEL must be one of DEBUG, INFO, WARNING, ERROR, CRITICAL; got {log_level!r}")
    auth_mode = (_env("AUTH_MODE", "local") or "local").lower()
    if auth_mode not in AUTH_MODES:
        raise ConfigError(f"AUTH_MODE must be local or ldap; got {auth_mode!r}. {_LDAP_FILE_HINT}")
    sign_in = {"auth_mode": auth_mode}
    if auth_mode == "ldap":
        sign_in.update(ldap_settings_from_env())
    sign_in["break_glass_username"] = _break_glass_username(
        sign_in.get("ldap_username_pattern") or _env("LDAP_USERNAME_PATTERN", DEFAULT_USERNAME_PATTERN))
    session_idle = _env_int("SESSION_IDLE_MINUTES", 30)
    session_absolute = _env_int("SESSION_ABSOLUTE_HOURS", 12)
    if session_idle < 1 or session_absolute < 1:
        raise ConfigError("SESSION_IDLE_MINUTES and SESSION_ABSOLUTE_HOURS must be at least 1.")

    reports_dir = Path(_env("REPORTS_OUTPUT_DIR", str(DATA_DIR / ("reports-test" if profile == "test" else "reports"))))
    if not reports_dir.is_absolute():
        reports_dir = PROJECT_ROOT / reports_dir
    common = dict(
        profile=profile,
        reports_dir=str(reports_dir),
        timezone=timezone,
        session_idle_minutes=session_idle,
        session_absolute_hours=session_absolute,
        cookie_secure=_env_bool("SESSION_COOKIE_SECURE", secure_default),
        trusted_proxy_count=_env_int("TRUSTED_PROXY_COUNT", 0),
        # Sign-in throttle. Many users behind one company IP (NAT/proxy) may need a higher per-IP limit.
        login_max_failures=_env_int("LOGIN_MAX_FAILURES", 5),
        login_max_failures_per_ip=_env_int("LOGIN_MAX_FAILURES_PER_IP", 20),
        login_window_seconds=_env_int("LOGIN_WINDOW_SECONDS", 300),
        log_level=log_level,
        local_env=local,
        **sign_in,
    )

    if profile == "oracle":
        dsn = _env("ORACLE_DSN")
        user = _env("ORACLE_USER")
        password = _env("ORACLE_PASSWORD")
        missing = [n for n, v in (("ORACLE_DSN", dsn), ("ORACLE_USER", user), ("ORACLE_PASSWORD", password)) if not v]
        if missing:
            raise ConfigError(f"Oracle profile requires {', '.join(missing)}. There is no fallback to demo data.")
        connect_args = {"user": user, "password": password, "dsn": dsn}
        for env_name, arg in (
            ("ORACLE_CONFIG_DIR", "config_dir"),
            ("ORACLE_WALLET_LOCATION", "wallet_location"),
            ("ORACLE_WALLET_PASSWORD", "wallet_password"),
        ):
            if _env(env_name):
                connect_args[arg] = _env(env_name)
        timeout = _env_int("ORACLE_TIMEOUT_SECONDS", 10)
        connect_args["tcp_connect_timeout"] = timeout
        schema = _env("ORACLE_SCHEMA")
        if schema is not None and not re.fullmatch(r"[A-Za-z][A-Za-z0-9_$#]{0,127}", schema):
            raise ConfigError("ORACLE_SCHEMA must be a plain Oracle identifier (the schema that owns the tables).")
        settings = Settings(
            database_url="oracle+oracledb://",
            oracle_connect_args=connect_args,
            oracle_schema=schema.upper() if schema else None,
            oracle_pool_max=_env_int("ORACLE_POOL_MAX", 5),
            oracle_thick_mode=_env_bool("ORACLE_THICK_MODE", False),
            oracle_client_lib_dir=_env("ORACLE_CLIENT_LIB_DIR"),
            **common,
        )
    elif profile == "demo":
        db_path = Path(_env("DEMO_DB_PATH", str(DATA_DIR / "cpc-demo.db")))
        if not db_path.is_absolute():
            db_path = PROJECT_ROOT / db_path  # relative paths are relative to the project, not the cwd
        settings = Settings(
            database_url=f"sqlite:///{db_path.as_posix()}",
            auto_migrate=True,
            auto_seed=not _env_bool("DEMO_SKIP_SEED", False),
            **common,
        )
    else:  # test
        settings = Settings(
            database_url=f"sqlite:///{(DATA_DIR / 'cpc-test.db').as_posix()}",
            auto_migrate=True,
            **{**common, "cookie_secure": False},
        )

    for key, value in (overrides or {}).items():
        if not hasattr(settings, key):
            raise ConfigError(f"Unknown setting override {key!r}")
        setattr(settings, key, value)
    return settings


def sqlite_path(settings: Settings) -> Path | None:
    if not settings.is_sqlite:
        return None
    return Path(settings.database_url.removeprefix("sqlite:///"))
