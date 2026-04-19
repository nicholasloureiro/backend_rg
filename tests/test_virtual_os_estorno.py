"""
BDD tests for manual estorno launch via Financeiro — item #5.

Given an admin launches a manual payment with tipo="estorno"
When the virtual OS create endpoint is called
Then a payment_details entry with tipo="estorno" is stored
And advance_payment is negative (money going OUT)
"""
from datetime import date
from decimal import Decimal

import pytest

from service_control.models import ServiceOrder


@pytest.mark.django_db
class TestVirtualOSEstorno:
    def test_create_virtual_os_with_estorno(self, admin_client):
        """
        Given the admin wants to record a R$100 estorno
        When POST /service-orders/virtual/ is called with an estorno payload
        Then an OS is created with payment_details containing a tipo="estorno" entry
        And the Financeiro endpoint reflects the negative R$100
        """
        payload = {
            "client_name": "CLIENTE TESTE",
            "total_value": 0,
            "estorno": {"amount": 100.0, "forma_pagamento": "PIX"},
            "observations": "estorno manual",
        }
        response = admin_client.post(
            "/api/v1/service-orders/virtual/",
            payload,
            format="json",
        )
        assert response.status_code == 201, response.content

        os_id = response.json()["service_order_id"]
        os = ServiceOrder.objects.get(id=os_id)
        assert os.is_virtual is True

        estorno_entries = [
            e for e in (os.payment_details or []) if e.get("tipo") == "estorno"
        ]
        assert len(estorno_entries) == 1
        assert estorno_entries[0]["amount"] == 100.0
        assert estorno_entries[0]["forma_pagamento"] == "PIX"

        # advance_payment should be NEGATIVE so it subtracts from finance totals
        assert os.advance_payment == Decimal("-100.00")

    def test_estorno_shows_as_negative_in_financeiro(self, admin_client):
        """
        Given an estorno virtual OS was created today
        When Financeiro is queried for today
        Then total_amount is negative (or the estorno transaction shows as negative)
        """
        payload = {
            "client_name": "CLIENTE TESTE",
            "total_value": 0,
            "estorno": {"amount": 50.0, "forma_pagamento": "PIX"},
        }
        admin_client.post("/api/v1/service-orders/virtual/", payload, format="json")

        today = str(date.today())
        response = admin_client.get(
            f"/api/v1/service-orders/finance/?start_date={today}&end_date={today}"
        )
        assert response.status_code == 200
        body = response.json()
        estorno_txs = [
            t for t in body.get("transactions", []) if t.get("transaction_type") == "estorno"
        ]
        assert len(estorno_txs) >= 1
        assert float(estorno_txs[0]["amount"]) == -50.0
