"""
BDD tests for cancelamento preserving caixa — item #12.

Given an OS with payment_details (cash already collected)
When the OS is RECUSADA (cancelled)
Then the Financeiro endpoint still shows those payments (caixa preserved)
But total_vendido excludes the RECUSADA OS (it's not a sale anymore)
"""
from datetime import date
from decimal import Decimal

import pytest

from service_control.models import ServiceOrder, ServiceOrderPhase


@pytest.fixture
def refused_with_payment(db, client_person, admin_user):
    recusada, _ = ServiceOrderPhase.objects.get_or_create(name="RECUSADA")
    return ServiceOrder.objects.create(
        renter=client_person,
        employee=admin_user,
        attendant=admin_user,
        order_date=date.today(),
        service_order_phase=recusada,
        total_value=Decimal("400.00"),
        advance_payment=Decimal("200.00"),
        service_type="Aluguel",
        payment_details=[
            {
                "amount": 200.0,
                "forma_pagamento": "PIX",
                "tipo": "sinal",
                "data": f"{date.today()}T10:00:00",
            }
        ],
        payment_method="PIX",
        justification_refusal="cliente desistiu",
    )


@pytest.mark.django_db
class TestCancelamentoPreservesCaixa:
    def test_finance_endpoint_still_shows_recusada_payments(
        self, admin_client, refused_with_payment
    ):
        """
        Given a RECUSADA OS with R$200 sinal
        When Financeiro is queried
        Then total_amount/total_recebido includes the R$200
        """
        today = str(date.today())
        response = admin_client.get(
            f"/api/v1/service-orders/finance/?start_date={today}&end_date={today}"
        )
        assert response.status_code == 200
        body = response.json()
        # The R$200 sinal should be present in the transactions list
        all_amounts = [float(t["amount"]) for t in body.get("transactions", [])]
        assert 200.0 in all_amounts, (
            f"RECUSADA payment not preserved in Financeiro. Got: {all_amounts}"
        )

    def test_planilha_excludes_recusada_from_total_vendido(
        self, admin_client, refused_with_payment
    ):
        """
        Given the same RECUSADA OS
        When Planilha is queried
        Then total_vendido does NOT include the R$400 total_value
        (RECUSADA is no longer a sale)
        """
        today = str(date.today())
        response = admin_client.get(
            f"/api/v1/service-orders/planilha/?start_date={today}&end_date={today}"
        )
        assert response.status_code == 200
        body = response.json()
        totals = body.get("totals", {})
        assert float(totals.get("total_vendido", 0)) == 0.0, (
            f"RECUSADA OS should not count in total_vendido: {totals}"
        )
