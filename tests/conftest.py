"""
Shared pytest fixtures for the roupadegala backend.

Usage:
    pytest                          # run all tests
    pytest tests/test_cpf.py        # a single file
    pytest -k planilha              # keyword filter
    pytest --reuse-db               # skip DB teardown (faster)

Tests run against in-memory SQLite via roupadegala.settings_test.
"""
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Person, PersonType


@pytest.fixture
def api_client():
    """Unauthenticated DRF client."""
    return APIClient()


@pytest.fixture
def admin_user(db):
    """A fully-wired admin Person (User + Person + PersonType=ADMINISTRADOR)."""
    pt, _ = PersonType.objects.get_or_create(type="ADMINISTRADOR")
    user = User.objects.create_user(username="12345678909", password="test123")
    person = Person.objects.create(
        user=user,
        name="ADMIN TEST",
        cpf="12345678909",
        person_type=pt,
    )
    return person


@pytest.fixture
def attendant_user(db):
    """A fully-wired ATENDENTE Person."""
    pt, _ = PersonType.objects.get_or_create(type="ATENDENTE")
    user = User.objects.create_user(username="98765432100", password="test123")
    person = Person.objects.create(
        user=user,
        name="ATENDENTE TEST",
        cpf="98765432100",
        person_type=pt,
    )
    return person


@pytest.fixture
def admin_client(api_client, admin_user):
    """DRF client authenticated as the admin_user fixture."""
    api_client.force_authenticate(user=admin_user.user)
    return api_client


@pytest.fixture
def attendant_client(api_client, attendant_user):
    """DRF client authenticated as the attendant_user fixture."""
    api_client.force_authenticate(user=attendant_user.user)
    return api_client


@pytest.fixture
def client_person(db):
    """A CLIENTE Person (a rental customer)."""
    pt, _ = PersonType.objects.get_or_create(type="CLIENTE")
    return Person.objects.create(
        name="CLIENTE TESTE",
        cpf="52998224725",  # valid CPF
        person_type=pt,
    )
