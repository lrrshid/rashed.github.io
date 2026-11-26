"""Where the server may connect to (Settings > Network and certificates; OWASP SSRF Prevention; ported from the
Asset Availability project).

Every connection Settings manages, its tests and its real use alike, first asks check(host, port, purpose):
- the host and port must match an approved destination (EGRESS_RULE) for that purpose: the exact name, or a
  "*.company.local" rule for the names under it;
- every address the name resolves to is checked: cloud metadata, link-local, multicast, "this network" and the
  unspecified addresses are always refused; loopback only when the rule itself names localhost or a loopback address
  (a database on this server), never because some other rule matched.
So Settings cannot become a network scanner: an admin can only reach what was approved first, by purpose. The check
resolves the name itself and the connection then resolves it again; the network's own egress rules stay the outer
fence (docs/oracle-migration.md section 4).
"""
from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from typing import Callable, Iterable

PURPOSES = ("LDAP", "DATABASE")
_ALWAYS_BLOCKED = [ipaddress.ip_network(n) for n in (
    "0.0.0.0/8", "169.254.0.0/16", "224.0.0.0/4", "240.0.0.0/4", "100.100.100.200/32",  # metadata, link-local ...
    "::/128", "fe80::/10", "ff00::/8", "fd00:ec2::254/128")]
_LOOPBACK = [ipaddress.ip_network("127.0.0.0/8"), ipaddress.ip_network("::1/128")]
_LOOPBACK_NAMES = {"localhost", "localhost.localdomain"}

Resolver = Callable[[str, int], Iterable[str]]


class EgressDenied(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class Rule:
    host: str
    port: int
    purpose: str


def default_resolver(host: str, port: int) -> list[str]:
    return sorted({info[4][0] for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)})


def normalise_host(host: str) -> str:
    return (host or "").strip().rstrip(".").lower()


def valid_rule_host(host: str) -> bool:
    """A rule's host: a name, "*.name", or an IP address. No scheme, port, path or spaces."""
    host = normalise_host(host)
    if not host or len(host) > 253:
        return False
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        pass
    name = host[2:] if host.startswith("*.") else host
    if host.startswith("*.") and "." not in name:
        return False  # "*.local" would approve a whole top-level domain
    # Single-label intranet names ("keycloak", "dc01") are allowed.
    return all(1 <= len(label) <= 63 and label.replace("-", "").isascii() and label.replace("-", "").isalnum()
               and not label.startswith("-") and not label.endswith("-") for label in name.split("."))


def _matches(rule: Rule, host: str) -> bool:
    pattern = normalise_host(rule.host)
    if pattern.startswith("*."):
        return host.endswith(pattern[1:]) and host != pattern[2:]
    return host == pattern


def _rule_allows_loopback(rule: Rule) -> bool:
    name = normalise_host(rule.host)
    if name in _LOOPBACK_NAMES:
        return True
    try:
        return any(ipaddress.ip_address(name) in net for net in _LOOPBACK)
    except ValueError:
        return False


def check(host: str, port: int, purpose: str, rules: Iterable[Rule], resolver: Resolver | None = None) -> list[str]:
    """The addresses `host` resolves to, when the connection is allowed. Raises EgressDenied (code NOT_APPROVED,
    BLOCKED_ADDRESS or DNS_FAILED) with a message for the admin; nothing is connected here."""
    name = normalise_host(host)
    matching = [r for r in rules if r.purpose == purpose and r.port == port and _matches(r, name)]
    if not matching:
        raise EgressDenied("NOT_APPROVED", f"{name}:{port} is not an approved destination for {purpose}. Add it "
                                           f"under Network and certificates first.")
    try:
        addresses = list((resolver or default_resolver)(name, port))
    except OSError:
        raise EgressDenied("DNS_FAILED", f"{name} could not be found (DNS).") from None
    if not addresses:
        raise EgressDenied("DNS_FAILED", f"{name} could not be found (DNS).")
    loopback_ok = any(_rule_allows_loopback(r) for r in matching)
    for text in addresses:
        address = ipaddress.ip_address(text.split("%", 1)[0])
        if getattr(address, "ipv4_mapped", None):
            address = address.ipv4_mapped
        if any(address in net for net in _ALWAYS_BLOCKED):
            raise EgressDenied("BLOCKED_ADDRESS", f"{name} resolves to {address}, an address the app never connects "
                                                  f"to (link-local, metadata or multicast).")
        if any(address in net for net in _LOOPBACK) and not loopback_ok:
            raise EgressDenied("BLOCKED_ADDRESS", f"{name} resolves to this server itself ({address}). Approve "
                                                  f"localhost by name if that is intended.")
    return addresses
