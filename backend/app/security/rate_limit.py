"""In-memory login throttle.

Two limits over a sliding window:
  - per (client IP, username): stops guessing one account's password;
  - per client IP across all usernames: stops one client spraying a password over many accounts.
Entries expire with the window and the table is capped, so memory stays bounded.

Single-process only (fine for the demo and one waitress process). A multi-instance deployment should move
this to a shared store or rely on the company identity provider.
"""
from __future__ import annotations

import threading
import time
from collections import deque

MAX_KEYS = 50_000


class LoginThrottle:
    def __init__(self, max_failures: int, window_seconds: int, max_failures_per_ip: int | None = None):
        self.max_failures = max_failures
        self.max_failures_per_ip = max_failures_per_ip or max_failures * 4
        self.window = window_seconds
        self._failures: dict[tuple, deque] = {}
        self._lock = threading.Lock()

    def _count(self, key, now: float) -> int:
        q = self._failures.get(key)
        if q is None:
            return 0
        while q and now - q[0] > self.window:
            q.popleft()
        if not q:
            del self._failures[key]
            return 0
        return len(q)

    def _sweep(self, now: float) -> None:
        for key in list(self._failures):
            self._count(key, now)
        while len(self._failures) >= MAX_KEYS:  # still full after expiry: drop the oldest entries
            oldest = min(self._failures, key=lambda k: self._failures[k][-1])
            del self._failures[oldest]

    def is_blocked(self, ip: str, username: str) -> bool:
        now = time.monotonic()
        with self._lock:
            return (self._count((ip, username.lower()), now) >= self.max_failures
                    or self._count((ip,), now) >= self.max_failures_per_ip)

    def begin(self, ip: str, username: str) -> float | None:
        """Check and count an attempt in one step (under the lock), so requests already in flight cannot all pass a
        check made before any of them is recorded. The attempt counts as a failure until succeeded() takes it back.
        Returns a token for succeeded(), or None when blocked."""
        now = time.monotonic()
        with self._lock:
            if (self._count((ip, username.lower()), now) >= self.max_failures
                    or self._count((ip,), now) >= self.max_failures_per_ip):
                return None
            if len(self._failures) >= MAX_KEYS:
                self._sweep(now)
            for key in ((ip, username.lower()), (ip,)):
                self._failures.setdefault(key, deque()).append(now)
            return now

    def succeeded(self, ip: str, username: str, token: float) -> None:
        """A sign-in begun with begin() worked: clear the account's failures and take back its counted attempt."""
        with self._lock:
            self._failures.pop((ip, username.lower()), None)
            q = self._failures.get((ip,))
            if q is not None:
                try:
                    q.remove(token)
                except ValueError:
                    pass
                if not q:
                    del self._failures[(ip,)]

    def cancel(self, ip: str, username: str, token: float) -> None:
        """A sign-in begun with begin() could not be checked at all (the company directory did not answer): take back
        only its counted attempt, so an outage does not lock people out. Earlier failures stay counted."""
        with self._lock:
            for key in ((ip, username.lower()), (ip,)):
                q = self._failures.get(key)
                if q is None:
                    continue
                try:
                    q.remove(token)
                except ValueError:
                    pass
                if not q:
                    del self._failures[key]

    def record_failure(self, ip: str, username: str) -> None:
        now = time.monotonic()
        with self._lock:
            if len(self._failures) >= MAX_KEYS:
                self._sweep(now)
            for key in ((ip, username.lower()), (ip,)):
                self._failures.setdefault(key, deque()).append(now)

    def reset(self, ip: str, username: str) -> None:
        with self._lock:
            self._failures.pop((ip, username.lower()), None)

    def clear(self) -> None:
        with self._lock:
            self._failures.clear()

    def __len__(self) -> int:
        return len(self._failures)
