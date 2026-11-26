"""Settings > connections (ported from the Asset Availability project's Settings tab).

registry.py           the providers Settings knows (fields, secrets)
ldap_provider.py      the company directory: validation, the settings it produces, its staged tests
database_provider.py  the main database: staged for a planned restart, read-only tests, a clean start (no demo data)
config_service.py     the one place the running app reads the managed settings from (the effective Settings)
connection_service.py connections, drafts, tests, apply, the sign-in method, certificates, destinations, history
egress.py / certs.py  where the server may connect to; the trusted CA certificates
"""
