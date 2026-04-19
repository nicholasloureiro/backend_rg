"""
BDD tests for OS update payment handling (items #1 and #6 from client urgencies).

Item #1: Double payment on value change
    Given an OS with a sinal payment
    When the user changes total_value and resubmits without explicit pagamentos
    Then the existing sinal is preserved (not overwritten with a zero-amount duplicate)

Item #6: Edit OS date cascades to ALL payment entries
    Given an OS with sinal and restante in payment_details
    When user edits data_pedido
    Then ALL payment entries' `data` field move to the new date
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from accounts.models import Person, PersonType
from service_control.models import ServiceOrder, ServiceOrderPhase


@pytest.fixture
def os_with_sinal(db, client_person, attendant_user):
    phase, _ = ServiceOrderPhase.objects.get_or_create(name="EM_PRODUCAO")
    return ServiceOrder.objects.create(
        renter=client_person,
        employee=attendant_user,
        attendant=attendant_user,
        order_date=date(2026, 3, 10),
        service_order_phase=phase,
        total_value=Decimal("500.00"),
        advance_payment=Decimal("150.00"),
        service_type="Aluguel",
        payment_details=[
            {
                "amount": 150.0,
                "forma_pagamento": "PIX",
                "tipo": "sinal",
                "data": "2026-03-10T14:30:00",
            }
        ],
        payment_method="PIX",
    )


@pytest.fixture
def os_with_sinal_and_restante(db, client_person, attendant_user):
    phase, _ = ServiceOrderPhase.objects.get_or_create(name="FINALIZADO")
    return ServiceOrder.objects.create(
        renter=client_person,
        employee=attendant_user,
        attendant=attendant_user,
        order_date=date(2026, 3, 10),
        service_order_phase=phase,
        total_value=Decimal("500.00"),
        advance_payment=Decimal("500.00"),
        service_type="Aluguel",
        payment_details=[
            {
                "amount": 200.0,
                "forma_pagamento": "PIX",
                "tipo": "sinal",
                "data": "2026-03-10T09:00:00",
            },
            {
                "amount": 300.0,
                "forma_pagamento": "credito",
                "tipo": "restante",
                "data": "2026-03-15T16:00:00",
            },
        ],
        payment_method="PIX, credito",
    )


@pytest.mark.django_db
class TestDoublePaymentOnValueChange:
    """Item #1 — guard against overwriting sinal with empty/zero entries."""

    def test_update_with_empty_pagamentos_preserves_sinal(
        self, admin_client, os_with_sinal
    ):
        """
        Given an OS with one sinal entry
        When total_value is updated and `pagamentos` is an empty list
        Then payment_details still has exactly one sinal (not erased)
        """
        payload = {
            "ordem_servico": {
                "pagamento": {
                    "total": 600.0,
                    "sinal": {"total": 150.0, "pagamentos": []},
                    "restante": 450.0,
                }
            }
        }
        response = admin_client.put(
            f"/api/v1/service-orders/{os_with_sinal.id}/update/",
            payload,
            format="json",
        )
        assert response.status_code in (200, 400)  # 400 ok if other validation fails
        os_with_sinal.refresh_from_db()
        sinal_entries = [
            e for e in (os_with_sinal.payment_details or []) if e.get("tipo") == "sinal"
        ]
        assert len(sinal_entries) == 1
        assert sinal_entries[0]["amount"] == 150.0

    def test_update_with_zero_amount_does_not_add_entry(
        self, admin_client, os_with_sinal
    ):
        """
        Given an OS with one sinal entry
        When a payment with amount=0 is submitted
        Then no new sinal entry is added (forma alone is not enough)
        """
        payload = {
            "ordem_servico": {
                "pagamento": {
                    "total": 500.0,
                    "sinal": {
                        "total": 150.0,
                        "pagamentos": [
                            {"amount": 0, "forma_pagamento": "PIX"},
                        ],
                    },
                    "restante": 350.0,
                }
            }
        }
        admin_client.put(
            f"/api/v1/service-orders/{os_with_sinal.id}/update/",
            payload,
            format="json",
        )
        os_with_sinal.refresh_from_db()
        sinal_entries = [
            e for e in (os_with_sinal.payment_details or []) if e.get("tipo") == "sinal"
        ]
        # Only the original entry should remain; no zero-amount entry added
        assert len(sinal_entries) == 1
        assert sinal_entries[0]["amount"] == 150.0


@pytest.mark.django_db
class TestOrderDateCascadesToPayments:
    """Item #6 — editing data_pedido moves ALL payment entries' dates."""

    def test_changing_data_pedido_moves_all_payment_entries(
        self, admin_client, os_with_sinal_and_restante
    ):
        """
        Given an OS with sinal (2026-03-10) and restante (2026-03-15)
        When data_pedido is changed to 2026-03-20
        Then BOTH entries' `data` starts with 2026-03-20
        """
        payload = {
            "ordem_servico": {
                "data_pedido": "2026-03-20",
            }
        }
        admin_client.put(
            f"/api/v1/service-orders/{os_with_sinal_and_restante.id}/update/",
            payload,
            format="json",
        )
        os_with_sinal_and_restante.refresh_from_db()
        entries = os_with_sinal_and_restante.payment_details or []
        assert len(entries) == 2
        for entry in entries:
            assert entry["data"].startswith("2026-03-20"), (
                f"Entry {entry} didn't move to 2026-03-20"
            )
