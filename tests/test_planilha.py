"""
Tests for the Planilha endpoint — verifies payment-centric row generation
and totalizer calculations (see ADR-0006).

These are scaffolds. Each test should populate fixture orders with
payment_details and assert the response shape matches expectations.
"""
import pytest


@pytest.mark.django_db
class TestPlanilhaEndpoint:
    def test_requires_authentication(self, api_client):
        response = api_client.get("/api/v1/service-orders/planilha/")
        assert response.status_code == 401

    def test_returns_expected_shape(self, admin_client):
        response = admin_client.get("/api/v1/service-orders/planilha/")
        assert response.status_code == 200
        body = response.json()
        assert "results" in body
        assert "totals" in body
        assert "available_filters" in body
        assert set(body["totals"].keys()) >= {
            "total_os",
            "total_fechadas",
            "taxa_conversao",
            "total_recebido",
            "total_vendido",
        }

    def test_date_filter_applies_to_payment_date(self, admin_client):
        """TODO: create an OS from 23/03 with a restante payment on 25/03,
        filter for 25/03, verify the restante row is in results but not the
        sinal row (from 23/03)."""
        pytest.skip("scaffold — fixture creation needed")

    def test_total_vendido_only_counts_sinal_rows(self, admin_client):
        """TODO: create OS X (total=R$270) on 23/03 with sinal on 23/03 and
        restante on 25/03. Filter for 25/03. total_vendido must be R$0."""
        pytest.skip("scaffold — fixture creation needed")

    def test_pendente_os_appears_with_fechamento_empty(self, admin_client):
        """TODO: create PENDENTE OS today. Filter for today. Verify
        fechamento=='' (not 'SIM' or 'NÃO')."""
        pytest.skip("scaffold — fixture creation needed")

    def test_estorno_entries_are_negative(self, admin_client):
        """TODO: create OS with an estorno payment_details entry. Verify the
        planilha row has a negative valor."""
        pytest.skip("scaffold — fixture creation needed")
