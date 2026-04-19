"""
BDD tests for Venda auto-finalize timestamps — item #10.

Given a Venda OS transitions automatically to FINALIZADO on items update
When it's saved
Then data_finalizado is set (today) but data_retirado/data_devolvido are NOT
(they were being set to timezone.now() erroneously, even though the product was
never actually retrieved/returned).
"""
from datetime import date
from decimal import Decimal

import pytest

from accounts.models import Person, PersonType
from service_control.models import ServiceOrder, ServiceOrderPhase


@pytest.fixture
def pending_venda(db, client_person, admin_user):
    pendente, _ = ServiceOrderPhase.objects.get_or_create(name="PENDENTE")
    return ServiceOrder.objects.create(
        renter=client_person,
        employee=admin_user,
        attendant=admin_user,
        order_date=date.today(),
        service_order_phase=pendente,
        total_value=Decimal("300.00"),
        service_type="Venda",
        purchase=True,
    )


@pytest.mark.django_db
class TestVendaAutoFinalize:
    def test_venda_auto_finalize_does_not_set_retirada_or_devolucao(
        self, admin_client, pending_venda
    ):
        """
        Given a PENDENTE Venda OS
        When the update endpoint is called with items (triggering auto-FINALIZADO)
        Then data_finalizado = today, but data_retirado and data_devolvido are NOT set.
        """
        payload = {
            "ordem_servico": {
                "modalidade": "Venda",
                "itens": [
                    {
                        "tipo": "paleto",
                        "numero": "38",
                        "cor": "preto",
                        "marca": "",
                        "venda": True,
                    }
                ],
                "pagamento": {
                    "total": 300.0,
                    "sinal": {
                        "total": 300.0,
                        "pagamentos": [{"amount": 300.0, "forma_pagamento": "PIX"}],
                    },
                    "restante": 0.0,
                },
            },
            "cliente": {
                "nome": "CLIENTE TESTE",
                "cpf": "52998224725",
                "is_infant": False,
            },
        }
        response = admin_client.put(
            f"/api/v1/service-orders/{pending_venda.id}/update/",
            payload,
            format="json",
        )
        assert response.status_code == 200, response.content

        pending_venda.refresh_from_db()
        assert pending_venda.service_order_phase.name == "FINALIZADO"
        assert pending_venda.data_finalizado == date.today()
        # These must NOT be auto-populated — the product was never retrieved/returned
        assert pending_venda.data_retirado is None, (
            f"data_retirado should be None on auto-FINALIZADO Venda, got {pending_venda.data_retirado}"
        )
        assert pending_venda.data_devolvido is None, (
            f"data_devolvido should be None on auto-FINALIZADO Venda, got {pending_venda.data_devolvido}"
        )
