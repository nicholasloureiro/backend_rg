"""
BDD tests for resgate (RECUSADA -> PENDENTE) behavior — item #2.

Given a RECUSADA OS with an old order_date
When admin returns it to PENDENTE
Then order_date becomes today AND data_resgate is set AND sinal entries' `data` updated
So that Dashboard (which filters by order_date) counts the resgate as a sale on today.
"""
from datetime import date
from decimal import Decimal

import pytest

from service_control.models import ServiceOrder, ServiceOrderPhase


@pytest.fixture
def refused_order(db, client_person, admin_user):
    recusada, _ = ServiceOrderPhase.objects.get_or_create(name="RECUSADA")
    return ServiceOrder.objects.create(
        renter=client_person,
        employee=admin_user,
        attendant=admin_user,
        order_date=date(2026, 3, 10),
        service_order_phase=recusada,
        total_value=Decimal("500.00"),
        advance_payment=Decimal("200.00"),
        service_type="Aluguel",
        payment_details=[
            {
                "amount": 200.0,
                "forma_pagamento": "PIX",
                "tipo": "sinal",
                "data": "2026-03-10T14:30:00",
            }
        ],
        payment_method="PIX",
        justification_refusal="cliente desistiu",
    )


@pytest.mark.django_db
class TestResgate:
    def test_resgate_updates_order_date_and_sinal_dates(
        self, admin_client, refused_order
    ):
        """
        Given RECUSADA OS from 2026-03-10
        When admin calls return-to-pending today
        Then:
          - order_date = today
          - data_resgate = today
          - sinal payment_details entries have `data` starting with today
        """
        response = admin_client.post(
            f"/api/v1/service-orders/{refused_order.id}/return-to-pending/"
        )
        assert response.status_code == 200

        refused_order.refresh_from_db()
        today = date.today()
        assert refused_order.order_date == today, (
            f"order_date not updated (got {refused_order.order_date})"
        )
        assert refused_order.data_resgate == today
        for entry in refused_order.payment_details or []:
            if entry.get("tipo") == "sinal":
                assert entry["data"].startswith(str(today)), (
                    f"sinal entry didn't move to today: {entry}"
                )

    def test_non_recusada_return_to_pending_does_not_change_order_date(
        self, admin_client, db, client_person, admin_user
    ):
        """
        Given a PRODUCAO OS (never refused)
        When return-to-pending is called
        Then order_date stays unchanged (no resgate semantics)
        """
        producao, _ = ServiceOrderPhase.objects.get_or_create(name="EM_PRODUCAO")
        original_date = date(2026, 3, 1)
        os = ServiceOrder.objects.create(
            renter=client_person,
            employee=admin_user,
            attendant=admin_user,
            order_date=original_date,
            service_order_phase=producao,
            total_value=Decimal("300.00"),
            service_type="Aluguel",
        )
        admin_client.post(f"/api/v1/service-orders/{os.id}/return-to-pending/")
        os.refresh_from_db()
        assert os.order_date == original_date
        assert os.data_resgate is None
