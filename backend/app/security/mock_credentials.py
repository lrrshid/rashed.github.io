"""MOCK CREDENTIALS: a temporary stand-in until real password handling is built.

`MOCK_PASSWORD` is committed to the repository, so it is public. It is the password of every seeded mock account
and of any user an ADMIN creates without typing one (demo and test profiles only; on Oracle the password is
required). Before a real deployment: remove the mock accounts, drop this module and issue passwords properly
(for example a one-time password shown to the admin once, plus a "change my password" screen).
"""
MOCK_PASSWORD = "Mock-Pass-123"
