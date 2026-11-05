"""
Exclusão de OS pela aba Recusadas.

Dado uma OS RECUSADA
Quando um administrador a exclui
Então a OS e os itens somem e ela sai da listagem da fase
Mas um atendente não consegue excluir
"""
from datetime import date
from decimal import Decimal

import pytest

from service_control.models import ServiceOrder, ServiceOrderItem, ServiceOrderPhase


@pytest.fixture
def os_recusada_zerada(db, admin_user, client_person):
    recusada, _ = ServiceOrderPhase.objects.get_or_create(name="RECUSADA")
    os_recusada = ServiceOrder.objects.create(
        renter=client_person,
        employee=admin_user,
        attendant=admin_user,
        order_date=date(2026, 10, 24),
        service_order_phase=recusada,
        total_value=Decimal("0.00"),
        advance_payment=Decimal("0.00"),
        service_type="Aluguel",
        justification_refusal="Cliente não retirou o produto",
    )
    ServiceOrderItem.objects.create(service_order=os_recusada)
    return os_recusada


@pytest.mark.django_db
class TestExcluirOsRecusada:
    def test_admin_exclui_os_e_itens(self, admin_client, os_recusada_zerada):
        os_id = os_recusada_zerada.id

        resp = admin_client.delete(f"/api/v1/service-orders/{os_id}/")

        assert resp.status_code == 200, resp.data
        assert not ServiceOrder.objects.filter(id=os_id).exists()
        assert not ServiceOrderItem.objects.filter(service_order_id=os_id).exists()

    def test_atendente_nao_exclui(self, attendant_client, os_recusada_zerada):
        os_id = os_recusada_zerada.id

        resp = attendant_client.delete(f"/api/v1/service-orders/{os_id}/")

        assert resp.status_code == 403
        assert ServiceOrder.objects.filter(id=os_id).exists()

    def test_os_excluida_sai_da_listagem_da_fase(self, admin_client, os_recusada_zerada):
        url = "/api/v1/service-orders/v2/phase/RECUSADA/?page=1&page_size=20&ordering=-id"
        assert admin_client.get(url).data["count"] == 1

        admin_client.delete(f"/api/v1/service-orders/{os_recusada_zerada.id}/")

        resp = admin_client.get(url)
        assert resp.status_code == 200, resp.data
        assert resp.data["count"] == 0
