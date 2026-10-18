"""Integration-test fixtures (IRA-55).

The gateway tests in this directory predate accounts (IRA-32). They get the same signed-in admin,
in-memory identity store and in-memory projects as the unit suite, rather than a bare TestClient that
the auth gate answers with 403. Tests that need the real Postgres identity store
(`test_identity_postgres.py`) build their own store and are unaffected.
"""

from tests.unit.conftest import _in_memory_projects, identity  # noqa: F401
