"""
Characterization test for the ServiceOrder dashboard endpoint.

Pins the EXACT output of /api/v1/service-orders/dashboard/ for a fixed dataset
so that performance refactors can be proven to preserve behaviour byte-for-byte.
"""
from datetime import date
from decimal import Decimal

import pytest

from accounts.models import Person, PersonType
from service_control.models import ServiceOrder, ServiceOrderPhase


@pytest.fixture
def dashboard_data(db, client_person, admin_user, attendant_user):
    """A rich-but-deterministic dataset exercising every dashboard calculation."""
    phases = {}
    for name in [
        "PENDENTE",
        "EM_PRODUCAO",
        "AGUARDANDO_RETIRADA",
        "AGUARDANDO_DEVOLUCAO",
        "FINALIZADO",
        "RECUSADA",
        "ATRASADO",
    ]:
        phases[name], _ = ServiceOrderPhase.objects.get_or_create(name=name)

    today = date.today()
    A = admin_user       # "ADMIN TEST"
    B = attendant_user   # "ATENDENTE TEST"

    def pd(*rows):
        return [
            {"amount": amt, "forma_pagamento": "PIX", "tipo": tipo, "data": f"{today}T10:00:00"}
            for amt, tipo in rows
        ]

    # 1) A, FINALIZADO, Aluguel, NOIVA, INSTAGRAM
    ServiceOrder.objects.create(
        renter=client_person, employee=A, attendant=A, order_date=today,
        service_order_phase=phases["FINALIZADO"], total_value=Decimal("500.00"),
        renter_role="NOIVA", came_from="INSTAGRAM", service_type="Aluguel",
        payment_details=pd((500.0, "sinal")),
    )
    # 2) A, RECUSADA, Aluguel, NOIVA, INSTAGRAM  (not "fechada")
    ServiceOrder.objects.create(
        renter=client_person, employee=A, attendant=A, order_date=today,
        service_order_phase=phases["RECUSADA"], total_value=Decimal("300.00"),
        renter_role="NOIVA", came_from="INSTAGRAM", service_type="Aluguel",
        payment_details=pd((100.0, "sinal")),
    )
    # 3) A, EM_PRODUCAO, Venda, MADRINHA, GOOGLE
    ServiceOrder.objects.create(
        renter=client_person, employee=A, attendant=A, order_date=today,
        service_order_phase=phases["EM_PRODUCAO"], total_value=Decimal("200.00"),
        renter_role="MADRINHA", came_from="GOOGLE", service_type="Venda",
        payment_details=pd((200.0, "sinal")),
    )
    # 4) B, FINALIZADO, Venda, MADRINHA, GOOGLE  (two payments)
    ServiceOrder.objects.create(
        renter=client_person, employee=B, attendant=B, order_date=today,
        service_order_phase=phases["FINALIZADO"], total_value=Decimal("1000.00"),
        renter_role="MADRINHA", came_from="GOOGLE", service_type="Venda",
        payment_details=pd((400.0, "sinal"), (600.0, "restante")),
    )
    # 5) B, PENDENTE, Aluguel, sem role/canal
    ServiceOrder.objects.create(
        renter=client_person, employee=B, attendant=B, order_date=today,
        service_order_phase=phases["PENDENTE"], total_value=Decimal("150.00"),
        renter_role=None, came_from="GOOGLE", service_type="Aluguel",
    )
    # 6) virtual payment (+50) and 7) virtual estorno (-30)
    ServiceOrder.objects.create(
        renter=None, order_date=today, service_order_phase=phases["FINALIZADO"],
        is_virtual=True, total_value=Decimal("0.00"),
        payment_details=pd((50.0, "sinal")),
    )
    ServiceOrder.objects.create(
        renter=None, order_date=today, service_order_phase=phases["FINALIZADO"],
        is_virtual=True, total_value=Decimal("0.00"),
        payment_details=pd((30.0, "estorno")),
    )
    return today


@pytest.mark.django_db
class TestDashboardCharacterization:
    def test_full_payload(self, admin_client, dashboard_data):
        today = str(dashboard_data)
        resp = admin_client.get(
            f"/api/v1/service-orders/dashboard/?data_inicio={today}&data_fim={today}"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]

        # ----- KPIs -----
        assert data["kpis"] == {
            "total_recebido": 1720.0,
            "total_vendido": 1700.0,
            "total_atendimentos": 5,
            "atendimentos_fechados": 3,
            "atendimentos_nao_fechados": 1,
            "taxa_conversao": 60.0,
        }

        # ----- atendentes: taxa de conversão (desc) -----
        assert data["atendentes_taxa_conversao"] == [
            {"id": _pid("ADMIN TEST"), "nome": "ADMIN TEST",
             "taxa_conversao": 66.67, "num_atendimentos": 3, "num_fechados": 2},
            {"id": _pid("ATENDENTE TEST"), "nome": "ATENDENTE TEST",
             "taxa_conversao": 50.0, "num_atendimentos": 2, "num_fechados": 1},
        ]

        # ----- atendentes: total vendido (desc) -----
        assert data["atendentes_total_vendido"] == [
            {"id": _pid("ATENDENTE TEST"), "nome": "ATENDENTE TEST",
             "total_vendido": 1000.0, "num_atendimentos": 1},
            {"id": _pid("ADMIN TEST"), "nome": "ADMIN TEST",
             "total_vendido": 700.0, "num_atendimentos": 2},
        ]

        # ----- gráfico tipo de cliente (desc por fechados) -----
        assert data["grafico_tipo_cliente"] == [
            {"tipo": "MADRINHA", "atendimentos_fechados": 2, "total_vendido": 1200.0},
            {"tipo": "NOIVA", "atendimentos_fechados": 1, "total_vendido": 500.0},
            {"tipo": "NÃO INFORMADO", "atendimentos_fechados": 0, "total_vendido": 0.0},
        ]

        # ----- gráfico canal de origem (desc por atendimentos) -----
        assert data["grafico_canal_origem"] == [
            {"canal": "GOOGLE", "atendimentos": 3, "atendimentos_fechados": 2},
            {"canal": "INSTAGRAM", "atendimentos": 2, "atendimentos_fechados": 1},
        ]

        # ----- gráfico aluguel x venda (desc por valor) -----
        assert data["grafico_aluguel_venda"] == [
            {"tipo": "VENDA", "valor_total": 1200.0, "quantidade_os": 2, "valor_medio": 600.0},
            {"tipo": "ALUGUEL", "valor_total": 500.0, "quantidade_os": 1, "valor_medio": 500.0},
        ]

        # ----- filtros disponíveis -----
        assert data["filtros_disponiveis"]["atendentes"] == [
            {"id": _pid("ADMIN TEST"), "nome": "ADMIN TEST"},
            {"id": _pid("ATENDENTE TEST"), "nome": "ATENDENTE TEST"},
        ]
        assert data["filtros_disponiveis"]["tipos_cliente"] == ["MADRINHA", "NOIVA"]
        assert data["filtros_disponiveis"]["formas_pagamento"] == []
        assert data["filtros_disponiveis"]["canais_origem"] == ["GOOGLE", "INSTAGRAM"]

        # ----- resultados financeiros (dia/semana/mês idênticos: só há hoje) -----
        # total_recebido agora bate com o dos KPIs (1720): cada pagamento conta
        # exatamente uma vez. O bug legado que somava em dobro os pagamentos de
        # OS virtuais em fase confirmada (resultando em 1740) foi corrigido.
        for periodo in ("dia", "semana", "mes"):
            assert data["resultados"][periodo] == {
                "total_pedidos": 1700.0,
                "total_recebido": 1720.0,
                "numero_pedidos": 3,
            }, periodo

        # ----- OS do dia -----
        osd = data["os_do_dia"]
        assert osd["total_pendentes"] == 1
        assert osd["total_em_producao"] == 1
        assert osd["total_recusadas"] == 1
        assert osd["total_do_dia"] == 5
        assert len(osd["finalizadas"]) == 2
        assert len(osd["aguardando_retirada"]) == 0
        assert len(osd["aguardando_devolucao"]) == 0

        # ----- status/agenda (nenhuma data agendada => tudo zero) -----
        assert data["status"] == {
            "em_atraso": {"provas": 0, "retiradas": 0, "devolucoes": 0},
            "hoje": {"provas": 0, "retiradas": 0, "devolucoes": 0},
            "proximos_10_dias": {"provas": 0, "retiradas": 0, "devolucoes": 0},
        }


    def test_virtual_confirmada_nao_conta_em_dobro(self, admin_client, dashboard_data):
        """
        Regressão do bug de dupla contagem: OS virtuais em fase confirmada
        (FINALIZADO) eram somadas duas vezes no total_recebido dos resultados
        financeiros. Agora KPIs e resultados devem concordar.
        """
        today = str(dashboard_data)
        resp = admin_client.get(
            f"/api/v1/service-orders/dashboard/?data_inicio={today}&data_fim={today}"
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Fixture: 1720 = 500 + 100 + 200 + 400 + 600 + 50 (virtual) - 30 (estorno virtual)
        assert data["kpis"]["total_recebido"] == 1720.0
        assert data["resultados"]["dia"]["total_recebido"] == 1720.0
        assert (
            data["resultados"]["dia"]["total_recebido"]
            == data["kpis"]["total_recebido"]
        )

    def test_query_count_is_bounded(self, admin_client, dashboard_data):
        """The dashboard must not issue an unbounded (N+1) number of queries."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        today = str(dashboard_data)
        with CaptureQueriesContext(connection) as ctx:
            resp = admin_client.get(
                f"/api/v1/service-orders/dashboard/?data_inicio={today}&data_fim={today}"
            )
        assert resp.status_code == 200
        n = len(ctx.captured_queries)
        print(f"\n>>> DASHBOARD QUERY COUNT: {n}")
        # After the refactor this is a small CONSTANT (~11) regardless of how
        # many orders/employees exist. Guardrail catches N+1 regressions.
        assert n < 15, f"too many queries: {n}"

    def test_query_count_does_not_grow_with_more_atendentes(
        self, admin_client, dashboard_data, db
    ):
        """N+1 guard: adding employees/orders must NOT increase query count."""
        from datetime import date
        from decimal import Decimal

        from django.contrib.auth.models import User
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from accounts.models import Person, PersonType
        from service_control.models import ServiceOrder, ServiceOrderPhase

        pt, _ = PersonType.objects.get_or_create(type="ATENDENTE")
        fin, _ = ServiceOrderPhase.objects.get_or_create(name="FINALIZADO")
        today = date.today()
        # Add 8 more employees, each with a few orders.
        for i in range(8):
            cpf = f"9000000000{i}"
            u = User.objects.create_user(username=cpf, password="x")
            emp = Person.objects.create(user=u, name=f"EMP {i}", cpf=cpf, person_type=pt)
            for _ in range(3):
                ServiceOrder.objects.create(
                    employee=emp, order_date=today, service_order_phase=fin,
                    total_value=Decimal("100.00"), renter_role="NOIVA",
                    came_from="GOOGLE", service_type="Aluguel",
                )

        with CaptureQueriesContext(connection) as ctx:
            resp = admin_client.get(
                f"/api/v1/service-orders/dashboard/?data_inicio={today}&data_fim={today}"
            )
        assert resp.status_code == 200
        n = len(ctx.captured_queries)
        print(f"\n>>> DASHBOARD QUERY COUNT (9 atendentes, 29 OS): {n}")
        assert n < 15, f"query count grew with data (N+1 regression): {n}"


def _pid(name):
    return Person.objects.get(name=name).id
