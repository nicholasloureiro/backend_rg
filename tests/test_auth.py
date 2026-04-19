"""
Tests for authentication endpoints.
"""
import pytest


@pytest.mark.django_db
class TestLogin:
    def test_login_with_valid_credentials(self, api_client, admin_user):
        response = api_client.post("/api/v1/auth/login/", {
            "username": admin_user.cpf,
            "password": "test123",
        }, format="json")
        assert response.status_code == 200
        body = response.json()
        assert "access" in body or "access_token" in body

    def test_login_with_wrong_password(self, api_client, admin_user):
        response = api_client.post("/api/v1/auth/login/", {
            "username": admin_user.cpf,
            "password": "wrong",
        }, format="json")
        assert response.status_code in (400, 401)

    def test_login_with_nonexistent_user(self, api_client):
        response = api_client.post("/api/v1/auth/login/", {
            "username": "00000000000",
            "password": "whatever",
        }, format="json")
        assert response.status_code in (400, 401)


@pytest.mark.django_db
class TestMeEndpoint:
    def test_me_requires_auth(self, api_client):
        response = api_client.get("/api/v1/auth/me/")
        assert response.status_code == 401

    def test_me_returns_current_user(self, admin_client, admin_user):
        response = admin_client.get("/api/v1/auth/me/")
        assert response.status_code == 200
