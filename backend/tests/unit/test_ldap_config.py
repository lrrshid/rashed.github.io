"""Company directory sign-in settings (ldap.env, AUTH_MODE=ldap) and username normalisation.

Nothing here touches the real project files: the settings files are written to a temporary folder and
config.LDAP_ENV_FILE / config.PROJECT_ROOT point there; every variable a test sets or loads is put back afterwards.
"""
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import app.core.config as config
from app.core.config import ConfigError, Settings, ldap_settings_from_env, load_settings
from app.security.directory import normalise_username

LDAP_KEYS = (
    "AUTH_MODE", "LDAP_SERVER", "LDAP_PORT", "LDAP_SECURITY", "LDAP_CA_FILE", "LDAP_BASE_DN", "LDAP_BIND_DN",
    "LDAP_BIND_PASSWORD", "LDAP_USERNAME_ATTRIBUTE", "LDAP_DISPLAY_NAME_ATTRIBUTE", "LDAP_USERNAME_PATTERN",
    "LDAP_TIMEOUT_SECONDS", "BREAK_GLASS_USERNAME", "SESSION_IDLE_MINUTES", "SESSION_ABSOLUTE_HOURS",
)


def _ca_certificate() -> x509.Certificate:
    """A throw-away self-signed CA certificate, standing in for the company CA."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Company Test CA")])
    now = datetime.now(timezone.utc)
    return (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=30))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))


@pytest.fixture(scope="module")
def ca_cert() -> x509.Certificate:
    return _ca_certificate()


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """No real ldap.env or .env is read, no sign-in variable leaks in, and whatever a test loads is removed again."""
    saved = os.environ.copy()
    for key in LDAP_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(config, "LDAP_ENV_FILE", tmp_path / "ldap.env")
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)
    yield tmp_path
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def ldap_env(isolated, monkeypatch, ca_cert):
    """A complete, valid set of directory settings in the environment (as if read from ldap.env)."""
    ca_file = isolated / "company-ca.pem"
    ca_file.write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    values = {
        "AUTH_MODE": "ldap",
        "LDAP_SERVER": "dc01.company.local, dc02.company.local",
        "LDAP_PORT": "636",
        "LDAP_SECURITY": "ldaps",
        "LDAP_CA_FILE": str(ca_file),
        "LDAP_BASE_DN": "OU=Staff,DC=company,DC=local",
        "LDAP_BIND_DN": "svc-cpc@company.local",
        "LDAP_BIND_PASSWORD": "Svc-Secret-Pass-9",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def _config_error(match: str):
    return pytest.raises(ConfigError, match=match)


# ---------------------------------------------------------------- username normalisation and the pattern

@pytest.mark.parametrize("typed", [
    "U12345", "u12345", " U12345 ", "COMPANY\\u12345", "company\\U12345", "u12345@company.local",
    " u12345@company.local ", "COMPANY\\ u12345 ",
])
def test_what_people_type_becomes_the_stored_username(typed):
    assert normalise_username(typed) == "U12345"


@pytest.mark.parametrize("typed, expected", [(None, ""), ("", ""), ("   ", ""), ("cpc.breakglass", "CPC.BREAKGLASS"),
                                             ("a\\b\\u7", "U7"), ("U1@a@b", "U1")])
def test_normalisation_edge_cases(typed, expected):
    assert normalise_username(typed) == expected


@pytest.mark.parametrize("name, ok", [
    ("U12345", True), ("u12345", True), ("U1", True),
    ("X123", False), ("U", False), ("U12a", False), ("", False), (" U12", False), ("U12 ", False),
    ("UU12", False), ("12345", False), ("U1*", False), ("U1)(objectClass=*", False), ("cpc.breakglass", False),
])
def test_default_pattern_is_u_followed_by_digits(name, ok):
    settings = Settings(profile="test", timezone="Asia/Dubai", database_url="sqlite://")
    assert settings.username_matches_pattern(name) is ok


def test_break_glass_name_matches_ignoring_case_and_is_off_when_empty():
    on = Settings(profile="test", timezone="Asia/Dubai", database_url="sqlite://", break_glass_username="cpc.breakglass")
    assert on.is_break_glass("CPC.BREAKGLASS") and on.is_break_glass(" cpc.breakglass ")
    assert not on.is_break_glass("cpc.breakglass2") and not on.is_break_glass("U12345")
    off = Settings(profile="test", timezone="Asia/Dubai", database_url="sqlite://")
    assert not off.is_break_glass("") and not off.is_break_glass("cpc.breakglass")


# ---------------------------------------------------------------- ldap_settings_from_env: a valid set

def test_a_complete_ldap_env_is_read(ldap_env):
    values = ldap_settings_from_env()
    assert values["ldap_servers"] == ("dc01.company.local", "dc02.company.local")  # failover order kept
    assert values["ldap_port"] == 636 and values["ldap_security"] == "ldaps"
    assert values["ldap_base_dn"] == "OU=Staff,DC=company,DC=local"
    assert values["ldap_bind_dn"] == "svc-cpc@company.local"
    assert values["ldap_bind_password"] == "Svc-Secret-Pass-9"
    assert values["ldap_username_attribute"] == "sAMAccountName"
    assert values["ldap_display_name_attribute"] == "displayName"
    assert values["ldap_username_pattern"] == "^U[0-9]+$"
    assert values["ldap_timeout_seconds"] == 5
    assert "BEGIN CERTIFICATE" in values["ldap_ca_data"]


def test_starttls_on_port_389_and_the_optional_keys(ldap_env, monkeypatch):
    monkeypatch.setenv("LDAP_SECURITY", "STARTTLS")
    monkeypatch.setenv("LDAP_PORT", "389")
    monkeypatch.setenv("LDAP_TIMEOUT_SECONDS", "10")
    monkeypatch.setenv("LDAP_USERNAME_ATTRIBUTE", "userPrincipalName")
    monkeypatch.setenv("LDAP_DISPLAY_NAME_ATTRIBUTE", "cn")
    monkeypatch.setenv("LDAP_USERNAME_PATTERN", "^U[0-9]{5}$")
    values = ldap_settings_from_env()
    assert (values["ldap_security"], values["ldap_port"], values["ldap_timeout_seconds"]) == ("starttls", 389, 10)
    assert values["ldap_username_attribute"] == "userPrincipalName" and values["ldap_display_name_attribute"] == "cn"
    assert values["ldap_username_pattern"] == "^U[0-9]{5}$"


def test_the_bind_password_is_not_trimmed_and_never_in_the_settings_repr(ldap_env, monkeypatch):
    monkeypatch.setenv("LDAP_BIND_PASSWORD", " Svc-Secret-Pass-9 ")
    values = ldap_settings_from_env()
    assert values["ldap_bind_password"] == " Svc-Secret-Pass-9 "
    settings = Settings(profile="test", timezone="Asia/Dubai", database_url="sqlite://", **values)
    assert "Svc-Secret-Pass-9" not in repr(settings) and "BEGIN CERTIFICATE" not in repr(settings)


# ---------------------------------------------------------------- ldap_settings_from_env: what IT can get wrong

@pytest.mark.parametrize("key", ["LDAP_SERVER", "LDAP_CA_FILE", "LDAP_BASE_DN", "LDAP_BIND_DN", "LDAP_BIND_PASSWORD"])
def test_every_required_key_is_named_with_the_file_to_edit(ldap_env, monkeypatch, key):
    monkeypatch.delenv(key)
    with _config_error(rf"AUTH_MODE=ldap needs {key} \(.*\)\. Set it in ldap\.env"):
        ldap_settings_from_env()


@pytest.mark.parametrize("key", ["LDAP_SERVER", "LDAP_BASE_DN", "LDAP_BIND_DN", "LDAP_BIND_PASSWORD", "LDAP_CA_FILE"])
def test_a_left_over_example_placeholder_is_refused(ldap_env, monkeypatch, key):
    monkeypatch.setenv(key, "<IT: fill this in, e.g. something>")
    with _config_error(rf"{key} is still the example placeholder.*ldap\.env"):
        ldap_settings_from_env()


def test_a_blank_bind_password_is_missing(ldap_env, monkeypatch):
    monkeypatch.setenv("LDAP_BIND_PASSWORD", "   ")
    with _config_error("needs LDAP_BIND_PASSWORD"):
        ldap_settings_from_env()


@pytest.mark.parametrize("server", ["ldaps://dc01.company.local", "dc01.company.local:636", "dc01/x", "dc 01", "dc01!"])
def test_ldap_server_is_a_plain_name(ldap_env, monkeypatch, server):
    monkeypatch.setenv("LDAP_SERVER", server)
    with _config_error(r"LDAP_SERVER .*ldap\.env"):
        ldap_settings_from_env()


def test_ldap_server_of_only_commas_is_missing(ldap_env, monkeypatch):
    monkeypatch.setenv("LDAP_SERVER", " , ,")
    with _config_error("needs LDAP_SERVER"):
        ldap_settings_from_env()


@pytest.mark.parametrize("port", ["abc", "636x", "0", "65536", "-1", "6 36"])
def test_ldap_port_must_be_a_port_number(ldap_env, monkeypatch, port):
    monkeypatch.setenv("LDAP_PORT", port)
    with _config_error(r"LDAP_PORT must be a whole number from 1 to 65535.*ldap\.env"):
        ldap_settings_from_env()


@pytest.mark.parametrize("security", ["none", "plain", "ldap", "ssl", "tls"])
def test_unencrypted_or_unknown_security_is_refused(ldap_env, monkeypatch, security):
    monkeypatch.setenv("LDAP_SECURITY", security)
    with _config_error(r"LDAP_SECURITY must be ldaps or starttls.*not supported.*ldap\.env"):
        ldap_settings_from_env()


def test_missing_ca_file_is_named(ldap_env, monkeypatch, tmp_path):
    monkeypatch.setenv("LDAP_CA_FILE", str(tmp_path / "nowhere" / "company-ca.cer"))
    with _config_error(r"LDAP_CA_FILE .*company-ca\.cer.* cannot be read.*ldap\.env"):
        ldap_settings_from_env()


def test_a_folder_is_not_a_ca_file(ldap_env, monkeypatch, tmp_path):
    monkeypatch.setenv("LDAP_CA_FILE", str(tmp_path))
    with _config_error("LDAP_CA_FILE .* cannot be read"):
        ldap_settings_from_env()


def test_a_ca_file_that_is_not_a_certificate_is_refused(ldap_env, monkeypatch, tmp_path):
    junk = tmp_path / "junk.cer"
    junk.write_bytes(b"this is not a certificate")
    monkeypatch.setenv("LDAP_CA_FILE", str(junk))
    with _config_error(r"LDAP_CA_FILE .* is not a certificate file \(PEM or DER\).*ldap\.env"):
        ldap_settings_from_env()


def test_a_der_ca_file_works_and_a_relative_path_is_from_the_project_root(ldap_env, monkeypatch, ca_cert, isolated):
    (isolated / "certs").mkdir()
    der = ca_cert.public_bytes(serialization.Encoding.DER)
    (isolated / "certs" / "company-ca.cer").write_bytes(der)
    monkeypatch.setenv("LDAP_CA_FILE", "certs/company-ca.cer")
    values = ldap_settings_from_env()
    assert values["ldap_ca_data"] == der
    assert values["ldap_ca_file"] == str(isolated / "certs" / "company-ca.cer")


def test_a_quoted_ca_path_works(ldap_env, monkeypatch):
    monkeypatch.setenv("LDAP_CA_FILE", f'"{ldap_env["LDAP_CA_FILE"]}"')
    assert ldap_settings_from_env()["ldap_ca_file"] == ldap_env["LDAP_CA_FILE"]


def test_base_dn_must_look_like_a_directory_path(ldap_env, monkeypatch):
    monkeypatch.setenv("LDAP_BASE_DN", "company.local")
    with _config_error(r"LDAP_BASE_DN .*OU=Staff,DC=company,DC=local.*ldap\.env"):
        ldap_settings_from_env()


@pytest.mark.parametrize("key", ["LDAP_USERNAME_ATTRIBUTE", "LDAP_DISPLAY_NAME_ATTRIBUTE"])
@pytest.mark.parametrize("value", ["sAM AccountName", "(cn=*)", "1abc", "name*"])
def test_attribute_names_are_checked(ldap_env, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with _config_error(rf"{key} must be a directory attribute name"):
        ldap_settings_from_env()


def test_a_broken_username_pattern_is_refused(ldap_env, monkeypatch):
    monkeypatch.setenv("LDAP_USERNAME_PATTERN", "^U[0-9+$")
    with _config_error(r"LDAP_USERNAME_PATTERN .* is not a valid pattern.*ldap\.env"):
        ldap_settings_from_env()


@pytest.mark.parametrize("pattern", [".*", "^U?[0-9]*$", "\\s*", "^(U[0-9]+)?$"])
def test_a_pattern_that_accepts_an_empty_username_is_refused(ldap_env, monkeypatch, pattern):
    monkeypatch.setenv("LDAP_USERNAME_PATTERN", pattern)
    with _config_error("would accept an empty username"):
        ldap_settings_from_env()


@pytest.mark.parametrize("timeout", ["0", "61", "five", "1.5"])
def test_timeout_is_one_to_sixty_seconds(ldap_env, monkeypatch, timeout):
    monkeypatch.setenv("LDAP_TIMEOUT_SECONDS", timeout)
    with _config_error(r"LDAP_TIMEOUT_SECONDS must be a whole number from 1 to 60"):
        ldap_settings_from_env()


# ---------------------------------------------------------------- load_settings: modes, break-glass, timeouts

def test_auth_mode_defaults_to_local_and_then_ignores_the_ldap_keys(isolated, monkeypatch):
    monkeypatch.setenv("LDAP_PORT", "not-a-port")      # not read at all in local mode
    monkeypatch.setenv("LDAP_SECURITY", "none")
    settings = load_settings("test")
    assert settings.auth_mode == "local" and not settings.is_ldap and settings.ldap_servers == ()
    assert settings.break_glass_username is None


def test_unknown_auth_mode_is_refused(isolated, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "kerberos")
    with _config_error(r"AUTH_MODE must be local or ldap; got 'kerberos'.*ldap\.env"):
        load_settings("test")


def test_auth_mode_ldap_without_a_server_names_the_key_and_the_file(isolated, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "LDAP")
    with pytest.raises(ConfigError) as caught:
        load_settings("test")
    assert str(caught.value).startswith(
        "AUTH_MODE=ldap needs LDAP_SERVER (the directory server name). Set it in ldap.env")


def test_auth_mode_ldap_with_everything_set(ldap_env, monkeypatch):
    monkeypatch.setenv("BREAK_GLASS_USERNAME", "cpc.breakglass")
    settings = load_settings("test")
    assert settings.is_ldap and settings.ldap_servers == ("dc01.company.local", "dc02.company.local")
    assert settings.break_glass_username == "cpc.breakglass"
    assert settings.session_idle_minutes == 30 and settings.session_absolute_hours == 12  # the default timeouts


@pytest.mark.parametrize("name, message", [
    ("U12345", "looks like a Windows username"),
    ("u99", "looks like a Windows username"),
    ("mock.admin", "must not be a mock account"),
    ("MOCK.anything", "must not be a mock account"),
    ("cpc breakglass", "letters A-Z, digits and . _ - only"),
    ("CORP\\breakglass", "letters A-Z, digits and . _ - only"),
    ("glass@company.local", "letters A-Z, digits and . _ - only"),
    ("x", "2 to 120 characters"),
])
def test_break_glass_name_is_checked_in_both_modes(isolated, monkeypatch, name, message):
    monkeypatch.setenv("BREAK_GLASS_USERNAME", name)
    with _config_error(message):
        load_settings("test")


def test_break_glass_name_follows_a_custom_pattern(isolated, monkeypatch):
    monkeypatch.setenv("LDAP_USERNAME_PATTERN", "^[A-Z]+\\.[A-Z]+$")
    monkeypatch.setenv("BREAK_GLASS_USERNAME", "cpc.breakglass")
    with _config_error("looks like a Windows username"):
        load_settings("test")


@pytest.mark.parametrize("key, value", [("SESSION_IDLE_MINUTES", "0"), ("SESSION_ABSOLUTE_HOURS", "0"),
                                        ("SESSION_IDLE_MINUTES", "-5")])
def test_session_timeouts_must_be_at_least_one(isolated, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with _config_error("SESSION_IDLE_MINUTES and SESSION_ABSOLUTE_HOURS must be at least 1"):
        load_settings("test")


def test_session_timeouts_are_read(isolated, monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_MINUTES", "15")
    monkeypatch.setenv("SESSION_ABSOLUTE_HOURS", "8")
    settings = load_settings("test")
    assert (settings.session_idle_minutes, settings.session_absolute_hours) == (15, 8)


# ---------------------------------------------------------------- precedence: environment > ldap.env > .env

def _write_settings_files(folder):
    (folder / "ldap.env").write_text(
        "# IT's file\nSESSION_IDLE_MINUTES=22\nBREAK_GLASS_USERNAME=from.ldapenv\n", encoding="utf-8")
    (folder / ".env").write_text(
        "SESSION_IDLE_MINUTES=33\nBREAK_GLASS_USERNAME=from.dotenv\nSESSION_ABSOLUTE_HOURS=7\n", encoding="utf-8")


def test_ldap_env_wins_over_dot_env(isolated):
    _write_settings_files(isolated)
    settings = load_settings("test")
    assert settings.session_idle_minutes == 22 and settings.break_glass_username == "from.ldapenv"
    assert settings.session_absolute_hours == 7  # a key only .env sets still comes from .env


def test_a_real_environment_variable_wins_over_both_files(isolated, monkeypatch):
    _write_settings_files(isolated)
    monkeypatch.setenv("SESSION_IDLE_MINUTES", "11")
    settings = load_settings("test")
    assert settings.session_idle_minutes == 11 and settings.break_glass_username == "from.ldapenv"


def test_without_ldap_env_the_dot_env_values_apply(isolated):
    (isolated / ".env").write_text("SESSION_IDLE_MINUTES=33\nBREAK_GLASS_USERNAME=from.dotenv\n", encoding="utf-8")
    settings = load_settings("test")
    assert settings.session_idle_minutes == 33 and settings.break_glass_username == "from.dotenv"
    assert settings.auth_mode == "local"


def test_ldap_env_switches_on_directory_sign_in(isolated, ca_cert):
    (isolated / "company-ca.pem").write_bytes(ca_cert.public_bytes(serialization.Encoding.PEM))
    (isolated / "ldap.env").write_text("\n".join([
        "AUTH_MODE=ldap",
        "LDAP_SERVER=dc01.company.local",
        "LDAP_SECURITY=starttls",
        "LDAP_PORT=389",
        "LDAP_CA_FILE=company-ca.pem",
        "LDAP_BASE_DN=OU=Staff,DC=company,DC=local",
        "LDAP_BIND_DN=CN=svc-cpc,OU=Service,DC=company,DC=local",
        "LDAP_BIND_PASSWORD=Svc-Secret-Pass-9",
        "BREAK_GLASS_USERNAME=cpc.breakglass",
    ]) + "\n", encoding="utf-8")
    settings = load_settings("test")
    assert settings.is_ldap and settings.ldap_security == "starttls" and settings.ldap_port == 389
    assert settings.ldap_bind_dn == "CN=svc-cpc,OU=Service,DC=company,DC=local"
    assert settings.ldap_ca_file == str(isolated / "company-ca.pem")


def test_the_example_file_left_unchanged_keeps_local_sign_in(isolated):
    """ldap.env.example copied as it is must start the app as today (AUTH_MODE=local): the placeholders are only
    checked once IT switches AUTH_MODE to ldap."""
    example = (Path(__file__).resolve().parents[3] / "ldap.env.example").read_text(encoding="utf-8")
    (isolated / "ldap.env").write_text(example, encoding="utf-8")
    settings = load_settings("test")
    assert settings.auth_mode == "local"


def test_switching_the_example_to_ldap_without_filling_it_in_names_the_first_placeholder(isolated):
    example = (Path(__file__).resolve().parents[3] / "ldap.env.example").read_text(encoding="utf-8")
    assert "AUTH_MODE=local" in example
    (isolated / "ldap.env").write_text(example.replace("AUTH_MODE=local", "AUTH_MODE=ldap"), encoding="utf-8")
    with _config_error(r"LDAP_SERVER is still the example placeholder .*Set it in ldap\.env"):
        load_settings("test")
