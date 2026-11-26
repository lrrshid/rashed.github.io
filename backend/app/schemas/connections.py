"""Request bodies of Settings > connections (ported from the Asset Availability project). Unknown fields are refused
(ApiModel). A connection's own fields arrive as a plain object and are checked against its provider's schema
(services/connections/registry.py)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import Field as PydanticField

from .common import ApiModel, Id, Version, optional_text, required_text

Kind = Literal["LDAP", "DATABASE"]


class Reauth(ApiModel):
    password: str = PydanticField(min_length=1, max_length=1024)


class ProfileCreate(ApiModel):
    kind: Kind
    provider: required_text(2, 30)
    name: required_text(2, 80)
    description: optional_text(500) = None
    purpose: required_text(2, 30)


class SecretChange(ApiModel):
    """keep: leave the saved value (the same as leaving the name out); replace: a new value; clear: delete it."""
    action: Literal["keep", "replace", "clear"]
    value: str | None = PydanticField(default=None, max_length=4096)


class DraftSave(ApiModel):
    draft_version: Version | None = None   # the draft's version when one exists (409 when someone else saved first)
    name: required_text(2, 80) | None = None
    description: optional_text(500) = None
    fields: dict[str, Any] = PydanticField(default_factory=dict)
    secrets: dict[str, SecretChange] = PydanticField(default_factory=dict)
    note: optional_text(500) = None


class Sample(ApiModel):
    username: optional_text(120) = None
    password: str | None = PydanticField(default=None, max_length=1024)  # used once for the test, never stored


class Candidate(ApiModel):
    fields: dict[str, Any] = PydanticField(default_factory=dict)
    secrets: dict[str, SecretChange] = PydanticField(default_factory=dict)


class TestRequest(ApiModel):
    __test__ = False  # not a pytest class
    target: Literal["draft", "active", "candidate"] = "draft"
    candidate: Candidate | None = None     # target "candidate": unsaved values (secrets not given are the draft's)
    sample: Sample | None = None


class Apply(ApiModel):
    draft_version: Version
    version: Version                       # the connection's


class VersionOnly(ApiModel):
    version: Version


class Rollback(ApiModel):
    revision_id: Id
    version: Version


class SignInMethod(ApiModel):
    method: Literal["local", "ldap"]
    version: Version | None = None         # CONNECTION_SETTING's, once Settings has saved a method


class EgressCreate(ApiModel):
    host: required_text(1, 253)
    port: int = PydanticField(ge=1, le=65535)
    purpose: Literal["LDAP", "DATABASE"]
    note: optional_text(500) = None


class EgressUpdate(ApiModel):
    version: Version
    host: required_text(1, 253) | None = None
    port: int | None = PydanticField(default=None, ge=1, le=65535)
    purpose: Literal["LDAP", "DATABASE"] | None = None
    note: optional_text(500) = None
