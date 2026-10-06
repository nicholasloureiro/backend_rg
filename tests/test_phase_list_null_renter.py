"""
Regression: OS sem renter (cliente excluído -> SET_NULL) quebrava a listagem por fase
com 500 "'NoneType' object has no attribute 'id'".

Given an EM_PRODUCAO OS whose renter is NULL
When the phase listings (V1/V2) and the OS detail are requested
Then they return 200 and the client falls back to client_name
"""
from datetime import date
from decimal import Decimal

import pytest

from service_control.models import ServiceOrder, ServiceOrderPhase


@pytest.fixture
def orphan_order(db, admin_user):
    producao, _ = ServiceOrderPhase.objects.get_or_create(name="EM_PRODUCAO")
    return ServiceOrder.objects.create(
        renter=None,
        client_name="CLIENTE EXCLUIDO",
        employee=admin_user,
        attendant=admin_user,
        order_date=date(2026, 3, 1),
        service_order_phase=producao,
        total_value=Decimal("300.00"),
        service_type="Aluguel",
    )


@pytest.fixture
def regular_order(db, admin_user, client_person):
    producao, _ = ServiceOrderPhase.objects.get_or_create(name="EM_PRODUCAO")
    return ServiceOrder.objects.create(
        renter=client_person,
        employee=admin_user,
        attendant=admin_user,
        order_date=date(2026, 3, 2),
        service_order_phase=producao,
        total_value=Decimal("300.00"),
        service_type="Aluguel",
    )


def _client_by_order_id(results, order_id):
    return next(o["client"] for o in results if o["id"] == order_id)


class TestPhaseListNullRenter:
    def test_v2_lists_order_without_renter(self, admin_client, orphan_order, regular_order):
        resp = admin_client.get(
            "/api/v1/service-orders/v2/phase/EM_PRODUCAO/?page=1&page_size=20&ordering=-id"
        )
        assert resp.status_code == 200, resp.data
        assert resp.data["count"] == 2

        orphan = _client_by_order_id(resp.data["results"], orphan_order.id)
        assert orphan["id"] is None
        assert orphan["name"] == "CLIENTE EXCLUIDO"
        assert orphan["contacts"] == []
        assert orphan["addresses"] == []

        regular = _client_by_order_id(resp.data["results"], regular_order.id)
        assert regular["id"] == regular_order.renter.id
        assert regular["name"] == "CLIENTE TESTE"

    def test_v1_lists_order_without_renter(self, admin_client, orphan_order):
        resp = admin_client.get("/api/v1/service-orders/phase/EM_PRODUCAO/")
        assert resp.status_code == 200, resp.data

    def test_detail_of_order_without_renter(self, admin_client, orphan_order):
        resp = admin_client.get(f"/api/v1/service-orders/{orphan_order.id}/")
        assert resp.status_code == 200, resp.data
