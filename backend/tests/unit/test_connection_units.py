"""Settings > connections, without a database: the secret box (AES-256-GCM), approved destinations, the field registry
and the settings key from the environment."""
from __future__ import annotations

import pytest

from app.core import secretbox
from app.core.config import ConfigError, _settings_keys
from app.services.connections import database_provider, egress, ldap_provider, registry


def test_secrets_round_trip_and_are_bound_to_their_field():
    key = secretbox.parse_key(secretbox.new_key_text())
    token = secretbox.encrypt((key,), "Svc-Secret", "profile 1 bindPassword")
    assert "Svc-Secret" not in token and token.startswith(secretbox.key_id(key) + ":")
    assert secretbox.decrypt((key,), token, "profile 1 bindPassword") == "Svc-Secret"
    with pytest.raises(secretbox.SecretUnavailable):
        secretbox.decrypt((key,), token, "profile 2 bindPassword")  # copied to another field: refused
    other = secretbox.parse_key(secretbox.new_key_text())
    with pytest.raises(secretbox.SecretUnavailable, match="not configured"):
        secretbox.decrypt((other,), token, "profile 1 bindPassword")
    assert secretbox.decrypt((other, key), token, "profile 1 bindPassword") == "Svc-Secret"  # a previous key reads


def test_the_settings_key_is_required_on_oracle_and_checked(monkeypatch):
    for name in ("SETTINGS_KEY", "SETTINGS_KEY_FILE", "SETTINGS_KEY_PREVIOUS"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(ConfigError, match="needs SETTINGS_KEY"):
        _settings_keys("oracle")
    monkeypatch.setenv("SETTINGS_KEY", "<make one>")
    with pytest.raises(ConfigError, match="placeholder"):
        _settings_keys("oracle")
    monkeypatch.setenv("SETTINGS_KEY", "too-short")
    with pytest.raises(ConfigError):
        _settings_keys("oracle")
    text = secretbox.new_key_text()
    monkeypatch.setenv("SETTINGS_KEY", text)
    assert _settings_keys("oracle") == (secretbox.parse_key(text),)


def test_egress_allows_only_approved_destinations_and_never_metadata():
    rules = (egress.Rule("dc01.company.local", 636, "LDAP"), egress.Rule("*.db.company.local", 1521, "DATABASE"))
    assert egress.check("DC01.company.local", 636, "LDAP", rules, lambda h, p: ["10.0.0.5"]) == ["10.0.0.5"]
    for host, port, purpose in (("dc01.company.local", 389, "LDAP"), ("dc01.company.local", 636, "DATABASE"),
                                ("db.company.local", 1521, "DATABASE"), ("dc02.company.local", 636, "LDAP")):
        with pytest.raises(egress.EgressDenied) as denied:
            egress.check(host, port, purpose, rules, lambda h, p: ["10.0.0.5"])
        assert denied.value.code == "NOT_APPROVED"
    assert egress.check("ora1.db.company.local", 1521, "DATABASE", rules, lambda h, p: ["10.0.0.9"])
    for address in ("169.254.169.254", "127.0.0.1", "0.0.0.0"):
        with pytest.raises(egress.EgressDenied) as denied:
            egress.check("dc01.company.local", 636, "LDAP", rules, lambda h, p, a=address: [a])
        assert denied.value.code == "BLOCKED_ADDRESS"
    assert not egress.valid_rule_host("*.local") and not egress.valid_rule_host("http://dc01")


def test_the_registry_refuses_unknown_and_invalid_values():
    values, problems = registry.validate(ldap_provider.PROVIDER, {"servers": "dc01.company.local, dc02.company.local",
                                                                  "baseDn": "OU=Staff,DC=company,DC=local"}, False)
    assert values["servers"] == ["dc01.company.local", "dc02.company.local"] and values["port"] == 636
    assert problems == []
    _values, problems = registry.validate(ldap_provider.PROVIDER, {"servers": ["ldaps://dc01"], "x": 1}, True)
    fields = {p["field"] for p in problems}
    assert {"servers", "x", "baseDn", "bindDn"} <= fields
    oracle, problems = registry.validate(database_provider.ORACLE, {"host": "db01.company.local", "serviceName": "CPC",
                                                                    "username": "cpc_app", "protocol": "tcps"}, True)
    assert oracle["username"] == "CPC_APP" and [p["field"] for p in problems] == ["caCertIds"]


def test_the_cutover_lines_never_hold_the_password():
    lines = database_provider.env_lines("oracle", {"host": "db01.company.local", "port": 1521, "serviceName": "CPCPDB",
                                                   "username": "CPC_APP", "schema": "CPC_OWNER"})
    assert lines[:3] == ["APP_PROFILE=oracle", "ORACLE_DSN=db01.company.local:1521/CPCPDB", "ORACLE_USER=CPC_APP"]
    assert any(line.startswith("ORACLE_PASSWORD=<") for line in lines)
    assert any(line.startswith("SETTINGS_KEY=<") for line in lines)
