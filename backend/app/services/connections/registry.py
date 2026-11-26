"""The providers Settings > connections knows, each described by an explicit, allow-listed schema (ported from the
Asset Availability project).

A Field says what an admin may enter (type, limits, choices, required to activate, shown under "Advanced"). Secret
fields are named separately: their values are never returned, only whether one is saved. validate() checks a set of
values against a provider: unknown names are refused, each value is checked for its type and limits, and with
`complete=True` (activation) every required field must be present. A provider marked FUTURE can be saved and
validated but never tested or activated. There is no free-form JSON and nothing executable.

Providers register here: the company directory (ldap_provider.py) and the main database (database_provider.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

SUPPORTED, FUTURE = "SUPPORTED", "FUTURE"
_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
_ATTRIBUTE = re.compile(r"[A-Za-z][A-Za-z0-9-]{0,63}")
_IDENTIFIER = re.compile(r"[A-Za-z][A-Za-z0-9_$#]{0,127}")      # an Oracle user or schema name
_SERVICE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")        # an Oracle service name
_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.db")   # a SQLite file in data/ (no folders)
_URL = re.compile(r"https?://[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?(?::[0-9]{1,5})?(?:/[A-Za-z0-9._~%/-]*)?")


@dataclass(frozen=True)
class Field:
    name: str
    type: str                 # text | int | choice | host | hosts | attribute | dn | pattern | certs | identifier
                              # | service | filename | url
    required: bool = False    # needed to activate (a draft may be incomplete)
    default: Any = None
    choices: tuple = ()
    low: int | None = None
    high: int | None = None
    max_len: int = 255
    advanced: bool = False


@dataclass(frozen=True)
class Provider:
    kind: str                 # LDAP | SSO | DATABASE | AI
    id: str                   # ldap, keycloak, oracle, ollama ...
    purposes: tuple[str, ...]
    status: str               # SUPPORTED | FUTURE
    schema_version: int
    fields: tuple[Field, ...]
    secrets: tuple[str, ...] = ()
    required_secrets: tuple[str, ...] = ()
    stages: tuple[str, ...] = ()           # test stages, in order
    required_stages: tuple[str, ...] = ()  # must have PASSED for the exact draft before it can be applied
    restart_required: bool = False
    check: Callable[[dict, bool], list] | None = field(default=None, compare=False)  # extra provider rules
    app_profiles: tuple[str, ...] = ()     # the APP_PROFILEs that offer it (empty: every one)
    note: str | None = None                # why it is FUTURE, or what it is for

    def field(self, name: str) -> Field | None:
        return next((f for f in self.fields if f.name == name), None)

    def describe(self) -> dict:
        """The schema as the browser shows it (no values)."""
        return {
            "kind": self.kind, "provider": self.id, "purposes": list(self.purposes), "status": self.status,
            "schemaVersion": self.schema_version, "restartRequired": self.restart_required,
            "appProfiles": list(self.app_profiles), "note": self.note,
            "stages": list(self.stages), "requiredStages": list(self.required_stages),
            "secrets": [{"name": s, "required": s in self.required_secrets} for s in self.secrets],
            "fields": [{"name": f.name, "type": f.type, "required": f.required, "default": f.default,
                        "choices": list(f.choices), "low": f.low, "high": f.high, "maxLength": f.max_len,
                        "advanced": f.advanced} for f in self.fields],
        }


_PROVIDERS: dict[tuple[str, str], Provider] = {}


def register(provider: Provider) -> Provider:
    _PROVIDERS[(provider.kind, provider.id)] = provider
    return provider


def get(kind: str, provider_id: str) -> Provider | None:
    return _PROVIDERS.get((kind, provider_id))


def all_providers() -> list[Provider]:
    return list(_PROVIDERS.values())


def _value_problem(f: Field, value) -> tuple[Any, str | None]:
    """(the normalised value, None) or (None, a message)."""
    if f.type == "int":
        if isinstance(value, bool) or not isinstance(value, (int, str)) or not str(value).strip().lstrip("-").isdigit():
            return None, "Must be a whole number."
        number = int(value)
        if (f.low is not None and number < f.low) or (f.high is not None and number > f.high):
            return None, f"Must be from {f.low} to {f.high}."
        return number, None
    if f.type == "certs":
        if not isinstance(value, list) or not all(isinstance(v, (str, int)) and str(v).isdigit() for v in value):
            return None, "Choose certificates from the list."
        return sorted({str(v) for v in value}, key=int)[:10], None
    if f.type == "host":
        host = str(value).strip()
        if "://" in host or ":" in host or "/" in host or not _HOST.fullmatch(host):
            return None, f"{host[:60]}: write only the server name, e.g. db01.company.local (no scheme and no port)."
        return host.lower(), None
    if f.type == "hosts":
        items = value if isinstance(value, list) else str(value or "").split(",")
        hosts = [str(h).strip() for h in items if str(h).strip()]
        if len(hosts) > 5:
            return None, "At most 5 servers."
        for host in hosts:
            if "://" in host or ":" in host or "/" in host or not _HOST.fullmatch(host):
                return None, f"{host[:60]}: write only the server name, e.g. dc01.company.local (no ldap:// and no port)."
        return hosts, None
    if not isinstance(value, str):
        return None, "Must be text."
    text = value.strip()
    if len(text) > f.max_len:
        return None, f"At most {f.max_len} characters."
    if f.type == "choice":
        upper = text.lower()
        if upper not in f.choices:
            return None, f"Must be one of: {', '.join(f.choices)}."
        return upper, None
    if f.type == "attribute" and text and not _ATTRIBUTE.fullmatch(text):
        return None, "Must be a directory attribute name such as sAMAccountName."
    if f.type == "identifier" and text and not _IDENTIFIER.fullmatch(text):
        return None, "Must be a plain name: letters, digits and _ $ #, starting with a letter."
    if f.type == "identifier":
        return text.upper(), None
    if f.type == "service" and text and not _SERVICE.fullmatch(text):
        return None, "Must be a service name such as ASSETS or assets.company.local."
    if f.type == "filename" and text and not _FILENAME.fullmatch(text):
        return None, "Must be a file name ending in .db, in the data folder (no folders), e.g. asset-new.db."
    if f.type == "url" and text:
        if not _URL.fullmatch(text):
            return None, "Must be an address such as https://sso.company.local/realms/staff (no spaces, no ?query)."
        return text.rstrip("/"), None
    if f.type == "dn" and text and "=" not in text:
        return None, "Must be a directory path such as OU=Staff,DC=company,DC=local."
    if f.type == "pattern" and text:
        try:
            compiled = re.compile(text, re.IGNORECASE)
        except re.error as exc:
            return None, f"Not a valid pattern ({exc})."
        if compiled.fullmatch("") is not None or compiled.fullmatch(" ") is not None:
            return None, "This pattern would accept an empty username."
    return text, None


def validate(provider: Provider, values: dict, complete: bool) -> tuple[dict, list[dict]]:
    """(normalised values, problems as [{"field", "message"}]). Unknown names are problems too."""
    problems, out = [], {}
    if not isinstance(values, dict):
        return {}, [{"field": "fields", "message": "Must be an object."}]
    for name in values:
        if provider.field(name) is None:
            problems.append({"field": name, "message": "Unknown setting."})
    for f in provider.fields:
        raw = values.get(f.name)
        empty = raw is None or raw == "" or raw == []
        if empty:
            if f.default is not None:
                out[f.name] = f.default
            elif complete and f.required:
                problems.append({"field": f.name, "message": "Required."})
            continue
        value, message = _value_problem(f, raw)
        if message:
            problems.append({"field": f.name, "message": message})
        elif value in ("", []) and complete and f.required:
            problems.append({"field": f.name, "message": "Required."})
        elif value not in ("", []):
            out[f.name] = value
    if provider.check is not None:  # on the values that are valid: every problem is listed at once
        flagged = {p["field"] for p in problems}
        problems.extend(p for p in provider.check(out, complete) if p["field"] not in flagged)
    return out, problems
