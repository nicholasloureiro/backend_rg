"""
Otimização sem mudar respostas: número de queries constante, contagens das abas
iguais às listas, e valores do Financeiro e da Planilha preservados.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from accounts.models import City, Person, PersonsAdresses, PersonsContacts, PersonType
from products.models import ColorCatalogue, ColorIntensity, TemporaryProduct
from service_control.models import Event, ServiceOrder, ServiceOrderItem, ServiceOrderPhase

HOJE = date.today()
ONTEM = HOJE - timedelta(days=1)
AMANHA = HOJE + timedelta(days=1)
FASES = [
    "PENDENTE", "EM_PRODUCAO", "AGUARDANDO_RETIRADA", "AGUARDANDO_DEVOLUCAO",
    "ATRASADO", "RECUSADA", "FINALIZADO",
]


@pytest.fixture
def fases(db):
    return {n: ServiceOrderPhase.objects.get_or_create(name=n)[0] for n in FASES}


@pytest.fixture
def cidade(db):
    return City.objects.create(code="1", name="Uberlândia", uf="MG")


def novo_cliente(n, cidade=None):
    pt, _ = PersonType.objects.get_or_create(type="CLIENTE")
    pessoa = Person.objects.create(name=f"CLIENTE {n}", cpf=f"{10000000000 + n}", person_type=pt)
    PersonsContacts.objects.create(person=pessoa, phone=f"34{n}", email=f"c{n}@x.com")
    if cidade:
        PersonsAdresses.objects.create(person=pessoa, street=f"Rua {n}", number="1", city=cidade)
    return pessoa


def nova_os(fase, admin, **kw):
    kw.setdefault("order_date", HOJE)
    kw.setdefault("service_type", "Aluguel")
    return ServiceOrder.objects.create(
        service_order_phase=fase, employee=admin, attendant=admin, **kw
    )


def queries_de(client, url):
    with CaptureQueriesContext(connection) as ctx:
        resp = client.get(url)
    assert resp.status_code == 200, resp.data
    return len(ctx), resp


@pytest.mark.django_db
class TestListagemPorFaseV2:
    URL = "/api/v1/service-orders/v2/phase/PENDENTE/?page=1&page_size=50&ordering=-id"

    def _criar(self, qtd, inicio, fases, admin_user, cidade):
        evento = Event.objects.create(name=f"E{inicio}", event_date=AMANHA)
        for i in range(inicio, inicio + qtd):
            os_ = nova_os(fases["PENDENTE"], admin_user, renter=novo_cliente(i, cidade), event=evento)
            ServiceOrderItem.objects.create(
                service_order=os_,
                temporary_product=TemporaryProduct.objects.create(product_type="paleto"),
            )

    def test_queries_nao_crescem_com_as_linhas(self, admin_client, admin_user, fases, cidade):
        self._criar(3, 1, fases, admin_user, cidade)
        poucas, _ = queries_de(admin_client, self.URL)
        self._criar(20, 100, fases, admin_user, cidade)
        muitas, resp = queries_de(admin_client, self.URL)
        assert resp.data["count"] == 23
        assert muitas == poucas

    def test_usa_contato_e_endereco_mais_recentes(self, admin_client, admin_user, fases, cidade):
        cliente = novo_cliente(1, cidade)
        PersonsContacts.objects.create(person=cliente, phone="NOVO", email="novo@x.com")
        PersonsAdresses.objects.create(person=cliente, street="Rua Nova", number="2", city=cidade)
        nova_os(fases["PENDENTE"], admin_user, renter=cliente)

        _, resp = queries_de(admin_client, self.URL)

        dados = resp.data["results"][0]["client"]
        assert [c["phone"] for c in dados["contacts"]] == ["NOVO"]
        assert [a["rua"] for a in dados["addresses"]] == ["Rua Nova"]
        assert dados["addresses"][0]["cidade"]["name"] == "Uberlândia"

    def test_os_sem_cliente_continua_listada(self, admin_client, admin_user, fases):
        nova_os(fases["PENDENTE"], admin_user, client_name="AVULSO")
        _, resp = queries_de(admin_client, self.URL)
        assert resp.data["results"][0]["client"]["name"] == "AVULSO"

    def test_empate_de_data_tem_ordem_estavel(self, admin_client, admin_user, fases):
        ids = [nova_os(fases["PENDENTE"], admin_user).id for _ in range(3)]
        _, resp = queries_de(
            admin_client, "/api/v1/service-orders/v2/phase/PENDENTE/?ordering=-order_date"
        )
        assert [o["id"] for o in resp.data["results"]] == sorted(ids, reverse=True)

    def test_page_size_tem_limite(self, admin_client, admin_user, fases):
        nova_os(fases["PENDENTE"], admin_user)
        _, resp = queries_de(
            admin_client, "/api/v1/service-orders/v2/phase/PENDENTE/?page_size=100000"
        )
        assert resp.data["page_size"] == 200


@pytest.mark.django_db
class TestRecusaAutomatica:
    URL = "/api/v1/service-orders/v2/phase/RECUSADA/?ordering=-id"

    def test_evento_passado_recusa_e_preenche_data(self, admin_client, admin_user, fases):
        evento = Event.objects.create(name="E", event_date=ONTEM)
        os_ = nova_os(
            fases["PENDENTE"], admin_user, event=evento,
            total_value=Decimal("300"), advance_payment=Decimal("100"),
            remaining_payment=Decimal("0"),
        )

        queries_de(admin_client, self.URL)

        os_.refresh_from_db()
        assert os_.service_order_phase.name == "RECUSADA"
        assert os_.justification_refusal == "Cliente não retirou o produto"
        assert os_.data_recusa == HOJE
        assert os_.remaining_payment == Decimal("200")  # recalculado, como fazia o save()

    def test_filtro_de_data_acha_a_os_recusada_automaticamente(
        self, admin_client, admin_user, fases
    ):
        evento = Event.objects.create(name="E", event_date=ONTEM)
        os_ = nova_os(fases["EM_PRODUCAO"], admin_user, event=evento)
        queries_de(admin_client, self.URL)
        _, resp = queries_de(admin_client, f"{self.URL}&filter_date={HOJE}")
        assert [o["id"] for o in resp.data["results"]] == [os_.id]

    @pytest.mark.parametrize("fase", ["AGUARDANDO_RETIRADA", "FINALIZADO"])
    def test_nao_recusa_outras_fases(self, admin_client, admin_user, fases, fase):
        evento = Event.objects.create(name="E", event_date=ONTEM)
        os_ = nova_os(fases[fase], admin_user, event=evento)
        queries_de(admin_client, self.URL)
        os_.refresh_from_db()
        assert os_.service_order_phase.name == fase

    def test_nao_recusa_quem_ja_retirou_ou_evento_futuro(self, admin_client, admin_user, fases):
        passado = Event.objects.create(name="P", event_date=ONTEM)
        futuro = Event.objects.create(name="F", event_date=AMANHA)
        retirou = nova_os(
            fases["PENDENTE"], admin_user, event=passado, data_retirado=timezone.now()
        )
        vai_ocorrer = nova_os(fases["PENDENTE"], admin_user, event=futuro)
        queries_de(admin_client, self.URL)
        for os_ in (retirou, vai_ocorrer):
            os_.refresh_from_db()
            assert os_.service_order_phase.name == "PENDENTE"


@pytest.mark.django_db
class TestFlagDeAtrasoAguardandoRetirada:
    URL = "/api/v1/service-orders/v2/phase/AGUARDANDO_RETIRADA/?ordering=-id"

    def test_marca_e_desmarca_so_quando_muda(self, admin_client, admin_user, fases):
        fase = fases["AGUARDANDO_RETIRADA"]
        passado = Event.objects.create(name="P", event_date=ONTEM)
        futuro = Event.objects.create(name="F", event_date=AMANHA)
        casos = {
            "retirada_vencida": (nova_os(fase, admin_user, retirada_date=ONTEM), True),
            "evento_vencido": (nova_os(fase, admin_user, event=passado), True),
            "evento_vencido_ja_retirou": (
                nova_os(fase, admin_user, event=passado, data_retirado=timezone.now()), False
            ),
            "tudo_no_futuro": (
                nova_os(fase, admin_user, event=futuro, retirada_date=AMANHA, esta_atrasada=True),
                False,
            ),
            "sem_datas": (nova_os(fase, admin_user, esta_atrasada=True), False),
        }

        queries_de(admin_client, self.URL)

        for nome, (os_, esperado) in casos.items():
            os_.refresh_from_db()
            assert os_.esta_atrasada is esperado, nome

    def test_nao_carrega_a_fase_inteira(self, admin_client, admin_user, fases):
        fase = fases["AGUARDANDO_RETIRADA"]
        url = f"{self.URL}&page_size=1"
        nova_os(fase, admin_user)
        poucas, _ = queries_de(admin_client, url)
        for _ in range(15):
            nova_os(fase, admin_user, retirada_date=AMANHA)
        muitas, _ = queries_de(admin_client, url)
        assert muitas == poucas


@pytest.mark.django_db
class TestContagemDasAbas:
    URL = "/api/v1/service-orders/phase-counts/"

    def test_igual_a_cada_listagem(self, admin_client, admin_user, fases):
        passado = Event.objects.create(name="P", event_date=ONTEM)
        futuro = Event.objects.create(name="F", event_date=AMANHA)
        for fase, qtd in [("EM_PRODUCAO", 2), ("AGUARDANDO_RETIRADA", 1), ("FINALIZADO", 3)]:
            for _ in range(qtd):
                nova_os(fases[fase], admin_user)
        nova_os(fases["PENDENTE"], admin_user, event=futuro)
        nova_os(fases["PENDENTE"], admin_user, event=passado)  # vira RECUSADA
        nova_os(fases["AGUARDANDO_DEVOLUCAO"], admin_user, devolucao_date=ONTEM)  # conta nas duas
        nova_os(fases["AGUARDANDO_DEVOLUCAO"], admin_user, devolucao_date=AMANHA)
        nova_os(fases["PENDENTE"], admin_user, is_virtual=True)  # virtual nunca conta

        _, resp = queries_de(admin_client, self.URL)

        for fase in FASES:
            _, lista = queries_de(
                admin_client, f"/api/v1/service-orders/v2/phase/{fase}/?page_size=1"
            )
            assert resp.data[fase] == lista.data["count"], fase
        assert resp.data["RECUSADA"] == 1
        assert resp.data["ATRASADO"] == 1

    def test_exige_autenticacao(self, api_client):
        assert api_client.get(self.URL).status_code == 401

    def test_queries_constantes(self, admin_client, admin_user, fases):
        nova_os(fases["PENDENTE"], admin_user)
        poucas, _ = queries_de(admin_client, self.URL)
        for fase in fases.values():
            nova_os(fase, admin_user)
        muitas, _ = queries_de(admin_client, self.URL)
        assert muitas == poucas
        assert muitas <= 12


def _pagamento(valor, tipo, data="2026-01-10T10:00:00", forma="PIX", **extra):
    d = {"amount": valor, "tipo": tipo, "forma_pagamento": forma, **extra}
    if data:
        d["data"] = data
    return d


@pytest.fixture
def carteira(admin_user, fases, client_person):
    """Um caso de cada forma de dinheiro que Financeiro e Planilha tratam."""
    fin, pen, rec = fases["FINALIZADO"], fases["PENDENTE"], fases["RECUSADA"]
    d = date(2026, 1, 5)
    r = client_person
    return {
        "sinal_restante": nova_os(fin, admin_user, renter=r, order_date=d, total_value=Decimal("400"), advance_payment=Decimal("200"), remaining_payment=Decimal("200"), payment_details=[_pagamento(200.0, "sinal"), _pagamento(200.0, "restante", "2026-01-12T00:00:00")], observations="obs A", came_from="Google"),
        "estorno": nova_os(pen, admin_user, renter=r, order_date=d, total_value=Decimal("100"), advance_payment=Decimal("100"), payment_details=[_pagamento(100.0, "sinal"), _pagamento(30.0, "estorno", forma="DINHEIRO")]),
        "indenizacao_sem_data": nova_os(pen, admin_user, renter=r, order_date=d, total_value=Decimal("50"), payment_details=[_pagamento(20.0, "indenizacao", data=None)]),
        "valor_zero": nova_os(pen, admin_user, renter=r, order_date=d, payment_details=[_pagamento(0, "parcial")]),
        "legada_sinal": nova_os(pen, admin_user, renter=r, order_date=d, total_value=Decimal("90"), advance_payment=Decimal("45"), payment_method="CREDITO"),
        "legada_finalizada": nova_os(fin, admin_user, renter=r, order_date=d, total_value=Decimal("70"), advance_payment=Decimal("0"), remaining_payment=Decimal("70"), payment_method="PIX", data_devolvido=timezone.make_aware(datetime(2026, 1, 20))),
        "virtual": nova_os(pen, admin_user, client_name="AVULSO", order_date=d, is_virtual=True, payment_details=[_pagamento(15.0, "sinal")], observations="caixa"),
        "recusada": nova_os(rec, admin_user, renter=r, order_date=d, total_value=Decimal("60"), advance_payment=Decimal("60"), payment_details=[_pagamento(60.0, "sinal")]),
        "sem_dinheiro": nova_os(pen, admin_user, renter=r, order_date=d, total_value=Decimal("0"), advance_payment=Decimal("0"), remaining_payment=Decimal("0")),
    }


@pytest.mark.django_db
class TestFinanceiroPreservaValores:
    URL = "/api/v1/service-orders/finance/"

    def test_total_transacoes_e_metodos(self, admin_client, carteira):
        n, resp = queries_de(admin_client, self.URL)
        assert resp.data["total_amount"] == Decimal("680")
        assert resp.data["total_transactions"] == 9
        assert resp.data["totals_by_method"] == {
            "PIX": Decimal("665"), "DINHEIRO": Decimal("-30"), "CREDITO": Decimal("45"),
        }
        por_os = {}
        for t in resp.data["transactions"]:
            por_os.setdefault(t["order_id"], []).append((t["transaction_type"], t["amount"]))
        assert carteira["sem_dinheiro"].id not in por_os
        assert carteira["valor_zero"].id not in por_os
        assert (("estorno", Decimal("-30.0")) in por_os[carteira["estorno"].id])
        assert por_os[carteira["legada_finalizada"].id] == [("restante", Decimal("70.0"))]
        assert n <= 2, "campos adiados não podem gerar query por linha"

    def test_cliente_descricao_e_datas(self, admin_client, carteira):
        _, resp = queries_de(admin_client, self.URL)
        por_id = {t["order_id"]: t for t in resp.data["transactions"]}
        assert por_id[carteira["virtual"].id]["client_name"] == "AVULSO"
        assert por_id[carteira["virtual"].id]["description"] == "caixa"
        assert por_id[carteira["virtual"].id]["is_virtual"] is True
        assert por_id[carteira["recusada"].id]["client_name"] == "CLIENTE TESTE"
        assert por_id[carteira["indenizacao_sem_data"].id]["date"] == "2026-01-05"

    def test_filtro_usa_data_do_pagamento(self, admin_client, carteira):
        _, resp = queries_de(admin_client, f"{self.URL}?start_date=2026-01-11&end_date=2026-01-15")
        assert [(t["order_id"], t["transaction_type"]) for t in resp.data["transactions"]] == [
            (carteira["sinal_restante"].id, "restante")
        ]

    def test_paginas_nao_repetem_nem_perdem(self, admin_client, carteira):
        vistos = []
        for pagina in (1, 2, 3):
            _, resp = queries_de(admin_client, f"{self.URL}?page={pagina}&page_size=4")
            vistos += [(t["order_id"], t["transaction_type"], t["date"]) for t in resp.data["transactions"]]
        assert len(vistos) == 9
        assert len(set(map(str, vistos))) == 9


@pytest.mark.django_db
class TestPlanilhaPreservaValores:
    URL = "/api/v1/service-orders/planilha/"

    def test_linhas_e_totais(self, admin_client, carteira):
        n, resp = queries_de(admin_client, self.URL)
        assert resp.data["totals"]["total_recebido"] == 610.0  # planilha não inclui restante legado
        assert resp.data["count"] == 10  # OS sem dinheiro aparecem com valor 0
        linhas = resp.data["results"]
        zerada = [l for l in linhas if l["numero_os"] == carteira["sem_dinheiro"].id]
        assert [l["valor"] for l in zerada] == [0]
        virtual = [l for l in linhas if l["fase"] == "VIRTUAL"]
        assert [(l["nome_cliente"], l["valor"], l["justificativa"]) for l in virtual] == [("AVULSO", 15.0, "caixa")]
        assert n <= 5, "campos adiados não podem gerar query por linha"

    def test_campos_da_linha(self, admin_client, carteira, admin_user):
        _, resp = queries_de(admin_client, f"{self.URL}?canal=Google")
        sinal = next(l for l in resp.data["results"] if l["tipo"] == "sinal")
        assert sinal["numero_os"] == carteira["sinal_restante"].id
        assert sinal["atendente"] == admin_user.name
        assert sinal["nome_cliente"] == "CLIENTE TESTE"
        assert sinal["fechamento"] == "SIM"
        assert sinal["valor_total_venda"] == 400.0
        assert sinal["justificativa"] == "obs A"


@pytest.mark.django_db
class TestEventos:
    URL = "/api/v1/events/list-with-status/?page=1&page_size=50"

    def _status(self, client):
        _, resp = queries_de(client, self.URL)
        return {e["name"]: (e["status"], e["service_orders_count"]) for e in resp.data["events"]}

    def test_status_de_cada_situacao(self, admin_client, admin_user, fases):
        def evento(nome, data, *nomes_fase):
            e = Event.objects.create(name=nome, event_date=data)
            for f in nomes_fase:
                nova_os(fases[f], admin_user, event=e, data_retirado=timezone.now())

        evento("sem_data", None)
        evento("futuro", AMANHA, "PENDENTE")
        evento("passado_vazio", ONTEM)
        evento("todas_finalizadas", ONTEM, "FINALIZADO", "FINALIZADO")
        evento("pendencia", ONTEM, "FINALIZADO", "AGUARDANDO_DEVOLUCAO")
        evento("so_recusadas", ONTEM, "RECUSADA")

        assert self._status(admin_client) == {
            "sem_data": ("N/A", 0),
            "futuro": ("AGENDADO", 1),
            "passado_vazio": ("CANCELADO", 0),
            "todas_finalizadas": ("FINALIZADO", 2),
            "pendencia": ("POSSUI PENDÊNCIAS", 2),
            "so_recusadas": ("CANCELADO", 1),
        }

    def test_queries_constantes_e_paginacao(self, admin_client, admin_user, fases):
        for i in range(3):
            nova_os(fases["FINALIZADO"], admin_user, event=Event.objects.create(name=f"A{i}", event_date=ONTEM))
        poucas, _ = queries_de(admin_client, self.URL)
        for i in range(20):
            nova_os(fases["FINALIZADO"], admin_user, event=Event.objects.create(name=f"B{i}", event_date=ONTEM))
        muitas, _ = queries_de(admin_client, self.URL)
        assert muitas == poucas <= 3

        _, pag = queries_de(admin_client, "/api/v1/events/list-with-status/?page=2&page_size=10")
        assert pag.data["count"] == 23
        assert pag.data["total_pages"] == 3
        assert len(pag.data["events"]) == 10

    def test_pagina_alem_do_fim_vem_vazia(self, admin_client):
        Event.objects.create(name="E", event_date=AMANHA)
        _, resp = queries_de(admin_client, "/api/v1/events/list-with-status/?page=9")
        assert resp.data["events"] == []


@pytest.mark.django_db
class TestClientes:
    URL = "/api/v1/clients/list/?page=1&page_size=50"

    def test_queries_constantes(self, admin_client, cidade):
        for i in range(3):
            novo_cliente(i, cidade)
        poucas, _ = queries_de(admin_client, self.URL)
        for i in range(10, 30):
            novo_cliente(i, cidade)
        muitas, resp = queries_de(admin_client, self.URL)
        assert muitas == poucas
        assert resp.data["count"] == 23

    def test_prefere_recente_com_data_senao_maior_id(self, admin_client, cidade):
        com_data = novo_cliente(1, cidade)
        recente = PersonsContacts.objects.create(person=com_data, phone="RECENTE", email="r@x.com")
        sem_data_mais_novo = PersonsContacts.objects.create(person=com_data, phone="SEM DATA", email="s@x.com")
        PersonsContacts.objects.filter(id=sem_data_mais_novo.id).update(date_created=None)

        so_sem_data = novo_cliente(2, cidade)
        PersonsContacts.objects.create(person=so_sem_data, phone="MAIOR ID", email="m@x.com")
        PersonsContacts.objects.filter(person=so_sem_data).update(date_created=None)
        PersonsAdresses.objects.filter(person=so_sem_data).update(date_created=None)

        sem_nada = Person.objects.create(name="VAZIO", cpf="99999999999", person_type=com_data.person_type)

        _, resp = queries_de(admin_client, self.URL)
        por_id = {c["id"]: c for c in resp.data["clients"]}
        assert por_id[com_data.id]["phone"] == recente.phone
        assert por_id[so_sem_data.id]["phone"] == "MAIOR ID"
        assert por_id[so_sem_data.id]["address"]["city"] == "Uberlândia"
        assert por_id[sem_nada.id]["phone"] == ""
        assert por_id[sem_nada.id]["address"] is None

    def test_page_size_tem_limite(self, admin_client):
        _, resp = queries_de(admin_client, "/api/v1/clients/list/?page_size=100000")
        assert resp.data["page_size"] == 200


@pytest.mark.django_db
class TestCores:
    def test_queries_nao_crescem_e_resposta_completa(self, api_client):
        cor = ColorCatalogue.objects.create(description="Azul")
        forte = ColorIntensity.objects.create(description="Forte")
        n1, resp = queries_de(api_client, "/api/v1/colors/")
        assert [r["combined"] for r in resp.data] == ["Azul", "Azul Forte"]
        assert cor and forte
        for i in range(5):
            ColorCatalogue.objects.create(description=f"C{i}")
            ColorIntensity.objects.create(description=f"I{i}")
        n2, _ = queries_de(api_client, "/api/v1/colors/")
        assert n2 == n1 <= 2


def test_debug_desligado_por_padrao(monkeypatch):
    from roupadegala.settings import env_bool

    monkeypatch.delenv("DEBUG", raising=False)
    assert env_bool("DEBUG") is False
    for ligado in ("True", "true", "1"):
        monkeypatch.setenv("DEBUG", ligado)
        assert env_bool("DEBUG") is True
    for desligado in ("False", "0", ""):
        monkeypatch.setenv("DEBUG", desligado)
        assert env_bool("DEBUG") is False


def test_gzip_ativo(settings):
    assert "django.middleware.gzip.GZipMiddleware" in settings.MIDDLEWARE


@pytest.mark.django_db
class TestDetalheDoCliente:
    def test_mesmo_formato_da_listagem(self, admin_client, cidade):
        cliente = novo_cliente(1, cidade)
        _, lista = queries_de(admin_client, "/api/v1/clients/list/?page_size=50")
        n, resp = queries_de(admin_client, f"/api/v1/clients/{cliente.id}/")
        assert resp.data == lista.data["clients"][0]
        assert n <= 4

    def test_nao_encontrado_e_nao_cliente(self, admin_client, admin_user):
        assert admin_client.get("/api/v1/clients/999999/").status_code == 404
        assert admin_client.get(f"/api/v1/clients/{admin_user.id}/").status_code == 404

    def test_exige_autenticacao(self, api_client, cidade):
        cliente = novo_cliente(1, cidade)
        assert api_client.get(f"/api/v1/clients/{cliente.id}/").status_code == 401
