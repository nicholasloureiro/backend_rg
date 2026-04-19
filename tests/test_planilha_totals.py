"""
BDD tests for Planilha <-> Dashboard total_vendido alignment — item #9.

Given the same date filter is applied to Dashboard and Planilha
When both compute total_vendido
Then they return the same number.
"""
from datetime import date
from decimal import Decimal

import pytest

from service_control.models import ServiceOrder, ServiceOrderPhase


@pytest.fixture
def sample_orders(db, client_person, admin_user):
    """Build a small mix: one FINALIZADO today, one RECUSADA today, one old."""
    finalizado, _ = ServiceOrderPhase.objects.get_or_create(name="FINALIZADO")
    recusada, _ = ServiceOrderPhase.objects.get_or_create(name="RECUSADA")

    today = date.today()
    # Confirmed sale today — counts
    ServiceOrder.objects.create(
        renter=client_person,
        employee=admin_user,
        attendant=admin_user,
        order_date=today,
        service_order_phase=finalizado,
        total_value=Decimal("500.00"),
        advance_payment=Decimal("500.00"),
        service_type="Aluguel",
        payment_details=[
            {"amount": 500.0, "forma_pagamento": "PIX", "tipo": "sinal", "data": f"{today}T10:00:00"}
        ],
    )
    # Refused today — should NOT count in total_vendido
    ServiceOrder.objects.create(
        renter=client_person,
        employee=admin_user,
        attendant=admin_user,
        order_date=today,
        service_order_phase=recusada,
        total_value=Decimal("300.00"),
        advance_payment=Decimal("100.00"),
        service_type="Aluguel",
        payment_details=[
            {"amount": 100.0, "forma_pagamento": "PIX", "tipo": "sinal", "data": f"{today}T11:00:00"}
        ],
    )
    # Old finalized — should NOT count (outside filter)
    ServiceOrder.objects.create(
        renter=client_person,
        employee=admin_user,
        attendant=admin_user,
        order_date=date(2025, 1, 1),
        service_order_phase=finalizado,
        total_value=Decimal("999.00"),
        service_type="Aluguel",
    )
    return today


@pytest.mark.django_db
class TestPlanilhaMatchesDashboard:
    def test_total_vendido_matches_dashboard(self, admin_client, sample_orders):
        """
        Given today's fixtures (1 FINALIZADO R$500, 1 RECUSADA R$300, 1 old R$999)
        When Dashboard and Planilha both filter to today
        Then both total_vendido == R$500 (only the FINALIZADO today)
        """
        today = str(sample_orders)

        dash = admin_client.get(
            f"/api/v1/service-orders/dashboard/?data_inicio={today}&data_fim={today}"
        )
        assert dash.status_code == 200
        dash_vendido = float(dash.json()["data"]["kpis"]["total_vendido"])

        plan = admin_client.get(
            f"/api/v1/service-orders/planilha/?start_date={today}&end_date={today}"
        )
        assert plan.status_code == 200
        plan_vendido = float(plan.json()["totals"]["total_vendido"])

        assert dash_vendido == plan_vendido, (
            f"Dashboard says R${dash_vendido} but Planilha says R${plan_vendido}"
        )
        assert dash_vendido == 500.0
