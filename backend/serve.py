"""Production server: waitress, behind the HTTPS reverse proxy (nginx in deployment/, or the company's own).

    python serve.py                      (from the backend/ folder; the Docker image runs exactly this)

Settings (environment variables):
  APP_LISTEN    host:port to listen on; default 127.0.0.1:8080 (the container sets 0.0.0.0:8080)
  APP_THREADS   worker threads; default 8. Keep ORACLE_POOL_MAX at least this high (one connection per busy thread).

One process on purpose: the sign-in throttle (security/rate_limit.py) counts failures in memory, so several
processes would each allow the full number of attempts.

Behind a proxy (TRUSTED_PROXY_COUNT > 0) the X-Forwarded-* headers must reach the app, where ProxyFix trusts exactly
that many hops. waitress removes those headers by default (it does not know the proxy), which would make every
request look as if it came from the proxy: one shared address for the whole sign-in throttle. So the removal is
switched off then, and left on otherwise (nothing in front: the headers come from the browser and are dropped).
"""
from __future__ import annotations

import os
import re
import sys

_LISTEN_RE = re.compile(r"[A-Za-z0-9.\-]+:[0-9]{1,5}|\[[0-9A-Fa-f:]+\]:[0-9]{1,5}")


def server_options(env=None) -> dict:
    """waitress.serve() keyword arguments from the environment. Raises ValueError with the variable's name."""
    env = os.environ if env is None else env
    listen = (env.get("APP_LISTEN") or "127.0.0.1:8080").strip()
    if not _LISTEN_RE.fullmatch(listen):
        raise ValueError(f"APP_LISTEN must be host:port, e.g. 0.0.0.0:8080; got {listen!r}")
    threads_raw = (env.get("APP_THREADS") or "8").strip()
    if not threads_raw.isdigit() or not 1 <= int(threads_raw) <= 64:
        raise ValueError(f"APP_THREADS must be a whole number from 1 to 64; got {threads_raw!r}")
    proxies_raw = (env.get("TRUSTED_PROXY_COUNT") or "0").strip()
    if not proxies_raw.isdigit():
        raise ValueError(f"TRUSTED_PROXY_COUNT must be a whole number; got {proxies_raw!r}")
    return dict(
        listen=listen,
        threads=int(threads_raw),
        ident="",                       # no "Server: waitress" header
        channel_timeout=300,            # an idle connection is closed after 5 minutes
        clear_untrusted_proxy_headers=int(proxies_raw) == 0,
    )


def main() -> None:
    try:
        options = server_options()
    except ValueError as exc:
        sys.exit(f"Configuration error: {exc}")
    from waitress import serve

    from wsgi import app  # exits with one clear line on a configuration or schema problem

    print(f"Capability Portfolio Command listening on {options['listen']} ({options['threads']} threads)", flush=True)
    serve(app, **options)


if __name__ == "__main__":
    main()
