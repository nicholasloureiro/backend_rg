"""BDD tests for the per-entry payment management endpoints.

Covers the OS 2428 scenario: a wrong payment was posted to an OS and the user
needs to delete or correct it without losing audit trail or drifting OS totals.

Endpoints:
    DELETE /service-orders/{id}/payments/{entry_id}/   — remove one entry
    PATCH  /service-orders/{id}/payments/{entry_id}/   — edit one entry
    POST   /service-orders/{id}/add-payment/           — accepts optional `data`
    POST   /service-orders/{id}/refund/                — accepts optional `data`
"""
from datetime import date
from decimal import Decimal

import pytest

from service_control.models import ServiceOrder, ServiceOrderPhase


@pytest.fixture
def os_with_two_payments(db, client_person, attendant_user):
    """OS mirroring the OS 2428 shape: a wrong parcial + a corrected sinal."""
    phase, _ = ServiceOrderPhase.objects.get_or_create(name="EM_PRODUCAO")
    return ServiceOrder.objects.create(
        renter=client_person,
        employee=attendant_user,
        attendant=attendant_user,
        order_date=date(2026, 4, 13),
        service_order_phase=phase,
        total_value=Decimal("680.00"),
        advance_payment=Decimal("590.00"),
        service_type="Aluguel",
        payment_details=[
            {
                "id": "11111111-1111-1111-1111-111111111111",
                "amount": 5900.0,
                "forma_pagamento": "DEBITO",
                "tipo": "parcial",
                "data": "2026-04-30T21:34:06+00:00",
            },
            {
                "id": "22222222-2222-2222-2222-222222222222",
                "amount": 590.0,
                "forma_pagamento": "DEBITO",
                "tipo": "sinal",
                "data": "2026-05-02T12:53:32+00:00",
            },
        ],
        payment_method="DEBITO",
    )


@pytest.mark.django_db
class TestDeletePaymentEntry:
    def test_admin_can_delete_wrong_entry(self, admin_client, os_with_two_payments):
        """Deleting the wrong 5900 leaves only the 590 and recomputes advance_payment."""
        response = admin_client.delete(
            f"/api/v1/service-orders/{os_with_two_payments.id}/payments/11111111-1111-1111-1111-111111111111/"
        )
        assert response.status_code == 200, response.content
        os_with_two_payments.refresh_from_db()
        details = os_with_two_payments.payment_details
        assert len(details) == 1
        assert details[0]["amount"] == 590.0
        assert os_with_two_payments.advance_payment == Decimal("590.00")

    def test_unknown_entry_returns_404(self, admin_client, os_with_two_payments):
        response = admin_client.delete(
            f"/api/v1/service-orders/{os_with_two_payments.id}/payments/00000000-0000-0000-0000-000000000000/"
        )
        assert response.status_code == 404

    def test_attendant_blocked(self, attendant_client, os_with_two_payments):
        response = attendant_client.delete(
            f"/api/v1/service-orders/{os_with_two_payments.id}/payments/11111111-1111-1111-1111-111111111111/"
        )
        assert response.status_code == 403


@pytest.mark.django_db
class TestPatchPaymentEntry:
    def test_admin_can_edit_amount_and_date(self, admin_client, os_with_two_payments):
        response = admin_client.patch(
            f"/api/v1/service-orders/{os_with_two_payments.id}/payments/11111111-1111-1111-1111-111111111111/",
            {"amount": 590.0, "data": "2026-04-30"},
            format="json",
        )
        assert response.status_code == 200, response.content
        os_with_two_payments.refresh_from_db()
        wrong = next(
            e for e in os_with_two_payments.payment_details
            if e["id"] == "11111111-1111-1111-1111-111111111111"
        )
        assert wrong["amount"] == 590.0
        assert wrong["data"].startswith("2026-04-30")
        # 590 (now-corrected) + 590 (original sinal) = 1180
        assert os_with_two_payments.advance_payment == Decimal("1180.00")

    def test_invalid_amount_rejected(self, admin_client, os_with_two_payments):
        response = admin_client.patch(
            f"/api/v1/service-orders/{os_with_two_payments.id}/payments/11111111-1111-1111-1111-111111111111/",
            {"amount": -50},
            format="json",
        )
        assert response.status_code == 400


@pytest.mark.django_db
class TestAddPaymentChosenDate:
    def test_payment_lands_on_user_supplied_date(
        self, admin_client, os_with_two_payments
    ):
        response = admin_client.post(
            f"/api/v1/service-orders/{os_with_two_payments.id}/add-payment/",
            {"payments": [{"amount": 90, "forma_pagamento": "PIX", "data": "2026-04-15"}]},
            format="json",
        )
        assert response.status_code == 200, response.content
        os_with_two_payments.refresh_from_db()
        new_entry = os_with_two_payments.payment_details[-1]
        assert new_entry["amount"] == 90.0
        assert new_entry["data"].startswith("2026-04-15")
        assert "id" in new_entry  # stable UUID injected

    def test_payment_without_date_defaults_to_now(
        self, admin_client, os_with_two_payments
    ):
        response = admin_client.post(
            f"/api/v1/service-orders/{os_with_two_payments.id}/add-payment/",
            {"payments": [{"amount": 10, "forma_pagamento": "PIX"}]},
            format="json",
        )
        assert response.status_code == 200
        os_with_two_payments.refresh_from_db()
        new_entry = os_with_two_payments.payment_details[-1]
        # Today's date — not the order_date or any old timestamp
        assert new_entry["data"].startswith(str(date.today()))


@pytest.mark.django_db
class TestRefundChosenDate:
    def test_refund_with_user_chosen_date(self, admin_client, os_with_two_payments):
        response = admin_client.post(
            f"/api/v1/service-orders/{os_with_two_payments.id}/refund/",
            {"amount": 50, "forma_pagamento": "PIX", "data": "2026-04-20", "motivo": "teste"},
            format="json",
        )
        assert response.status_code == 200, response.content
        os_with_two_payments.refresh_from_db()
        estornos = [
            e for e in os_with_two_payments.payment_details if e.get("tipo") == "estorno"
        ]
        assert len(estornos) == 1
        assert estornos[0]["data"].startswith("2026-04-20")
        assert estornos[0].get("motivo") == "teste"
