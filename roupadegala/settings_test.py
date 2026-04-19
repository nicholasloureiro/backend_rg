"""
Test-only Django settings. Overrides DATABASES to use in-memory SQLite
so the test suite doesn't need a running PostgreSQL.

Referenced from pytest.ini via DJANGO_SETTINGS_MODULE.
"""
from roupadegala.settings import *  # noqa: F401, F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Skip migrations entirely — create schema from models directly.
# Our data-loading migrations use Postgres-specific SQL (public.city) that
# SQLite can't handle. Tests seed data via fixtures instead.
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

# Speed up tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Silence logging during tests
import logging

logging.disable(logging.CRITICAL)
