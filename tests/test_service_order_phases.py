"""
Tests for service order phase transitions (see ADR-0003).
"""
import pytest

from accounts.models import PersonType, Person
from service_control.models import ServiceOrder, ServiceOrderPhase


@pytest.mark.django_db
class TestPhaseTransitions:
    @pytest.fixture
    def pending_order(self, attendant_user, client_person):
        phase, _ = ServiceOrderPhase.objects.get_or_create(name="PENDENTE")
        return ServiceOrder.objects.create(
            renter=client_person,
            employee=attendant_user,
            attendant=attendant_user,
            order_date="2026-04-19",
            service_order_phase=phase,
            total_value=500,
            service_type="Aluguel",
        )

    def test_refuse_requires_reason(self, admin_client, pending_order):
        response = admin_client.post(
            f"/api/v1/service-orders/{pending_order.id}/refuse/",
            {},
            format="json",
        )
        # Should fail without a reason
        assert response.status_code in (400, 422)

    def test_change_phase_admin_only(self, attendant_client, pending_order):
        """Non-admins cannot change phase arbitrarily."""
        response = attendant_client.post(
            f"/api/v1/service-orders/{pending_order.id}/change-phase/",
            {"target_phase": "EM_PRODUCAO"},
            format="json",
        )
        assert response.status_code == 403

    def test_sale_order_goes_to_finalizado_on_mark_retrieved(self, admin_client):
        """TODO: create a Venda OS in AGUARDANDO_RETIRADA, call mark-retrieved,
        verify phase becomes FINALIZADO (not AGUARDANDO_DEVOLUCAO)."""
        pytest.skip("scaffold — fixture setup needed")
