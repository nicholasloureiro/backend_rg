"""
Views API para o app service_control
"""

import logging
from datetime import date, timedelta
from decimal import Decimal

logger = logging.getLogger(__name__)

from django.db import models
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, OpenApiExample
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import City, Person, PersonsAdresses, PersonsContacts, PersonType
from products.models import TemporaryProduct

from .models import (
    Event,
    EventParticipant,
    ServiceOrder,
    ServiceOrderItem,
    ServiceOrderPhase,
)
from .serializers import (
    EventAddParticipantsSerializer,
    EventCreateSerializer,
    EventDetailSerializer,
    EventLinkServiceOrderSerializer,
    EventListWithStatusSerializer,
    EventSerializer,
    EventStatusSerializer,
    EventUpdateSerializer,
    FrontendServiceOrderUpdateSerializer,
    ServiceOrderClientSerializer,
    ServiceOrderDashboardResponseSerializer,
    ServiceOrderListByPhaseSerializer,
    ServiceOrderMarkPaidSerializer,
    ServiceOrderMarkRetrievedSerializer,
    ServiceOrderRefuseSerializer,
    ServiceOrderSerializer,
    ServiceOrderFinanceSummarySerializer,
    VirtualServiceOrderCreateSerializer,
)
from django.core.paginator import Paginator, EmptyPage


@extend_schema(
    tags=["service-orders"],
    summary="Criar ordem de serviço",
    description="Cria uma nova ordem de serviço no sistema",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "cliente_nome": {"type": "string", "description": "Nome do cliente"},
                "telefone": {"type": "string", "description": "Telefone do cliente (opcional)"},
                "email": {
                    "type": "string",
                    "format": "email",
                    "description": "Email do cliente (opcional)",
                },
                "cpf": {"type": "string", "description": "CPF do cliente"},
                "atendente": {"type": "string", "description": "Nome do atendente"},
                "origem": {"type": "string", "description": "Origem do pedido"},
                "data_evento": {
                    "type": "string",
                    "format": "date",
                    "description": "Data do evento",
                },
                "tipo_servico": {
                    "type": "string",
                    "description": "Tipo de serviço (Aluguel/Compra)",
                },
                "papel_evento": {"type": "string", "description": "Papel no evento"},
                "endereco": {
                    "type": "object",
                    "properties": {
                        "cep": {"type": "string"},
                        "rua": {"type": "string"},
                        "numero": {"type": "string"},
                        "bairro": {"type": "string"},
                        "cidade": {"type": "string"},
                        "complemento": {
                            "type": "string",
                            "description": "Complemento do endereço (opcional)",
                        },
                    },
                },
                "event_id": {
                    "type": "integer",
                    "description": "ID do evento para vincular à OS (opcional)",
                },
            },
            "required": [
                "cliente_nome",
                "cpf",
                "atendente",
                "origem",
                "data_evento",
                "tipo_servico",
                "papel_evento",
            ],
        }
    },
    responses={
        201: {
            "description": "Ordem de serviço criada com sucesso",
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
                "order_id": {"type": "integer"},
                "service_order": {"$ref": "#/components/schemas/ServiceOrder"},
            },
        },
        400: {"description": "Dados inválidos"},
        500: {"description": "Erro interno do servidor"},
    },
)
class ServiceOrderCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Criar nova ordem de serviço"""
        try:
            # Extrair dados da requisição
            order_data = {
                "cliente": request.data.get("cliente_nome"),
                "telefone": request.data.get("telefone"),
                "email": request.data.get("email", ""),
                "cpf": request.data.get("cpf", "").replace(".", "").replace("-", ""),
                "atendente": request.data.get("atendente"),
                "origem": request.data.get("origem"),
                "data_evento": request.data.get("data_evento"),
                "tipo_servico": request.data.get("tipo_servico"),
                "papel_evento": request.data.get("papel_evento"),
                "event_id": request.data.get("event_id"),
                "endereco": {
                    "cep": request.data.get("endereco", {}).get("cep"),
                    "rua": request.data.get("endereco", {}).get("rua"),
                    "numero": request.data.get("endereco", {}).get("numero"),
                    "bairro": request.data.get("endereco", {}).get("bairro"),
                    "cidade": request.data.get("endereco", {}).get("cidade"),
                    "complemento": request.data.get("endereco", {}).get("complemento"),
                },
            }

            # Validações
            if len(order_data["cpf"]) != 11:
                return Response(
                    {"error": "CPF Inválido"}, status=status.HTTP_400_BAD_REQUEST
                )

            if not all(
                [order_data["cpf"], order_data["cliente"]]
            ):
                return Response(
                    {"error": "Dados do cliente incompletos"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Buscar ou criar cidade
            city_obj = None
            cidade_nome = order_data["endereco"].get("cidade")
            if cidade_nome:
                try:
                    city_obj = City.objects.get(name__iexact=cidade_nome.upper())
                except City.DoesNotExist:
                    return Response(
                        {"error": "Cidade não encontrada"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Buscar ou criar cliente
            pt, _ = PersonType.objects.get_or_create(type="CLIENTE")
            person, _ = Person.objects.get_or_create(
                cpf=order_data["cpf"],
                defaults={
                    "name": order_data["cliente"].upper(),
                    "person_type": pt,
                    "created_by": request.user,
                },
            )

            # Criar contato (verificando duplicatas)
            email = order_data.get("email", "").strip()
            telefone = order_data.get("telefone", "") or ""

            # Tratar email vazio como None
            if not email:
                email = None

            # Criar contato apenas se tiver email ou telefone
            if email or telefone:
                PersonsContacts.objects.get_or_create(
                    phone=telefone,
                    person=person,
                    defaults={"email": email, "created_by": request.user},
                )

            # Criar endereço se cidade for informada
            if city_obj:
                PersonsAdresses.objects.get_or_create(
                    person=person,
                    street=order_data["endereco"].get("rua") or "",
                    number=order_data["endereco"].get("numero") or "",
                    cep=order_data["endereco"].get("cep") or "",
                    neighborhood=order_data["endereco"].get("bairro") or "",
                    city=city_obj,
                    defaults={"created_by": request.user},
                )

            # Buscar funcionário
            employee = Person.objects.filter(name=order_data["atendente"]).first()
            if not employee:
                return Response(
                    {"error": "Funcionário não encontrado."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validar e buscar evento se event_id fornecido
            event_obj = None
            event_id = order_data.get("event_id")
            if event_id:
                try:
                    event_obj = Event.objects.get(id=event_id)
                except Event.DoesNotExist:
                    return Response(
                        {"error": f"Evento com ID {event_id} não encontrado."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                except ValueError:
                    return Response(
                        {"error": "ID do evento inválido."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # Buscar fase pendente
            service_order_phase = ServiceOrderPhase.objects.filter(
                name="PENDENTE"
            ).first()

            # Criar ordem de serviço
            service_order = ServiceOrder.objects.create(
                renter=person,
                employee=employee,
                attendant=request.user.person,
                order_date=date.today(),
                renter_role=order_data["papel_evento"].upper(),
                purchase=True if order_data["tipo_servico"] in ["Compra", "Venda"] else False,
                service_type=order_data["tipo_servico"],
                came_from=order_data["origem"].upper(),
                service_order_phase=service_order_phase,
                event=event_obj,  # Vincular evento à OS se fornecido
            )

            return Response(
                {
                    "success": True,
                    "message": "OS criada com sucesso",
                    "order_id": service_order.id,
                    "service_order": ServiceOrderSerializer(service_order).data,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response(
                {"error": f"Erro ao criar OS: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Atualizar ordem de serviço",
    description="""Atualiza uma ordem de serviço existente com dados completos do frontend.
    
    **CPF do cliente é obrigatório** neste momento (diferente da triagem onde é opcional).
    
    Se o cliente foi criado na triagem sem CPF e o CPF informado pertencer a um cliente já existente,
    os dados (contatos e endereços) serão transferidos para o cliente existente e a pessoa temporária será removida.""",
    request=FrontendServiceOrderUpdateSerializer,
    responses={
        200: {
            "description": "Ordem de serviço atualizada com sucesso",
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
                "service_order": {"$ref": "#/components/schemas/ServiceOrder"},
            },
        },
        400: {"description": "CPF do cliente é obrigatório e deve conter 11 dígitos"},
        404: {"description": "Ordem de serviço não encontrada"},
        500: {"description": "Erro interno do servidor"},
    },
)
class ServiceOrderUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FrontendServiceOrderUpdateSerializer

    def put(self, request, order_id):
        """Atualizar ordem de serviço com dados do frontend"""
        try:
            service_order = get_object_or_404(ServiceOrder, id=order_id)

            # Validar dados com o serializer
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data

            # Processar dados da ordem de serviço
            if "ordem_servico" in data:
                os_data = data["ordem_servico"]

                if "data_retirada" in os_data:
                    service_order.retirada_date = os_data["data_retirada"]
                if "data_devolucao" in os_data:
                    service_order.devolucao_date = os_data["data_devolucao"]
                if "data_prova" in os_data:
                    service_order.prova_date = os_data["data_prova"]
                # NOTA: "ocasiao" é o papel do cliente no evento (renter_role), não o canal de origem
                # O campo came_from (canal de origem) é definido no pre-triage e não deve ser sobrescrito aqui
                if "ocasiao" in os_data and os_data["ocasiao"]:
                    service_order.renter_role = os_data["ocasiao"].upper()
                # Atualizar canal de origem (came_from) - se fornecido explicitamente
                if "origem" in os_data and os_data["origem"]:
                    service_order.came_from = os_data["origem"].upper()

                # Atualizar informações básicas
                if "modalidade" in os_data:
                    modalidade = os_data["modalidade"]
                    if modalidade == "Compra":
                        service_order.purchase = True
                    elif modalidade == "Aluguel":
                        service_order.purchase = False
                    elif modalidade == "Aluguel + Venda":
                        service_order.purchase = False  # Mantém como aluguel
                    elif modalidade == "Venda":
                        service_order.purchase = True

                    # Salvar modalidade no campo específico
                    service_order.service_type = modalidade

                # Atualizar atendente/recepcionista responsável
                if "employee_id" in os_data and os_data["employee_id"]:
                    try:
                        employee = Person.objects.get(id=os_data["employee_id"])
                        service_order.employee = employee
                    except Person.DoesNotExist:
                        return Response(
                            {
                                "error": f"Atendente com ID {os_data['employee_id']} não encontrado"
                            },
                            status=status.HTTP_400_BAD_REQUEST,
                        )

                if "pagamento" in os_data:
                    pagamento = os_data["pagamento"]

                    if "total" in pagamento:
                        service_order.total_value = pagamento["total"]

                    if "sinal" in pagamento:
                        sinal_data = pagamento["sinal"]
                        if isinstance(sinal_data, dict):
                            if "total" in sinal_data:
                                service_order.advance_payment = sinal_data["total"]
                            if "pagamentos" in sinal_data and sinal_data["pagamentos"]:
                                formas = []
                                payment_details = []
                                data_sinal = str(service_order.order_date)
                                for pag in sinal_data["pagamentos"]:
                                    forma = pag.get("forma_pagamento")
                                    amount = pag.get("amount", 0)
                                    if forma:
                                        if forma not in formas:
                                            formas.append(forma)
                                        payment_details.append({
                                            "amount": float(amount),
                                            "forma_pagamento": forma,
                                            "tipo": "sinal",
                                            "data": data_sinal
                                        })
                                if formas:
                                    service_order.payment_method = ", ".join(formas)
                                if payment_details:
                                    service_order.payment_details = payment_details
                        elif isinstance(sinal_data, (int, float, Decimal)):
                            service_order.advance_payment = Decimal(str(sinal_data))

                    if "forma_pagamento" in pagamento and pagamento["forma_pagamento"]:
                        service_order.payment_method = pagamento["forma_pagamento"]

            # Processar dados do cliente
            if "cliente" in data:
                cliente_data = data["cliente"]
                
                # CPF é obrigatório no update da OS
                cpf_raw = cliente_data.get("cpf", "") or ""
                cpf_limpo = cpf_raw.replace(".", "").replace("-", "").strip()
                
                if not cpf_limpo or len(cpf_limpo) != 11:
                    return Response(
                        {"error": "CPF do cliente é obrigatório no update da OS e deve conter 11 dígitos."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                
                current_renter = service_order.renter
                pessoa_temporaria = current_renter and not current_renter.cpf
                
                # Verificar se o CPF informado já existe em outra pessoa
                existing_person_with_cpf = Person.objects.filter(cpf=cpf_limpo).first()
                
                if pessoa_temporaria:
                    # Cliente atual foi criado na triagem sem CPF
                    if existing_person_with_cpf:
                        # CPF pertence a cliente já existente - transferir dados e vincular
                        # Transferir contatos da pessoa temporária para a pessoa existente
                        for contact in current_renter.contacts.all():
                            # Verificar se já existe contato igual na pessoa destino
                            existing = PersonsContacts.objects.filter(
                                person=existing_person_with_cpf,
                                email=contact.email,
                                phone=contact.phone,
                            ).exists()
                            if not existing:
                                contact.person = existing_person_with_cpf
                                contact.save()
                        
                        # Transferir endereços da pessoa temporária para a pessoa existente
                        for address in current_renter.personsadresses_set.all():
                            # Verificar se já existe endereço igual na pessoa destino
                            existing = PersonsAdresses.objects.filter(
                                person=existing_person_with_cpf,
                                street=address.street,
                                number=address.number,
                                cep=address.cep,
                                neighborhood=address.neighborhood,
                                complemento=address.complemento,
                                city=address.city,
                            ).exists()
                            if not existing:
                                address.person = existing_person_with_cpf
                                address.save()
                        
                        # Atualizar nome se fornecido
                        if cliente_data.get("nome"):
                            existing_person_with_cpf.name = cliente_data["nome"].upper()
                            existing_person_with_cpf.save()
                        
                        # Verificar se pessoa temporária não está vinculada a outras OS
                        other_os_count = ServiceOrder.objects.filter(renter=current_renter).exclude(id=service_order.id).count()
                        
                        # Atualizar renter da OS para a pessoa existente
                        person = existing_person_with_cpf
                        service_order.renter = person
                        
                        # Se pessoa temporária não tem outras OS, pode ser removida
                        if other_os_count == 0:
                            current_renter.delete()
                    else:
                        # CPF não existe - atualizar pessoa temporária com o CPF
                        current_renter.cpf = cpf_limpo
                        if cliente_data.get("nome"):
                            current_renter.name = cliente_data["nome"].upper()
                        current_renter.save()
                        person = current_renter
                else:
                    # Fluxo normal: cliente já tem CPF
                    if existing_person_with_cpf:
                        # Atualizar nome se mudou
                        if cliente_data.get("nome") and existing_person_with_cpf.name != cliente_data["nome"].upper():
                            existing_person_with_cpf.name = cliente_data["nome"].upper()
                            existing_person_with_cpf.save()
                        person = existing_person_with_cpf
                    else:
                        # Criar nova pessoa com o CPF
                        person = Person.objects.create(
                            cpf=cpf_limpo,
                            name=cliente_data.get("nome", "").upper(),
                            person_type=PersonType.objects.get_or_create(type="CLIENTE")[0],
                            created_by=request.user,
                        )
                    service_order.renter = person

                # Processar email e telefone do cliente
                email_cliente = cliente_data.get("email", "")
                email_cliente = email_cliente.strip() if email_cliente else ""
                telefone_cliente = ""

                # Pegar telefone dos contatos
                if "contatos" in cliente_data:
                    contatos = cliente_data["contatos"]
                    if contatos:
                        for contato in contatos:
                            if contato.get("tipo") == "telefone":
                                telefone_cliente = contato.get("valor", "").strip()
                                break

                # Verificar se já existe contato com os mesmos dados
                existing_contact = PersonsContacts.objects.filter(
                    person=person,
                    email=email_cliente or None,
                    phone=telefone_cliente or None,
                ).first()

                # Só criar novo contato se não existir um com os mesmos dados
                if not existing_contact and (email_cliente or telefone_cliente):
                    # Tratar email vazio como None
                    email_final = email_cliente if email_cliente else None
                    PersonsContacts.objects.create(
                        email=email_final,
                        phone=telefone_cliente,
                        person=person,
                        created_by=request.user,
                    )

                # Processar endereços
                if "enderecos" in cliente_data:
                    # Manter apenas o endereço mais recente (último da lista)
                    enderecos = cliente_data["enderecos"]
                    if enderecos:
                        # Pegar apenas o último endereço da lista
                        endereco = enderecos[-1]

                        # Buscar cidade
                        city, _ = City.objects.get_or_create(
                            name=endereco["cidade"].upper(),
                            defaults={
                                "code": "00000",
                                "uf": "SP",
                                "created_by": request.user,
                            },
                        )

                        # Verificar se endereço já existe (incluindo complemento)
                        existing_address = PersonsAdresses.objects.filter(
                            person=person,
                            street=endereco.get("rua") or "",
                            number=endereco.get("numero") or "",
                            cep=endereco.get("cep") or "",
                            neighborhood=endereco.get("bairro") or "",
                            complemento=endereco.get("complemento") or "",
                            city=city,
                        ).first()

                        # Só criar se não existir um endereço idêntico
                        if not existing_address:
                            # Criar novo endereço (mantém histórico)
                            PersonsAdresses.objects.create(
                                person=person,
                                street=endereco.get("rua") or "",
                                number=endereco.get("numero") or "",
                                cep=endereco.get("cep") or "",
                                neighborhood=endereco.get("bairro") or "",
                                complemento=endereco.get("complemento") or "",
                                city=city,
                                created_by=request.user,
                            )

            # Remover itens existentes
            service_order.items.all().delete()

            if "ordem_servico" in data and "itens" in data["ordem_servico"]:
                for item in data["ordem_servico"]["itens"]:
                    def clean_field(value):
                        if value is None:
                            return None
                        if isinstance(value, str):
                            return value.strip() if value.strip() else None
                        return value

                    temp_product = TemporaryProduct.objects.create(
                        product_type=item["tipo"],
                        size=clean_field(item.get("numero")),
                        sleeve_length=clean_field(item.get("manga")),
                        color=clean_field(item.get("cor")),
                        brand=clean_field(item.get("marca")),
                        description=clean_field(item.get("extras")),
                        venda=item.get("venda", False),
                        created_by=request.user,
                    )

                    # Campos específicos para calça
                    if item["tipo"] == "calca":
                        temp_product.waist_size = clean_field(item.get("cintura"))
                        temp_product.leg_length = clean_field(item.get("perna"))
                        temp_product.ajuste_cintura = clean_field(
                            item.get("ajuste_cintura")
                        )
                        temp_product.ajuste_comprimento = clean_field(
                            item.get("ajuste_comprimento")
                        )
                        temp_product.save()

                    # Criar item da OS
                    ServiceOrderItem.objects.create(
                        service_order=service_order,
                        temporary_product=temp_product,
                        adjustment_needed=bool(clean_field(item.get("ajuste"))),
                        adjustment_notes=clean_field(item.get("ajuste")),
                        created_by=request.user,
                    )

            if "ordem_servico" in data and "acessorios" in data["ordem_servico"]:
                for acessorio in data["ordem_servico"]["acessorios"]:
                    def clean_field(value):
                        if value is None:
                            return None
                        if isinstance(value, str):
                            return value.strip() if value.strip() else None
                        return value

                    temp_product = TemporaryProduct.objects.create(
                        product_type=acessorio["tipo"],
                        size=clean_field(acessorio.get("numero")),
                        color=clean_field(acessorio.get("cor")),
                        brand=clean_field(acessorio.get("marca")),
                        description=clean_field(acessorio.get("descricao")),
                        extensor=acessorio.get("extensor", False),
                        venda=acessorio.get("venda", False),
                        created_by=request.user,
                    )

                    # Criar item da OS
                    ServiceOrderItem.objects.create(
                        service_order=service_order,
                        temporary_product=temp_product,
                        created_by=request.user,
                    )

            service_order.save()

            # Mover para EM_PRODUCAO apenas se for atualização COMPLETA
            # Considera completa se tem itens ou acessórios (não é apenas employee_id ou datas)
            is_full_update = False
            if "ordem_servico" in data:
                os_data = data["ordem_servico"]
                # Verifica se tem itens ou acessórios (atualização completa)
                if "itens" in os_data or "acessorios" in os_data:
                    is_full_update = True

            if is_full_update:
                # Atualização completa - mover para EM_PRODUCAO
                em_producao_phase = ServiceOrderPhase.objects.filter(
                    name="EM_PRODUCAO"
                ).first()

                if em_producao_phase and service_order.service_order_phase:
                    # Só mover se não estiver já em EM_PRODUCAO, AGUARDANDO_RETIRADA ou fases posteriores
                    current_phase_name = service_order.service_order_phase.name
                    if current_phase_name not in [
                        "EM_PRODUCAO",
                        "AGUARDANDO_RETIRADA",
                        "AGUARDANDO_DEVOLUCAO",
                        "FINALIZADO",
                        "RECUSADA",
                    ]:
                        service_order.service_order_phase = em_producao_phase
                        service_order.production_date = date.today()
                        service_order.save()

            service_order.update(request.user)

            return Response(
                {
                    "success": True,
                    "message": "OS atualizada com sucesso",
                    "service_order": ServiceOrderSerializer(service_order).data,
                }
            )

        except ServiceOrder.DoesNotExist:
            return Response(
                {"error": "Ordem de serviço não encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"Erro ao atualizar OS: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Lista de ordens de serviço",
    description="Retorna a lista de ordens de serviço com filtros opcionais",
    parameters=[
        OpenApiParameter(
            name="phase",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filtrar por fase da ordem de serviço",
            required=False,
        )
    ],
    responses={200: ServiceOrderSerializer(many=True)},
)
class ServiceOrderListAPIView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderSerializer

    def get_queryset(self):
        queryset = ServiceOrder.objects.select_related(
            "renter", "employee", "attendant", "service_order_phase", "event"
        ).prefetch_related("items")

        # Filtros
        phase = self.request.GET.get("phase")
        if phase:
            queryset = queryset.filter(service_order_phase__name__icontains=phase)

        return queryset


@extend_schema(
    tags=["service-orders"],
    summary="Detalhes da ordem de serviço",
    description="Retorna os detalhes completos de uma ordem de serviço com a mesma estrutura da listagem por fase",
    responses={
        200: ServiceOrderListByPhaseSerializer,
        404: {"description": "Ordem de serviço não encontrada"},
    },
)
class ServiceOrderDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderListByPhaseSerializer

    def get(self, request, order_id):
        """Detalhes de uma ordem de serviço com estrutura normalizada"""
        try:
            # Buscar a ordem de serviço específica
            order = (
                ServiceOrder.objects.select_related(
                    "renter",
                    "employee",
                    "attendant",
                    "renter__person_type",
                    "event",
                )
                .prefetch_related("items__temporary_product", "items__product")
                .get(id=order_id)
            )

            # Dados do cliente
            client_data = {
                "id": order.renter.id,
                "name": order.renter.name,
                "cpf": order.renter.cpf,
                "person_type": (
                    {
                        "id": order.renter.person_type.id,
                        "type": order.renter.person_type.type,
                    }
                    if order.renter.person_type
                    else None
                ),
            }

            # Contatos do cliente (apenas o mais recente)
            contact = (
                order.renter.contacts.filter(date_created__isnull=False)
                .order_by("-date_created", "-id")
                .first()
            )
            if not contact:
                # Se não houver contato com date_created, buscar o mais recente por ID
                contact = order.renter.contacts.order_by("-id").first()

            client_data["contacts"] = []
            if contact:
                client_data["contacts"].append(
                    {
                        "id": contact.id,
                        "email": contact.email,
                        "phone": contact.phone,
                    }
                )

            # Endereços do cliente (apenas o mais recente)
            address = (
                order.renter.personsadresses_set.filter(date_created__isnull=False)
                .order_by("-date_created", "-id")
                .first()
            )
            if not address:
                # Se não houver endereço com date_created, buscar o mais recente por ID
                address = order.renter.personsadresses_set.order_by("-id").first()
            client_data["addresses"] = []
            if address:
                city_data = None
                if address.city:
                    city_data = {
                        "id": address.city.id,
                        "name": address.city.name,
                        "uf": address.city.uf,
                    }

                client_data["addresses"].append(
                    {
                        "id": address.id,
                        "cep": address.cep,
                        "rua": address.street,
                        "numero": address.number,
                        "bairro": address.neighborhood,
                        "complemento": address.complemento or "",
                        "cidade": city_data,
                    }
                )

            # Dados da OS
            order_data = {
                "id": order.id,
                "total_value": order.total_value,
                "advance_payment": order.advance_payment,
                "remaining_payment": order.remaining_payment,
                "employee_name": order.employee.name if order.employee else "",
                "attendant_name": order.attendant.name if order.attendant else "",
                "order_date": order.order_date,
                "prova_date": order.prova_date,
                "retirada_date": order.retirada_date,
                "devolucao_date": order.devolucao_date,
                "production_date": order.production_date,
                "data_recusa": order.data_recusa,
                "data_finalizado": order.data_finalizado,
                "client": client_data,
                "justification_refusal": order.justification_refusal,
                "event_date": (
                    order.event.event_date.date()
                    if order.event
                    and order.event.event_date
                    and hasattr(order.event.event_date, "date")
                    else order.event.event_date if order.event else None
                ),
                "event_name": order.event.name if order.event else None,
            }

            # Processar itens da OS (mesma lógica do ServiceOrderListByPhaseAPIView)
            itens = []
            acessorios = []

            for item in order.items.all():
                # Determinar se é produto temporário ou produto real
                temp_product = item.temporary_product
                product = item.product

                if temp_product:
                    # Produto temporário
                    if temp_product.product_type in [
                        "paleto",
                        "camisa",
                        "calca",
                        "colete",
                    ]:
                        # Item de roupa
                        item_data = {
                            "tipo": temp_product.product_type,
                            "cor": temp_product.color or "",
                            "extras": temp_product.extras
                            or temp_product.description
                            or "",
                            "venda": temp_product.venda or False,
                            "extensor": False,  # Extensor só para passante
                        }

                        # Campos específicos por tipo
                        if temp_product.product_type in ["paleto", "camisa"]:
                            item_data.update(
                                {
                                    "numero": temp_product.size or "",
                                    "manga": temp_product.sleeve_length or "",
                                    "marca": temp_product.brand or "",
                                    "ajuste": item.adjustment_notes or "",
                                }
                            )
                        elif temp_product.product_type == "calca":
                            item_data.update(
                                {
                                    "numero": temp_product.size,
                                    "cintura": temp_product.waist_size or "",
                                    "perna": temp_product.leg_length or "",
                                    "marca": temp_product.brand or "",
                                    "ajuste_cintura": temp_product.ajuste_cintura or "",
                                    "ajuste_comprimento": temp_product.ajuste_comprimento
                                    or "",
                                }
                            )
                        elif temp_product.product_type == "colete":
                            item_data.update({"marca": temp_product.brand or ""})

                        itens.append(item_data)
                    else:
                        # Acessório
                        acessorio_data = {
                            "tipo": temp_product.product_type,
                            "numero": temp_product.size or "",
                            "cor": temp_product.color or "",
                            "descricao": temp_product.description or "",
                            "marca": temp_product.brand or "",
                            "extensor": temp_product.extensor or False,
                            "venda": temp_product.venda or False,
                        }
                        acessorios.append(acessorio_data)

                elif product:
                    # Produto real do estoque
                    if product.tipo.lower() in [
                        "paleto",
                        "camisa",
                        "calça",
                        "colete",
                    ]:
                        # Item de roupa
                        item_data = {
                            "tipo": product.tipo.lower(),
                            "cor": product.cor or "",
                            "extras": product.nome_produto or "",
                            "venda": False,  # Produtos do estoque não são vendidos
                            "extensor": False,
                        }

                        # Campos específicos por tipo
                        if product.tipo.lower() in ["paleto", "camisa"]:
                            item_data.update(
                                {
                                    "numero": (
                                        str(product.tamanho) if product.tamanho else ""
                                    ),
                                    "manga": "",
                                    "marca": product.marca or "",
                                    "ajuste": item.adjustment_notes or "",
                                }
                            )
                        elif product.tipo.lower() == "calça":
                            item_data.update(
                                {
                                    "numero": (
                                        str(product.tamanho) if product.tamanho else ""
                                    ),
                                    "cintura": "",
                                    "perna": "",
                                    "marca": product.marca or "",
                                    "ajuste_cintura": "",
                                    "ajuste_comprimento": "",
                                }
                            )
                        elif product.tipo.lower() == "colete":
                            item_data.update({"marca": product.marca or ""})

                        itens.append(item_data)
                    else:
                        # Acessório
                        acessorio_data = {
                            "tipo": product.tipo.lower(),
                            "numero": (str(product.tamanho) if product.tamanho else ""),
                            "cor": product.cor or "",
                            "descricao": product.nome_produto or "",
                            "marca": product.marca or "",
                            "extensor": False,  # Produtos do estoque não têm extensor
                            "venda": False,
                        }
                        acessorios.append(acessorio_data)

            # Dados da ordem de serviço no formato esperado pelo frontend
            ordem_servico_data = {
                "data_pedido": order.order_date,
                "data_evento": (
                    order.event.event_date.date()
                    if order.event
                    and order.event.event_date
                    and hasattr(order.event.event_date, "date")
                    else order.event.event_date if order.event else None
                ),
                "data_retirada": order.retirada_date,
                "data_devolucao": order.devolucao_date,
                "modalidade": order.service_type or "Aluguel",
                "itens": itens,
                "acessorios": acessorios,
                "pagamento": {
                    "total": float(order.total_value) if order.total_value else 0,
                    "sinal": (
                        float(order.advance_payment) if order.advance_payment else 0
                    ),
                    "restante": (
                        float(order.remaining_payment) if order.remaining_payment else 0
                    ),
                    "forma_pagamento": order.payment_method or "",
                },
            }

            # Adicionar dados completos ao response
            order_data.update({"ordem_servico": ordem_servico_data})

            return Response(order_data)

        except ServiceOrder.DoesNotExist:
            return Response(
                {"error": "Ordem de serviço não encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Marcar ordem de serviço como paga",
    description="Marca uma ordem de serviço como paga, alterando sua fase para FINALIZADO e registrando a data de devolução",
    responses={
        200: {
            "description": "Ordem de serviço marcada como paga e finalizada",
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
                "data_devolvido": {"type": "string", "format": "date-time"},
            },
        },
        404: {"description": "Ordem de serviço não encontrada"},
        400: {"description": "OS não pode ser marcada como paga"},
        500: {"description": "Erro interno do servidor"},
    },
)
class ServiceOrderMarkPaidAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderMarkPaidSerializer

    def post(self, request, order_id):
        """Marcar ordem de serviço como paga e concluída"""
        try:
            service_order = get_object_or_404(ServiceOrder, id=order_id)

            if not service_order.service_order_phase:
                return Response(
                    {"error": "OS não possui fase definida."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if service_order.service_order_phase.name == "FINALIZADO":
                return Response(
                    {"error": "OS já está finalizada."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if service_order.service_order_phase.name != "AGUARDANDO_DEVOLUCAO":
                return Response(
                    {
                        "error": "OS deve estar na fase AGUARDANDO_DEVOLUCAO para ser marcada como paga."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            finalizado_phase, created = ServiceOrderPhase.objects.get_or_create(
                name="FINALIZADO", defaults={"created_by": request.user}
            )

            user_person = getattr(request.user, "person", None)
            is_admin = user_person and user_person.person_type.type == "ADMINISTRADOR"
            is_employee = (
                user_person
                and service_order.employee
                and user_person.id == service_order.employee.id
            )
            is_attendant = (
                user_person
                and service_order.attendant
                and user_person.id == service_order.attendant.id
            )

            if not (is_admin or is_employee or is_attendant):
                return Response(
                    {
                        "error": "Apenas o atendente responsável, recepcionista ou um administrador pode marcar uma OS como paga."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            service_order.service_order_phase = finalizado_phase
            service_order.data_devolvido = timezone.now()
            service_order.data_finalizado = date.today()
            service_order.save()

            return Response(
                {
                    "success": True,
                    "message": "OS marcada como paga e finalizada com sucesso",
                    "data_devolvido": service_order.data_devolvido,
                }
            )

        except ServiceOrder.DoesNotExist:
            return Response(
                {"error": "Ordem de serviço não encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"Erro ao marcar OS como paga: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Recusar ordem de serviço",
    description="Recusa uma ordem de serviço, alterando sua fase para RECUSADA. Apenas OS nas fases PENDENTE ou AGUARDANDO_RETIRADA, ou OS sem fase definida (recusadas na triagem) podem ser recusadas. Requer justificativa obrigatória.",
    responses={
        200: {
            "description": "Ordem de serviço recusada",
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
            },
        },
        400: {
            "description": "OS não pode ser recusada na fase atual ou justificativa não fornecida"
        },
        403: {
            "description": "Permissão negada - apenas atendente responsável, administrador ou usuários de triagem"
        },
        404: {"description": "Ordem de serviço não encontrada"},
    },
)
class ServiceOrderRefuseAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderRefuseSerializer

    def post(self, request, order_id):
        """Recusar ordem de serviço"""
        try:
            from .models import RefusalReason

            service_order = get_object_or_404(ServiceOrder, id=order_id)

            justification_raw = request.data.get("justification_refusal")
            justification = justification_raw.strip() if justification_raw else None

            reason_id = request.data.get("justification_reason_id")

            if not reason_id:
                return Response(
                    {"error": "Motivo de recusa é obrigatório."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                refusal_reason = RefusalReason.objects.get(id=reason_id)
            except RefusalReason.DoesNotExist:
                return Response(
                    {"error": "Motivo de recusa inválido."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            refused_phase, created = ServiceOrderPhase.objects.get_or_create(
                name="RECUSADA", defaults={"created_by": request.user}
            )

            current_phase = service_order.service_order_phase
            allowed_phases = ["PENDENTE", "EM_PRODUCAO", "AGUARDANDO_RETIRADA"]

            if current_phase and current_phase.name not in allowed_phases:
                return Response(
                    {
                        "error": f"OS não pode ser recusada na fase atual ({current_phase.name}). Apenas fases {', '.join(allowed_phases)} ou OS sem fase definida podem ser recusadas."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            user_person = getattr(request.user, "person", None)
            is_admin = user_person and user_person.person_type.type == "ADMINISTRADOR"
            is_employee = (
                user_person
                and service_order.employee
                and user_person.id == service_order.employee.id
            )

            if not (is_admin or is_employee or not service_order.employee):
                return Response(
                    {
                        "error": "Apenas o atendente responsável, um administrador, ou usuários autorizados para triagem podem recusar uma OS."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            service_order.service_order_phase = refused_phase
            service_order.justification_refusal = justification
            service_order.justification_reason = refusal_reason
            service_order.data_recusa = date.today()
            service_order.cancel(request.user)  # Atualiza date_canceled e canceled_by

            return Response(
                {
                    "success": True,
                    "message": "OS recusada",
                    "reason": refusal_reason.name,
                }
            )

        except ServiceOrder.DoesNotExist:
            return Response(
                {"error": "Ordem de serviço não encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"Erro ao recusar OS: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Listar motivos de recusa",
    description="Retorna a lista de motivos de recusa/cancelamento disponíveis",
    responses={
        200: {
            "description": "Lista de motivos de recusa",
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "ID do motivo"},
                    "name": {"type": "string", "description": "Nome do motivo"},
                },
            },
        }
    },
)
class RefusalReasonsListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Lista todos os motivos de recusa/cancelamento"""
        try:
            from .models import RefusalReason
            from .serializers import RefusalReasonSerializer

            reasons = RefusalReason.objects.all().order_by("name")
            serializer = RefusalReasonSerializer(reasons, many=True)

            return Response(serializer.data)

        except Exception as e:
            return Response(
                {"error": f"Erro ao listar motivos de recusa: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Marcar ordem de serviço como retirada",
    description="Marca uma ordem de serviço como retirada, alterando sua fase para AGUARDANDO_DEVOLUCAO e registrando a data de retirada",
    responses={
        200: {
            "description": "Ordem de serviço marcada como retirada",
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
            },
        },
        404: {"description": "Ordem de serviço não encontrada"},
        400: {"description": "OS não pode ser marcada como retirada"},
        500: {"description": "Erro interno do servidor"},
    },
)
class ServiceOrderMarkRetrievedAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderMarkRetrievedSerializer

    def post(self, request, order_id):
        """Marcar ordem de serviço como retirada"""
        try:
            service_order = get_object_or_404(ServiceOrder, id=order_id)

            # Verificar se a OS pode ser marcada como retirada
            if not service_order.service_order_phase:
                return Response(
                    {"error": "OS não possui fase definida."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verificar se já está na fase AGUARDANDO_DEVOLUCAO
            if service_order.service_order_phase.name == "AGUARDANDO_DEVOLUCAO":
                return Response(
                    {"error": "OS já está aguardando devolução."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verificar se já está finalizada
            if service_order.service_order_phase.name == "FINALIZADO":
                return Response(
                    {"error": "OS já está finalizada."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verificar se está na fase EM_PRODUCAO ou AGUARDANDO_RETIRADA
            if service_order.service_order_phase.name not in [
                "EM_PRODUCAO",
                "AGUARDANDO_RETIRADA",
            ]:
                return Response(
                    {
                        "error": "OS deve estar na fase EM_PRODUCAO ou AGUARDANDO_RETIRADA para ser marcada como retirada."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Buscar ou criar fase "AGUARDANDO_DEVOLUCAO"
            aguardando_devolucao_phase, created = (
                ServiceOrderPhase.objects.get_or_create(
                    name="AGUARDANDO_DEVOLUCAO", defaults={"created_by": request.user}
                )
            )

            user_person = getattr(request.user, "person", None)
            is_admin = user_person and user_person.person_type.type == "ADMINISTRADOR"
            is_employee = (
                user_person
                and service_order.employee
                and user_person.id == service_order.employee.id
            )
            is_attendant = (
                user_person
                and service_order.attendant
                and user_person.id == service_order.attendant.id
            )

            if not (is_admin or is_employee or is_attendant):
                return Response(
                    {
                        "error": "Apenas o atendente responsável, recepcionista ou um administrador pode marcar uma OS como retirada."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data

            if data.get("receive_remaining_payment"):
                remaining_amount = data.get("remaining_amount") or service_order.remaining_payment or Decimal("0")
                payment_forms = data.get("payment_forms", [])

                if not payment_forms:
                    return Response(
                        {"error": "payment_forms é obrigatório quando receive_remaining_payment é True"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                total_paid = sum(Decimal(item["amount"]) for item in payment_forms)
                if total_paid != remaining_amount:
                    return Response(
                        {"error": f"Total dos pagamentos ({total_paid}) não corresponde ao valor restante ({remaining_amount})"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                service_order.advance_payment = (service_order.advance_payment or Decimal("0")) + total_paid

                current_details = service_order.payment_details or []
                formas_pagamento = []
                for item in payment_forms:
                    current_details.append({
                        "amount": float(item["amount"]),
                        "forma_pagamento": item["forma_pagamento"],
                        "tipo": "restante",
                        "data": timezone.now().isoformat()
                    })
                    if item["forma_pagamento"] not in formas_pagamento:
                        formas_pagamento.append(item["forma_pagamento"])

                service_order.payment_details = current_details

                formas_str = ", ".join(formas_pagamento)
                if service_order.payment_method:
                    service_order.payment_method = f"{service_order.payment_method}, {formas_str}"
                else:
                    service_order.payment_method = formas_str

            service_order.service_order_phase = aguardando_devolucao_phase
            service_order.data_retirado = timezone.now()
            service_order.save()

            return Response(
                {
                    "success": True,
                    "message": "OS marcada como retirada com sucesso",
                    "data_retirado": service_order.data_retirado,
                }
            )

        except ServiceOrder.DoesNotExist:
            return Response(
                {"error": "Ordem de serviço não encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"Erro ao marcar OS como retirada: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Marcar ordem de serviço como pronta para retirada",
    description="Marca uma ordem de serviço como pronta, movendo da fase EM_PRODUCAO para AGUARDANDO_RETIRADA",
    responses={
        200: {
            "description": "Ordem de serviço marcada como pronta",
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
            },
        },
        404: {"description": "Ordem de serviço não encontrada"},
        400: {"description": "OS não pode ser marcada como pronta"},
        500: {"description": "Erro interno do servidor"},
    },
)
class ServiceOrderMarkReadyAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderMarkRetrievedSerializer

    def post(self, request, order_id):
        """Marcar ordem de serviço como pronta para retirada"""
        try:
            service_order = get_object_or_404(ServiceOrder, id=order_id)

            # Verificar se a OS pode ser marcada como pronta
            if not service_order.service_order_phase:
                return Response(
                    {"error": "OS não possui fase definida."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verificar se está na fase EM_PRODUCAO
            if service_order.service_order_phase.name != "EM_PRODUCAO":
                return Response(
                    {
                        "error": "OS deve estar na fase EM_PRODUCAO para ser marcada como pronta."
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Buscar ou criar fase "AGUARDANDO_RETIRADA"
            aguardando_retirada_phase, created = (
                ServiceOrderPhase.objects.get_or_create(
                    name="AGUARDANDO_RETIRADA", defaults={"created_by": request.user}
                )
            )

            user_person = getattr(request.user, "person", None)
            is_admin = user_person and user_person.person_type.type == "ADMINISTRADOR"
            is_employee = (
                user_person
                and service_order.employee
                and user_person.id == service_order.employee.id
            )
            is_attendant = (
                user_person
                and service_order.attendant
                and user_person.id == service_order.attendant.id
            )

            if not (is_admin or is_employee or is_attendant):
                return Response(
                    {
                        "error": "Apenas o atendente responsável, recepcionista ou um administrador pode marcar uma OS como pronta."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Marcar como pronta (mover para AGUARDANDO_RETIRADA)
            service_order.service_order_phase = aguardando_retirada_phase
            service_order.save()

            return Response(
                {
                    "success": True,
                    "message": "OS marcada como pronta para retirada com sucesso",
                }
            )

        except ServiceOrder.DoesNotExist:
            return Response(
                {"error": "Ordem de serviço não encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"Erro ao marcar OS como pronta: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Retornar ordem de serviço para pendente",
    description="Retorna uma ordem de serviço para a fase PENDENTE, permitindo reprocessamento",
    responses={
        200: {
            "description": "Ordem de serviço retornada para pendente",
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
            },
        },
        404: {"description": "Ordem de serviço não encontrada"},
        400: {"description": "OS não pode ser retornada para pendente"},
        403: {"description": "Usuário não autorizado"},
        500: {"description": "Erro interno do servidor"},
    },
)
class ServiceOrderReturnToPendingAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        """Retornar ordem de serviço para pendente"""
        try:
            service_order = get_object_or_404(ServiceOrder, id=order_id)

            # Verificar se a OS possui fase definida
            if not service_order.service_order_phase:
                return Response(
                    {"error": "OS não possui fase definida."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verificar se já está na fase PENDENTE
            if service_order.service_order_phase.name == "PENDENTE":
                return Response(
                    {"error": "OS já está na fase PENDENTE."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Verificar se está finalizada (não permitir retornar)
            if service_order.service_order_phase.name in ["FINALIZADO"]:
                return Response(
                    {"error": "OS finalizada não pode ser retornada para pendente."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Buscar ou criar fase "PENDENTE"
            pendente_phase, created = (
                ServiceOrderPhase.objects.get_or_create(
                    name="PENDENTE", defaults={"created_by": request.user}
                )
            )

            user_person = getattr(request.user, "person", None)
            is_admin = user_person and user_person.person_type.type == "ADMINISTRADOR"
            is_employee = (
                user_person
                and service_order.employee
                and user_person.id == service_order.employee.id
            )
            is_attendant = (
                user_person
                and service_order.attendant
                and user_person.id == service_order.attendant.id
            )

            if not (is_admin or is_employee or is_attendant):
                return Response(
                    {
                        "error": "Apenas o atendente responsável, recepcionista ou um administrador pode retornar uma OS para pendente."
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            # Retornar para pendente
            service_order.service_order_phase = pendente_phase
            # Opcional: limpar datas de produção ou retirada se necessário
            # service_order.production_date = None
            # service_order.data_retirado = None
            service_order.save()

            return Response(
                {
                    "success": True,
                    "message": "OS retornada para pendente com sucesso",
                }
            )

        except ServiceOrder.DoesNotExist:
            return Response(
                {"error": "Ordem de serviço não encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"Erro ao retornar OS para pendente: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Dashboard de ordens de serviço - Relatório de Atendimentos",
    description="""
    Dashboard analítico completo estilo Looker com métricas de atendimentos.
    
    Retorna:
    - KPIs principais: Total Recebido, Total Vendido, Total de Atendimentos, Atendimentos Fechados, Taxa de Conversão
    - Tabela de Taxa de Conversão por Atendente
    - Tabela de Total Vendido por Atendente
    - Gráfico de Atendimentos por Tipo de Cliente (renter_role)
    - Gráfico de Atendimentos por Canal de Origem (came_from)
    
    Filtros disponíveis via query params:
    - data_inicio: Data inicial do período (YYYY-MM-DD)
    - data_fim: Data final do período (YYYY-MM-DD)
    - atendente_id: ID do atendente para filtrar
    - tipo_cliente: Tipo de cliente (PADRINHO, NOIVO, etc.)
    - forma_pagamento: Forma de pagamento
    - canal_origem: Canal de origem (INDICAÇÃO, FACEBOOK, etc.)
    """,
    parameters=[
        OpenApiParameter(
            name="data_inicio",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Data inicial do período (YYYY-MM-DD). Default: início do mês atual",
            required=False,
        ),
        OpenApiParameter(
            name="data_fim",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Data final do período (YYYY-MM-DD). Default: hoje",
            required=False,
        ),
        OpenApiParameter(
            name="atendente_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="ID do atendente para filtrar",
            required=False,
        ),
        OpenApiParameter(
            name="tipo_cliente",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Tipo de cliente (renter_role) para filtrar",
            required=False,
        ),
        OpenApiParameter(
            name="forma_pagamento",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Forma de pagamento para filtrar",
            required=False,
        ),
        OpenApiParameter(
            name="canal_origem",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Canal de origem (came_from) para filtrar",
            required=False,
        ),
    ],
    responses={
        200: ServiceOrderDashboardResponseSerializer,
        500: {"description": "Erro interno do servidor"},
    },
)
class ServiceOrderDashboardAPIView(APIView):
    """
    Dashboard analítico completo estilo Looker - Relatório de Atendimentos
    
    Espelha o dashboard do Looker com:
    - Cards KPIs superiores
    - Tabelas de atendentes (conversão e vendas)
    - Gráficos por tipo de cliente e canal de origem
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Dashboard analítico completo com métricas de ordens de serviço"""
        try:
            # Executar função de avanço de fases
            from .views import advance_service_order_phases
            advance_service_order_phases()

            # ========== PROCESSAR FILTROS ==========
            filters = self._parse_filters(request)
            
            # Datas para cálculos de período
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
            month_start = today.replace(day=1)
            in_10_days = today + timedelta(days=10)
            
            # ========== BUSCAR DADOS BASE ==========
            base_queryset = self._get_base_queryset(filters)
            
            # ========== CALCULAR MÉTRICAS NOVAS (estilo Looker) ==========
            kpis = self._calculate_kpis(base_queryset, filters)
            atendentes_conversao = self._calculate_atendentes_taxa_conversao(base_queryset, filters)
            atendentes_vendido = self._calculate_atendentes_total_vendido(base_queryset, filters)
            grafico_tipo_cliente = self._calculate_grafico_tipo_cliente(base_queryset, filters)
            grafico_canal_origem = self._calculate_grafico_canal_origem(base_queryset, filters)
            grafico_aluguel_venda = self._calculate_grafico_aluguel_venda(base_queryset, filters)
            filtros_disponiveis = self._get_available_filters()
            
            # ========== CALCULAR MÉTRICAS LEGADAS (agenda e resultados) ==========
            status_metrics = self._calculate_status_metrics(today, in_10_days)
            resultados = self._calculate_financial_metrics(today, week_start, month_start)

            return Response(
                {
                    "status": 200,
                    "message": "Dados analíticos recuperados com sucesso",
                    "data": {
                        # Métricas novas (estilo Looker)
                        "kpis": kpis,
                        "atendentes_taxa_conversao": atendentes_conversao,
                        "atendentes_total_vendido": atendentes_vendido,
                        "grafico_tipo_cliente": grafico_tipo_cliente,
                        "grafico_canal_origem": grafico_canal_origem,
                        "grafico_aluguel_venda": grafico_aluguel_venda,
                        "filtros_disponiveis": filtros_disponiveis,
                        "periodo": {
                            "data_inicio": filters["data_inicio"].isoformat(),
                            "data_fim": filters["data_fim"].isoformat(),
                        },
                        # Métricas legadas (agenda e resultados financeiros)
                        "status": status_metrics,
                        "resultados": resultados,
                    },
                }
            )

        except Exception as e:
            import traceback
            traceback.print_exc()
            return Response(
                {"error": f"Erro ao gerar dashboard: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _parse_filters(self, request):
        """Parse query parameters para filtros"""
        today = date.today()
        month_start = today.replace(day=1)
        
        # Período
        data_inicio_str = request.query_params.get("data_inicio")
        data_fim_str = request.query_params.get("data_fim")
        
        if data_inicio_str:
            try:
                data_inicio = date.fromisoformat(data_inicio_str)
            except ValueError:
                data_inicio = month_start
        else:
            data_inicio = month_start
            
        if data_fim_str:
            try:
                data_fim = date.fromisoformat(data_fim_str)
            except ValueError:
                data_fim = today
        else:
            data_fim = today
        
        # Outros filtros
        atendente_id = request.query_params.get("atendente_id")
        tipo_cliente = request.query_params.get("tipo_cliente")
        forma_pagamento = request.query_params.get("forma_pagamento")
        canal_origem = request.query_params.get("canal_origem")
        
        return {
            "data_inicio": data_inicio,
            "data_fim": data_fim,
            "atendente_id": int(atendente_id) if atendente_id else None,
            "tipo_cliente": tipo_cliente.upper() if tipo_cliente else None,
            "forma_pagamento": forma_pagamento.upper() if forma_pagamento else None,
            "canal_origem": canal_origem.upper() if canal_origem else None,
        }

    def _get_base_queryset(self, filters):
        """Retorna queryset base com filtros aplicados"""
        qs = ServiceOrder.objects.filter(
            order_date__gte=filters["data_inicio"],
            order_date__lte=filters["data_fim"],
        ).select_related("service_order_phase", "employee", "renter")
        
        # Aplicar filtros opcionais
        if filters["atendente_id"]:
            qs = qs.filter(employee_id=filters["atendente_id"])
            
        if filters["tipo_cliente"]:
            qs = qs.filter(renter_role__iexact=filters["tipo_cliente"])
            
        if filters["forma_pagamento"]:
            qs = qs.filter(payment_method__icontains=filters["forma_pagamento"])
            
        if filters["canal_origem"]:
            qs = qs.filter(came_from__iexact=filters["canal_origem"])
        
        return qs

    def _calculate_kpis(self, queryset, filters):
        """
        Calcula KPIs principais do dashboard:
        - Total Recebido: soma de advance_payment + remaining_payment (para OS finalizadas)
        - Total Vendido: soma de total_value das OS confirmadas
        - Total de Atendimentos: contagem total de OS no período
        - Atendimentos Fechados: OS confirmadas (não recusadas/pendentes)
        - Atendimentos Não Fechados: OS recusadas
        - Taxa de Conversão: (fechados / total) * 100
        """
        # Fases que consideramos como "fechado/convertido"
        fases_fechadas = [
            "EM_PRODUCAO",
            "AGUARDANDO_RETIRADA",
            "AGUARDANDO_DEVOLUCAO",
            "FINALIZADO",
        ]
        
        total_atendimentos = queryset.count()
        
        # Atendimentos fechados (confirmados)
        qs_fechados = queryset.filter(service_order_phase__name__in=fases_fechadas)
        atendimentos_fechados = qs_fechados.count()
        
        # Atendimentos não fechados (recusados)
        atendimentos_nao_fechados = queryset.filter(
            service_order_phase__name="RECUSADA"
        ).count()
        
        # Total Vendido (valor das OS confirmadas)
        total_vendido = Decimal("0.00")
        for order in qs_fechados:
            if order.total_value:
                total_vendido += order.total_value
        
        # Total Recebido (sinal + restante para OS finalizadas)
        total_recebido = Decimal("0.00")
        for order in qs_fechados:
            if order.advance_payment:
                total_recebido += order.advance_payment
            # Só soma remaining_payment se a OS estiver finalizada
            if order.service_order_phase and order.service_order_phase.name == "FINALIZADO":
                if order.remaining_payment:
                    total_recebido += order.remaining_payment
        
        # Taxa de conversão
        taxa_conversao = round(
            (atendimentos_fechados / total_atendimentos * 100) if total_atendimentos > 0 else 0,
            2
        )
        
        return {
            "total_recebido": float(total_recebido),
            "total_vendido": float(total_vendido),
            "total_atendimentos": total_atendimentos,
            "atendimentos_fechados": atendimentos_fechados,
            "atendimentos_nao_fechados": atendimentos_nao_fechados,
            "taxa_conversao": taxa_conversao,
        }

    def _calculate_atendentes_taxa_conversao(self, queryset, filters):
        """
        Calcula taxa de conversão por atendente
        Ordenado por taxa de conversão (maior primeiro)
        
        Considera todos os employees que têm OS no período, independente do PersonType.
        O employee é quem está vinculado à OS como atendente responsável.
        """
        fases_fechadas = [
            "EM_PRODUCAO",
            "AGUARDANDO_RETIRADA",
            "AGUARDANDO_DEVOLUCAO",
            "FINALIZADO",
        ]
        
        # Buscar todos os employees distintos que têm OS no período
        employee_ids = queryset.exclude(employee__isnull=True).values_list('employee_id', flat=True).distinct()
        
        result = []
        for employee_id in employee_ids:
            from accounts.models import Person
            try:
                atendente = Person.objects.get(id=employee_id)
            except Person.DoesNotExist:
                continue
            
            qs_atendente = queryset.filter(employee_id=employee_id)
            num_atendimentos = qs_atendente.count()
            
            if num_atendimentos == 0:
                continue
            
            num_fechados = qs_atendente.filter(
                service_order_phase__name__in=fases_fechadas
            ).count()
            
            taxa = round(
                (num_fechados / num_atendimentos * 100) if num_atendimentos > 0 else 0,
                2
            )
            
            result.append({
                "id": atendente.id,
                "nome": atendente.name,
                "taxa_conversao": taxa,
                "num_atendimentos": num_atendimentos,
                "num_fechados": num_fechados,
            })
        
        # Ordenar por taxa de conversão (maior primeiro)
        result.sort(key=lambda x: x["taxa_conversao"], reverse=True)
        
        return result

    def _calculate_atendentes_total_vendido(self, queryset, filters):
        """
        Calcula total vendido por atendente
        Ordenado por total vendido (maior primeiro)
        
        Considera todos os employees que têm OS fechadas no período, independente do PersonType.
        """
        fases_fechadas = [
            "EM_PRODUCAO",
            "AGUARDANDO_RETIRADA",
            "AGUARDANDO_DEVOLUCAO",
            "FINALIZADO",
        ]
        
        # Buscar todos os employees distintos que têm OS fechadas no período
        qs_fechadas = queryset.filter(service_order_phase__name__in=fases_fechadas)
        employee_ids = qs_fechadas.exclude(employee__isnull=True).values_list('employee_id', flat=True).distinct()
        
        result = []
        for employee_id in employee_ids:
            from accounts.models import Person
            try:
                atendente = Person.objects.get(id=employee_id)
            except Person.DoesNotExist:
                continue
            
            qs_atendente = qs_fechadas.filter(employee_id=employee_id)
            num_atendimentos = qs_atendente.count()
            
            if num_atendimentos == 0:
                continue
            
            total_vendido = Decimal("0.00")
            for order in qs_atendente:
                if order.total_value:
                    total_vendido += order.total_value
            
            result.append({
                "id": atendente.id,
                "nome": atendente.name,
                "total_vendido": float(total_vendido),
                "num_atendimentos": num_atendimentos,
            })
        
        # Ordenar por total vendido (maior primeiro)
        result.sort(key=lambda x: x["total_vendido"], reverse=True)
        
        return result

    def _calculate_grafico_tipo_cliente(self, queryset, filters):
        """
        Calcula dados para gráfico de atendimentos por tipo de cliente (renter_role)
        Similar ao gráfico inferior esquerdo do Looker
        """
        fases_fechadas = [
            "EM_PRODUCAO",
            "AGUARDANDO_RETIRADA",
            "AGUARDANDO_DEVOLUCAO",
            "FINALIZADO",
        ]
        
        # Agrupar por renter_role
        tipo_counts = {}
        
        for order in queryset:
            tipo = order.renter_role.upper() if order.renter_role else "NÃO INFORMADO"
            
            if tipo not in tipo_counts:
                tipo_counts[tipo] = {
                    "atendimentos_fechados": 0,
                    "total_vendido": Decimal("0.00"),
                }
            
            # Verificar se está fechado
            if order.service_order_phase and order.service_order_phase.name in fases_fechadas:
                tipo_counts[tipo]["atendimentos_fechados"] += 1
                if order.total_value:
                    tipo_counts[tipo]["total_vendido"] += order.total_value
        
        # Converter para lista ordenada
        result = []
        for tipo, dados in tipo_counts.items():
            result.append({
                "tipo": tipo,
                "atendimentos_fechados": dados["atendimentos_fechados"],
                "total_vendido": float(dados["total_vendido"]),
            })
        
        # Ordenar por atendimentos fechados (maior primeiro)
        result.sort(key=lambda x: x["atendimentos_fechados"], reverse=True)
        
        return result

    def _calculate_grafico_canal_origem(self, queryset, filters):
        """
        Calcula dados para gráfico de atendimentos por canal de origem (came_from)
        Similar ao gráfico inferior direito do Looker
        """
        fases_fechadas = [
            "EM_PRODUCAO",
            "AGUARDANDO_RETIRADA",
            "AGUARDANDO_DEVOLUCAO",
            "FINALIZADO",
        ]
        
        # Agrupar por canal
        canal_counts = {}
        
        for order in queryset:
            canal = order.came_from.upper() if order.came_from else "NÃO INFORMADO"
            
            if canal not in canal_counts:
                canal_counts[canal] = {
                    "atendimentos": 0,
                    "atendimentos_fechados": 0,
                }
            
            canal_counts[canal]["atendimentos"] += 1
            
            # Verificar se está fechado
            if order.service_order_phase and order.service_order_phase.name in fases_fechadas:
                canal_counts[canal]["atendimentos_fechados"] += 1
        
        # Converter para lista ordenada
        result = []
        for canal, dados in canal_counts.items():
            result.append({
                "canal": canal,
                "atendimentos": dados["atendimentos"],
                "atendimentos_fechados": dados["atendimentos_fechados"],
            })
        
        # Ordenar por atendimentos (maior primeiro)
        result.sort(key=lambda x: x["atendimentos"], reverse=True)
        
        return result

    def _calculate_grafico_aluguel_venda(self, queryset, filters):
        """
        Calcula dados para gráfico de valores por tipo de serviço (aluguel vs venda)
        Mostra valores totais de aluguel e venda no período, ignorando 'Aluguel + Venda'
        """
        fases_fechadas = [
            "EM_PRODUCAO",
            "AGUARDANDO_RETIRADA",
            "AGUARDANDO_DEVOLUCAO",
            "FINALIZADO",
        ]
        
        # Agrupar por tipo de serviço
        tipo_counts = {}
        
        for order in queryset:
            tipo = order.service_type
            
            # Mapear apenas Aluguel e Venda, ignorar outros (como Aluguel + Venda, Compra)
            if tipo == "Aluguel":
                tipo_key = "ALUGUEL"
            elif tipo == "Venda":
                tipo_key = "VENDA"
            else:
                continue  # Ignorar outros tipos
            
            if tipo_key not in tipo_counts:
                tipo_counts[tipo_key] = {
                    "tipo": tipo_key,
                    "valor_total": Decimal("0.00"),
                    "quantidade_os": 0,
                    "valor_medio": Decimal("0.00"),
                }
            
            # Só contar valores de OS fechadas
            if order.service_order_phase and order.service_order_phase.name in fases_fechadas:
                if order.total_value:
                    tipo_counts[tipo_key]["valor_total"] += order.total_value
                tipo_counts[tipo_key]["quantidade_os"] += 1
        
        # Calcular valor médio
        result = []
        for tipo, dados in tipo_counts.items():
            if dados["quantidade_os"] > 0:
                dados["valor_medio"] = dados["valor_total"] / dados["quantidade_os"]
            dados["valor_total"] = float(dados["valor_total"])
            dados["valor_medio"] = float(dados["valor_medio"])
            result.append(dados)
        
        # Ordenar por valor total (maior primeiro)
        result.sort(key=lambda x: x["valor_total"], reverse=True)
        
        return result

    def _get_available_filters(self):
        """
        Retorna opções de filtros disponíveis para o frontend
        Busca atendentes a partir dos employees que têm OS, não pelo PersonType.
        """
        from accounts.models import Person
        
        # Atendentes - buscar todos os employees distintos que têm OS
        employee_ids = ServiceOrder.objects.exclude(
            employee__isnull=True
        ).values_list("employee_id", flat=True).distinct()
        
        atendentes = []
        for emp_id in employee_ids:
            try:
                p = Person.objects.get(id=emp_id)
                atendentes.append({"id": p.id, "nome": p.name})
            except Person.DoesNotExist:
                continue
        
        # Ordenar atendentes por nome
        atendentes.sort(key=lambda x: x["nome"])
        
        # Tipos de cliente (valores únicos de renter_role)
        tipos_cliente = list(
            ServiceOrder.objects.exclude(renter_role__isnull=True)
            .exclude(renter_role="")
            .values_list("renter_role", flat=True)
            .distinct()
        )
        tipos_cliente = [t.upper() for t in tipos_cliente if t]
        tipos_cliente = sorted(list(set(tipos_cliente)))
        
        # Formas de pagamento (valores únicos de payment_method)
        formas_pagamento = list(
            ServiceOrder.objects.exclude(payment_method__isnull=True)
            .exclude(payment_method="")
            .values_list("payment_method", flat=True)
            .distinct()
        )
        formas_pagamento = [f.upper() for f in formas_pagamento if f]
        formas_pagamento = sorted(list(set(formas_pagamento)))
        
        # Canais de origem (valores únicos de came_from)
        canais_origem = list(
            ServiceOrder.objects.exclude(came_from__isnull=True)
            .exclude(came_from="")
            .values_list("came_from", flat=True)
            .distinct()
        )
        canais_origem = [c.upper() for c in canais_origem if c]
        canais_origem = sorted(list(set(canais_origem)))
        
        return {
            "atendentes": atendentes,
            "tipos_cliente": tipos_cliente,
            "formas_pagamento": formas_pagamento,
            "canais_origem": canais_origem,
        }

    def _calculate_status_metrics(self, today, in_10_days):
        """Calcula métricas de status e agenda (provas, retiradas, devoluções)"""
        refused_phase = ServiceOrderPhase.objects.filter(name="RECUSADA").first()
        atrasado_phase = ServiceOrderPhase.objects.filter(name="ATRASADO").first()

        status = {
            "em_atraso": {"provas": 0, "retiradas": 0, "devolucoes": 0},
            "hoje": {"provas": 0, "retiradas": 0, "devolucoes": 0},
            "proximos_10_dias": {"provas": 0, "retiradas": 0, "devolucoes": 0},
        }

        # Fases ativas para contagem
        active_phases = [
            "PENDENTE",
            "EM_PRODUCAO",
            "AGUARDANDO_RETIRADA",
            "AGUARDANDO_DEVOLUCAO",
        ]

        # OS em atraso (fase ATRASADO ou RECUSADA com datas)
        atraso_phases = []
        if refused_phase:
            atraso_phases.append(refused_phase)
        if atrasado_phase:
            atraso_phases.append(atrasado_phase)
            
        if atraso_phases:
            for phase in atraso_phases:
                status["em_atraso"]["provas"] += ServiceOrder.objects.filter(
                    service_order_phase=phase, prova_date__isnull=False
                ).count()
                status["em_atraso"]["retiradas"] += ServiceOrder.objects.filter(
                    service_order_phase=phase, retirada_date__isnull=False
                ).count()
                status["em_atraso"]["devolucoes"] += ServiceOrder.objects.filter(
                    service_order_phase=phase, devolucao_date__isnull=False
                ).count()

        # Também contar OS atrasadas pela flag esta_atrasada
        status["em_atraso"]["retiradas"] += ServiceOrder.objects.filter(
            esta_atrasada=True,
            retirada_date__lt=today,
            service_order_phase__name__in=active_phases,
        ).count()
        status["em_atraso"]["devolucoes"] += ServiceOrder.objects.filter(
            esta_atrasada=True,
            devolucao_date__lt=today,
            service_order_phase__name__in=active_phases,
        ).count()

        # OS de hoje
        status["hoje"]["provas"] = ServiceOrder.objects.filter(
            prova_date=today, service_order_phase__name__in=active_phases
        ).count()
        status["hoje"]["retiradas"] = ServiceOrder.objects.filter(
            retirada_date=today, service_order_phase__name__in=active_phases
        ).count()
        status["hoje"]["devolucoes"] = ServiceOrder.objects.filter(
            devolucao_date=today, service_order_phase__name__in=active_phases
        ).count()

        # OS próximos 10 dias
        status["proximos_10_dias"]["provas"] = ServiceOrder.objects.filter(
            prova_date__gt=today,
            prova_date__lte=in_10_days,
            service_order_phase__name__in=active_phases,
        ).count()
        status["proximos_10_dias"]["retiradas"] = ServiceOrder.objects.filter(
            retirada_date__gt=today,
            retirada_date__lte=in_10_days,
            service_order_phase__name__in=active_phases,
        ).count()
        status["proximos_10_dias"]["devolucoes"] = ServiceOrder.objects.filter(
            devolucao_date__gt=today,
            devolucao_date__lte=in_10_days,
            service_order_phase__name__in=active_phases,
        ).count()

        return status

    def _calculate_financial_metrics(self, today, week_start, month_start):
        """Calcula métricas financeiras - dia, semana, mês"""
        finished_phase = ServiceOrderPhase.objects.filter(name="FINALIZADO").first()

        # Fases consideradas como confirmadas (OS fechadas)
        confirmed_phases = [
            "EM_PRODUCAO",
            "AGUARDANDO_RETIRADA",
            "AGUARDANDO_DEVOLUCAO",
            "FINALIZADO",
        ]

        resultados = {
            "dia": {"total_pedidos": 0.00, "total_recebido": 0.00, "numero_pedidos": 0},
            "semana": {"total_pedidos": 0.00, "total_recebido": 0.00, "numero_pedidos": 0},
            "mes": {"total_pedidos": 0.00, "total_recebido": 0.00, "numero_pedidos": 0},
        }

        # Dia - apenas OS confirmadas
        today_orders = ServiceOrder.objects.filter(
            order_date=today,
            service_order_phase__name__in=confirmed_phases,
        )
        for order in today_orders:
            if order.total_value:
                resultados["dia"]["total_pedidos"] += float(order.total_value)
                resultados["dia"]["numero_pedidos"] += 1
            if order.advance_payment:
                resultados["dia"]["total_recebido"] += float(order.advance_payment)
            if order.service_order_phase == finished_phase and order.remaining_payment:
                resultados["dia"]["total_recebido"] += float(order.remaining_payment)

        # Semana - apenas OS confirmadas
        week_orders = ServiceOrder.objects.filter(
            order_date__gte=week_start,
            order_date__lte=today,
            service_order_phase__name__in=confirmed_phases,
        )
        for order in week_orders:
            if order.total_value:
                resultados["semana"]["total_pedidos"] += float(order.total_value)
                resultados["semana"]["numero_pedidos"] += 1
            if order.advance_payment:
                resultados["semana"]["total_recebido"] += float(order.advance_payment)
            if order.service_order_phase == finished_phase and order.remaining_payment:
                resultados["semana"]["total_recebido"] += float(order.remaining_payment)

        # Mês - apenas OS confirmadas
        month_orders = ServiceOrder.objects.filter(
            order_date__gte=month_start,
            order_date__lte=today,
            service_order_phase__name__in=confirmed_phases,
        )
        for order in month_orders:
            if order.total_value:
                resultados["mes"]["total_pedidos"] += float(order.total_value)
                resultados["mes"]["numero_pedidos"] += 1
            if order.advance_payment:
                resultados["mes"]["total_recebido"] += float(order.advance_payment)
            if order.service_order_phase == finished_phase and order.remaining_payment:
                resultados["mes"]["total_recebido"] += float(order.remaining_payment)

        return resultados


class ServiceOrderAttendantMetricsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["service-orders"],
        summary="Métricas por atendente",
        description="Retorna métricas de performance e taxa de conversão por atendente",
        responses={
            200: {
                "description": "Métricas por atendente",
                "type": "object",
                "properties": {
                    "atendentes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "atendente_id": {"type": "integer"},
                                "atendente_nome": {"type": "string"},
                                "dia": {"type": "object"},
                                "semana": {"type": "object"},
                                "mes": {"type": "object"},
                            },
                        },
                    }
                },
            },
            500: {"description": "Erro interno do servidor"},
        },
    )
    def get(self, request):
        """Métricas de performance por atendente"""
        try:
            from accounts.models import Person, PersonType

            today = date.today()
            week_start = today - timedelta(days=today.weekday())
            month_start = today.replace(day=1)

            # Buscar todos os atendentes
            atendente_type = PersonType.objects.filter(type="ATENDENTE").first()
            if not atendente_type:
                return Response({"atendentes": []})

            atendentes = Person.objects.filter(person_type=atendente_type)
            result_data = []

            for atendente in atendentes:
                atendente_data = {
                    "atendente_id": atendente.id,
                    "atendente_nome": atendente.name,
                    "dia": {},
                    "semana": {},
                    "mes": {},
                }

                for periodo, data_inicio in [
                    ("dia", today),
                    ("semana", week_start),
                    ("mes", month_start),
                ]:
                    # OS do atendente no período
                    orders = ServiceOrder.objects.filter(
                        employee=atendente,
                        order_date__gte=data_inicio,
                        order_date__lte=today,
                    )

                    total_atendimentos = orders.count()
                    finalizados = orders.filter(
                        service_order_phase__name="FINALIZADO"
                    ).count()
                    cancelados = orders.filter(
                        service_order_phase__name="RECUSADA"
                    ).count()
                    em_andamento = orders.filter(
                        service_order_phase__name__in=[
                            "PENDENTE",
                            "EM_PRODUCAO",
                            "AGUARDANDO_RETIRADA",
                            "AGUARDANDO_DEVOLUCAO",
                        ]
                    ).count()

                    # Taxa de conversão
                    # Considera sucesso: OS que foram retiradas (AGUARDANDO_DEVOLUCAO),
                    # aguardando retirada (confirmadas), em produção ou finalizadas
                    sucesso = orders.filter(
                        service_order_phase__name__in=[
                            "FINALIZADO",
                            "AGUARDANDO_DEVOLUCAO",
                            "AGUARDANDO_RETIRADA",
                            "EM_PRODUCAO",
                        ]
                    ).count()
                    taxa_conversao = round(
                        (
                            (sucesso / total_atendimentos * 100)
                            if total_atendimentos > 0
                            else 0.0
                        ),
                        2,
                    )

                    # Valores financeiros
                    total_vendido = sum(
                        [
                            float(order.total_value)
                            for order in orders
                            if order.total_value
                        ]
                    )
                    total_recebido = sum(
                        [float(order.advance_payment or 0) for order in orders]
                    )

                    # Vendas (itens marcados como venda)
                    itens_venda = ServiceOrderItem.objects.filter(
                        service_order__employee=atendente,
                        service_order__order_date__gte=data_inicio,
                        service_order__order_date__lte=today,
                        temporary_product__isnull=False,
                        temporary_product__venda=True,
                    ).count()

                    # Canais de aquisição do atendente
                    canais = (
                        ServiceOrder.objects.filter(
                            employee=atendente,
                            order_date__gte=data_inicio,
                            order_date__lte=today,
                            came_from__isnull=False,
                        )
                        .values("came_from")
                        .annotate(total=models.Count("id"))
                        .order_by("-total")
                    )

                    canal_dict = {}
                    for canal_item in canais:
                        canal = canal_item["came_from"] or "NÃO INFORMADO"
                        total = canal_item["total"]
                        percentual = round(
                            (
                                (total / total_atendimentos * 100)
                                if total_atendimentos > 0
                                else 0.0
                            ),
                            2,
                        )
                        canal_dict[canal] = {"total": total, "percentual": percentual}

                    atendente_data[periodo] = {
                        "atendimentos": {
                            "total_atendimentos": total_atendimentos,
                            "finalizados": finalizados,
                            "cancelados": cancelados,
                            "em_andamento": em_andamento,
                        },
                        "conversao": {
                            "taxa_conversao": taxa_conversao,
                            "atendimentos_iniciados": total_atendimentos,
                            "concluidos_sucesso": sucesso,
                        },
                        "financeiro": {
                            "total_vendido": round(total_vendido, 2),
                            "total_recebido": round(total_recebido, 2),
                        },
                        "vendas": {"itens_vendidos": itens_venda},
                        "canais": canal_dict,
                    }

                result_data.append(atendente_data)

            return Response({"atendentes": result_data})

        except Exception as e:
            return Response(
                {"error": f"Erro ao gerar métricas por atendente: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Listar ordens de serviço por fase",
    description="Retorna a lista de ordens de serviço filtradas por fase específica com dados completos do cliente",
    responses={
        200: ServiceOrderListByPhaseSerializer(many=True),
        404: {"description": "Fase não encontrada"},
        500: {"description": "Erro interno do servidor"},
    },
)
class ServiceOrderListByPhaseAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderListByPhaseSerializer

    def get(self, request, phase_name):
        """Listar ordens de serviço por fase com dados completos do cliente"""
        try:
            today = date.today()

            # Função para mover automaticamente para RECUSADA quem passou da data do evento
            def move_to_refused_if_event_passed():
                refused_phase = ServiceOrderPhase.objects.filter(
                    name="RECUSADA"
                ).first()
                if not refused_phase:
                    return

                # Buscar OS que passaram da data do evento e não foram retiradas
                overdue_orders = ServiceOrder.objects.filter(
                    event__event_date__lt=today,
                    data_retirado__isnull=True,  # Não foi retirada
                    service_order_phase__name__in=[
                        "PENDENTE",
                        "EM_PRODUCAO",
                        "AGUARDANDO_DEVOLUCAO",
                        "FINALIZADO",
                        "AGUARDANDO_RETIRADA",
                    ],
                    event__isnull=False,  # Só OS com evento vinculado
                ).exclude(service_order_phase__name="RECUSADA")

                for order in overdue_orders:
                    order.service_order_phase = refused_phase
                    order.justification_refusal = "Cliente não retirou o produto"
                    order.save()
                    print(
                        f"OS {order.id} movida automaticamente para RECUSADA - Cliente não retirou o produto"
                    )

            # Executar verificação automática
            move_to_refused_if_event_passed()

            phase = ServiceOrderPhase.objects.filter(name__icontains=phase_name).first()
            if not phase:
                return Response(
                    {"error": "Fase não encontrada"}, status=status.HTTP_404_NOT_FOUND
                )

            # Base queryset - exclui OSs virtuais
            base_qs = ServiceOrder.objects.filter(is_virtual=False)

            # Filtrar orders baseado na fase
            if phase.name == "ATRASADO":
                # Fase ATRASADO: SOMENTE OS em AGUARDANDO_DEVOLUCAO que estão atrasadas na devolução
                # OS atrasadas em retirada ficam em AGUARDANDO_RETIRADA com flag esta_atrasada=True
                aguardando_devolucao_phase = ServiceOrderPhase.objects.filter(
                    name="AGUARDANDO_DEVOLUCAO"
                ).first()

                orders = (
                    base_qs.filter(
                        models.Q(
                            service_order_phase=aguardando_devolucao_phase,
                            devolucao_date__lt=today,  # Passou da data de devolução
                            event__event_date__gt=today,  # Evento ainda não passou
                            event__isnull=False,  # Só OS com evento vinculado
                        )
                        | models.Q(
                            service_order_phase=aguardando_devolucao_phase,
                            data_devolvido__isnull=True,  # Não foi devolvida
                            event__event_date__lt=today,  # Evento já passou
                            event__isnull=False,  # Só OS com evento vinculado
                        )
                    )
                    .select_related(
                        "renter",
                        "employee",
                        "attendant",
                        "renter__person_type",
                        "event",
                        "justification_reason",
                    )
                    .prefetch_related("items__temporary_product", "items__product")
                )

            elif phase.name == "AGUARDANDO_DEVOLUCAO":
                # Fase AGUARDANDO_DEVOLUCAO: todas as OS nesta fase
                orders = (
                    base_qs.filter(
                        service_order_phase=phase,
                    )
                    .select_related(
                        "renter",
                        "employee",
                        "attendant",
                        "renter__person_type",
                        "event",
                        "justification_reason",
                    )
                    .prefetch_related("items__temporary_product", "items__product")
                )

            elif phase.name == "EM_PRODUCAO":
                # Fase EM_PRODUCAO: todas as OS nesta fase
                orders = (
                    base_qs.filter(
                        service_order_phase=phase,
                    )
                    .select_related(
                        "renter",
                        "employee",
                        "attendant",
                        "renter__person_type",
                        "event",
                        "justification_reason",
                    )
                    .prefetch_related("items__temporary_product", "items__product")
                )

            elif phase.name == "AGUARDANDO_RETIRADA":
                # Fase AGUARDANDO_RETIRADA: todas as OS nesta fase
                # Marcar com flag esta_atrasada=True as que estão atrasadas
                orders = (
                    base_qs.filter(
                        service_order_phase=phase,
                    )
                    .select_related(
                        "renter",
                        "employee",
                        "attendant",
                        "renter__person_type",
                        "event",
                        "justification_reason",
                    )
                    .prefetch_related("items__temporary_product", "items__product")
                )

                # Atualizar flag de atraso para cada OS
                for order in orders:
                    esta_atrasada = False

                    # Verifica se passou da data de retirada
                    if order.retirada_date and order.retirada_date < today:
                        esta_atrasada = True

                    # Verifica se o evento já passou e ainda não foi retirada
                    if (
                        order.event
                        and order.event.event_date
                        and order.event.event_date < today
                        and not order.data_retirado
                    ):
                        esta_atrasada = True

                    # Atualiza a flag se mudou
                    if order.esta_atrasada != esta_atrasada:
                        order.esta_atrasada = esta_atrasada
                        order.save()

            else:
                # Outras fases: comportamento normal
                orders = (
                    base_qs.filter(service_order_phase=phase)
                    .select_related(
                        "renter",
                        "employee",
                        "attendant",
                        "renter__person_type",
                        "event",
                        "justification_reason",
                    )
                    .prefetch_related("items__temporary_product", "items__product")
                )

            data = []
            for order in orders:
                # Dados do cliente
                client_data = {
                    "id": order.renter.id,
                    "name": order.renter.name,
                    "cpf": order.renter.cpf,
                    "person_type": (
                        {
                            "id": order.renter.person_type.id,
                            "type": order.renter.person_type.type,
                        }
                        if order.renter.person_type
                        else None
                    ),
                }

                # Contatos do cliente (apenas o mais recente)
                contact = order.renter.contacts.order_by("-date_created", "-id").first()
                client_data["contacts"] = []
                if contact:
                    client_data["contacts"].append(
                        {
                            "id": contact.id,
                            "email": contact.email,
                            "phone": contact.phone,
                        }
                    )

                # Endereços do cliente (apenas o mais recente)
                address = order.renter.personsadresses_set.order_by(
                    "-date_created", "-id"
                ).first()
                client_data["addresses"] = []
                if address:
                    city_data = None
                    if address.city:
                        city_data = {
                            "id": address.city.id,
                            "name": address.city.name,
                            "uf": address.city.uf,
                        }

                    client_data["addresses"].append(
                        {
                            "id": address.id,
                            "cep": address.cep,
                            "rua": address.street,
                            "numero": address.number,
                            "bairro": address.neighborhood,
                            "complemento": address.complemento or "",
                            "cidade": city_data,
                        }
                    )

                # Dados da OS
                order_data = {
                    "id": order.id,
                    "total_value": order.total_value,
                    "advance_payment": order.advance_payment,
                    "remaining_payment": order.remaining_payment,
                    "esta_atrasada": order.esta_atrasada,
                    "employee_name": order.employee.name if order.employee else "",
                    "attendant_name": order.attendant.name if order.attendant else "",
                    "order_date": order.order_date,
                    "prova_date": order.prova_date,
                    "retirada_date": order.retirada_date,
                    "devolucao_date": order.devolucao_date,
                    "production_date": order.production_date,
                    "data_recusa": order.data_recusa,
                    "data_finalizado": order.data_finalizado,
                    "client": client_data,
                    "justification_refusal": order.justification_refusal,
                    "justification_reason": (
                        order.justification_reason.name
                        if order.justification_reason
                        else None
                    ),
                    "event_date": (
                        order.event.event_date.date()
                        if order.event
                        and order.event.event_date
                        and hasattr(order.event.event_date, "date")
                        else order.event.event_date if order.event else None
                    ),
                    "event_name": order.event.name if order.event else None,
                }

                # Calcular justificativa do atraso para fase ATRASADO
                if phase.name == "ATRASADO":
                    # Para fase ATRASADO, determinar a justificativa baseada nas datas
                    event_date = None
                    if order.event and order.event.event_date:
                        # Garantir que event_date seja datetime.date para comparação
                        if hasattr(order.event.event_date, "date"):
                            event_date = order.event.event_date.date()
                        else:
                            event_date = order.event.event_date

                    if (
                        order.devolucao_date
                        and order.devolucao_date < today
                        and event_date
                        and event_date > today
                    ):
                        order_data["justificativa_atraso"] = (
                            "Cliente ainda não devolveu"
                        )
                    elif (
                        order.retirada_date
                        and order.retirada_date < today
                        and event_date
                        and event_date > today
                    ):
                        order_data["justificativa_atraso"] = "Cliente não retirou"
                    elif (
                        order.data_devolvido is None
                        and event_date
                        and event_date < today
                    ):
                        order_data["justificativa_atraso"] = (
                            "Cliente ainda não devolveu (evento passou)"
                        )
                    else:
                        order_data["justificativa_atraso"] = None
                else:
                    order_data["justificativa_atraso"] = None

                # Processar itens da OS
                itens = []
                acessorios = []

                for item in order.items.all():
                    # Determinar se é produto temporário ou produto real
                    temp_product = item.temporary_product
                    product = item.product

                    if temp_product:
                        # Produto temporário
                        if temp_product.product_type in [
                            "paleto",
                            "camisa",
                            "calca",
                            "colete",
                        ]:
                            # Item de roupa
                            item_data = {
                                "tipo": temp_product.product_type,
                                "cor": temp_product.color or "",
                                "extras": temp_product.extras
                                or temp_product.description
                                or "",
                                "venda": temp_product.venda or False,
                                "extensor": False,  # Extensor só para passante
                            }

                            # Campos específicos por tipo
                            if temp_product.product_type in ["paleto", "camisa"]:
                                item_data.update(
                                    {
                                        "numero": temp_product.size
                                        or "",  # ✅ Campo "numero" retorna o "size" do banco
                                        "manga": temp_product.sleeve_length or "",
                                        "marca": temp_product.brand or "",
                                        "ajuste": item.adjustment_notes or "",
                                    }
                                )
                            elif temp_product.product_type == "calca":
                                item_data.update(
                                    {
                                        "numero": temp_product.size,
                                        "cintura": temp_product.waist_size or "",
                                        "perna": temp_product.leg_length or "",
                                        "marca": temp_product.brand or "",
                                        "ajuste_cintura": temp_product.ajuste_cintura
                                        or "",
                                        "ajuste_comprimento": temp_product.ajuste_comprimento
                                        or "",
                                    }
                                )
                            elif temp_product.product_type == "colete":
                                item_data.update({"marca": temp_product.brand or ""})

                            print(
                                f"DEBUG ITEM: Retornando item - tipo: {item_data['tipo']}, numero: '{item_data.get('numero', '')}'"
                            )
                            itens.append(item_data)
                        else:
                            # Acessório
                            acessorio_data = {
                                "tipo": temp_product.product_type,
                                "numero": temp_product.size
                                or "",  # ✅ Campo "numero" retorna o "size" do banco
                                "cor": temp_product.color or "",
                                "descricao": temp_product.description or "",
                                "marca": temp_product.brand or "",
                                "extensor": temp_product.extensor or False,
                                "venda": temp_product.venda or False,
                            }
                            print(
                                f"DEBUG ACESSORIO: Retornando acessório - tipo: {acessorio_data['tipo']}, numero: '{acessorio_data['numero']}'"
                            )
                            acessorios.append(acessorio_data)

                    elif product:
                        # Produto real do estoque
                        if product.tipo.lower() in [
                            "paleto",
                            "camisa",
                            "calça",
                            "colete",
                        ]:
                            # Item de roupa
                            item_data = {
                                "tipo": product.tipo.lower(),
                                "cor": product.cor or "",
                                "extras": product.nome_produto or "",
                                "venda": False,  # Produtos do estoque não são vendidos
                                "extensor": False,
                            }

                            # Campos específicos por tipo
                            if product.tipo.lower() in ["paleto", "camisa"]:
                                item_data.update(
                                    {
                                        "numero": (
                                            str(product.tamanho)
                                            if product.tamanho
                                            else ""
                                        ),  # ✅ Campo "numero" retorna o "tamanho" do produto do estoque
                                        "manga": "",
                                        "marca": product.marca or "",
                                        "ajuste": item.adjustment_notes or "",
                                    }
                                )
                            elif product.tipo.lower() == "calça":
                                item_data.update(
                                    {
                                        "numero": (
                                            str(product.tamanho)
                                            if product.tamanho
                                            else ""
                                        ),  # ✅ Campo "numero" retorna o "tamanho" do produto do estoque
                                        "cintura": "",
                                        "perna": "",
                                        "marca": product.marca or "",
                                        "ajuste_cintura": "",
                                        "ajuste_comprimento": "",
                                    }
                                )
                            elif product.tipo.lower() == "colete":
                                item_data.update({"marca": product.marca or ""})

                            itens.append(item_data)
                        else:
                            # Acessório
                            acessorio_data = {
                                "tipo": product.tipo.lower(),
                                "numero": (
                                    str(product.tamanho) if product.tamanho else ""
                                ),  # ✅ Campo "numero" retorna o "tamanho" do produto do estoque
                                "cor": product.cor or "",
                                "descricao": product.nome_produto or "",
                                "marca": product.marca or "",
                                "extensor": False,  # Produtos do estoque não têm extensor
                                "venda": False,
                            }
                            acessorios.append(acessorio_data)

                # Dados da ordem de serviço no formato esperado pelo frontend
                ordem_servico_data = {
                    "data_pedido": order.order_date,
                    "data_evento": (
                        order.event.event_date.date()
                        if order.event
                        and order.event.event_date
                        and hasattr(order.event.event_date, "date")
                        else order.event.event_date if order.event else None
                    ),
                    "data_retirada": order.retirada_date,
                    "data_devolucao": order.devolucao_date,
                    "modalidade": order.service_type or "Aluguel",
                    "itens": itens,
                    "acessorios": acessorios,
                    "pagamento": {
                        "total": float(order.total_value) if order.total_value else 0,
                        "sinal": (
                            float(order.advance_payment) if order.advance_payment else 0
                        ),
                        "restante": (
                            float(order.remaining_payment)
                            if order.remaining_payment
                            else 0
                        ),
                    },
                }

                # Adicionar dados completos ao response
                order_data.update({"ordem_servico": ordem_servico_data})

                data.append(order_data)

            return Response(data)

        except Exception as e:
            return Response(
                {"error": f"Erro ao listar OS: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Listar ordens de serviço por fase (V2, paginado)",
    description=(
        "Retorna ordens de serviço filtradas por fase com paginação simples. "
        "Use query params `page` (1-based) e `page_size`. A resposta contém "
        "`count`, `page`, `page_size`, `total_pages` e `results` (lista de ordens no formato do V1)."
    ),
    parameters=[
        OpenApiParameter(
            name="page",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Número da página (1-based)",
            required=False,
        ),
        OpenApiParameter(
            name="page_size",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Número de itens por página",
            required=False,
        ),
        OpenApiParameter(
            name="start_date",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filtrar ordens a partir desta data (inclusive) - formato YYYY-MM-DD",
            required=False,
        ),
        OpenApiParameter(
            name="end_date",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filtrar ordens até esta data (inclusive) - formato YYYY-MM-DD",
            required=False,
        ),
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Pesquisa livre (ILIKE) em id (quando numérico), nome do cliente, CPF, nome do evento, funcionário ou atendente",
            required=False,
        ),
        OpenApiParameter(
            name="ordering",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description=(
                "Campo(s) para ordenacao. Use '-' para decrescente. "
                "Campos: order_date, prova_date, retirada_date, devolucao_date, "
                "total_value, remaining_payment, id, renter__name, event__event_date. "
                "Padrao: -order_date. Exemplo: ?ordering=-total_value,renter__name"
            ),
            required=False,
        ),
    ],
    methods=["GET"],
    responses={
        200: {
            "type": "object",
            "description": "Objeto paginado contendo os resultados e metadados de paginação",
        },
        404: {"description": "Fase não encontrada"},
        500: {"description": "Erro interno do servidor"},
    },
    examples=[
        OpenApiExample(
            "Exemplo paginado (v2)",
            value={
                "count": 2,
                "page": 1,
                "page_size": 20,
                "total_pages": 1,
                "results": [
                    {
                        "id": 123,
                        "total_value": "150.00",
                        "advance_payment": "50.00",
                        "remaining_payment": "100.00",
                        "esta_atrasada": False,
                        "employee_name": "Fulano",
                        "attendant_name": "Beltrano",
                        "order_date": "2025-11-10",
                        "prova_date": None,
                        "retirada_date": None,
                        "devolucao_date": None,
                        "data_recusa": None,
                        "data_finalizado": None,
                        "client": {
                            "id": 1,
                            "name": "Cliente Exemplo",
                            "cpf": "00000000000",
                        },
                        "justification_refusal": None,
                    }
                ],
            },
            response_only=True,
            status_codes=["200"],
        )
    ],
)
class ServiceOrderListByPhaseV2APIView(APIView):
    """Versão V2 com paginação simples para a listagem por fase."""

    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderListByPhaseSerializer

    def get(self, request, phase_name):
        try:
            # Params de paginação
            try:
                page = int(request.GET.get("page", 1))
            except (TypeError, ValueError):
                page = 1

            try:
                page_size = int(request.GET.get("page_size", 20))
            except (TypeError, ValueError):
                page_size = 20

            if page_size <= 0:
                page_size = 20

            today = date.today()

            # Reaplicar a mesma lógica automática de recusa por evento passado
            def move_to_refused_if_event_passed():
                refused_phase = ServiceOrderPhase.objects.filter(
                    name="RECUSADA"
                ).first()
                if not refused_phase:
                    return

                overdue_orders = ServiceOrder.objects.filter(
                    event__event_date__lt=today,
                    data_retirado__isnull=True,
                    service_order_phase__name__in=[
                        "PENDENTE",
                        "EM_PRODUCAO",
                        "AGUARDANDO_DEVOLUCAO",
                        "FINALIZADO",
                        "AGUARDANDO_RETIRADA",
                    ],
                    event__isnull=False,
                ).exclude(service_order_phase__name="RECUSADA")

                for order in overdue_orders:
                    order.service_order_phase = refused_phase
                    order.justification_refusal = "Cliente não retirou o produto"
                    order.save()

            move_to_refused_if_event_passed()

            phase = ServiceOrderPhase.objects.filter(name__icontains=phase_name).first()
            if not phase:
                return Response(
                    {"error": "Fase não encontrada"}, status=status.HTTP_404_NOT_FOUND
                )

            # Base queryset - exclui OSs virtuais
            base_qs = ServiceOrder.objects.filter(is_virtual=False)

            # Filtrar orders baseado na fase (mesma lógica que V1)
            if phase.name == "ATRASADO":
                aguardando_devolucao_phase = ServiceOrderPhase.objects.filter(
                    name="AGUARDANDO_DEVOLUCAO"
                ).first()

                orders_qs = (
                    base_qs.filter(
                        models.Q(
                            service_order_phase=aguardando_devolucao_phase,
                            devolucao_date__lt=today,
                            event__event_date__gt=today,
                            event__isnull=False,
                        )
                        | models.Q(
                            service_order_phase=aguardando_devolucao_phase,
                            data_devolvido__isnull=True,
                            event__event_date__lt=today,
                            event__isnull=False,
                        )
                    )
                    .select_related(
                        "renter",
                        "employee",
                        "attendant",
                        "renter__person_type",
                        "event",
                        "justification_reason",
                    )
                    .prefetch_related("items__temporary_product", "items__product")
                )

            elif phase.name in [
                "AGUARDANDO_DEVOLUCAO",
                "EM_PRODUCAO",
                "AGUARDANDO_RETIRADA",
            ]:
                orders_qs = (
                    base_qs.filter(
                        service_order_phase=phase,
                    )
                    .select_related(
                        "renter",
                        "employee",
                        "attendant",
                        "renter__person_type",
                        "event",
                        "justification_reason",
                    )
                    .prefetch_related("items__temporary_product", "items__product")
                )

                # Para AGUARDANDO_RETIRADA atualizar flag de atraso globalmente
                if phase.name == "AGUARDANDO_RETIRADA":
                    for order in orders_qs:
                        esta_atrasada = False

                        if order.retirada_date and order.retirada_date < today:
                            esta_atrasada = True

                        if (
                            order.event
                            and order.event.event_date
                            and order.event.event_date < today
                            and not order.data_retirado
                        ):
                            esta_atrasada = True

                        if order.esta_atrasada != esta_atrasada:
                            order.esta_atrasada = esta_atrasada
                            order.save()

            else:
                orders_qs = (
                    base_qs.filter(service_order_phase=phase)
                    .select_related(
                        "renter",
                        "employee",
                        "attendant",
                        "renter__person_type",
                        "event",
                        "justification_reason",
                    )
                    .prefetch_related("items__temporary_product", "items__product")
                )

            # Aplicar filtros opcionais de data e pesquisa livre antes da paginação
            start_date = request.GET.get("start_date")
            end_date = request.GET.get("end_date")
            if start_date:
                try:
                    orders_qs = orders_qs.filter(order_date__gte=start_date)
                except Exception:
                    pass
            if end_date:
                try:
                    orders_qs = orders_qs.filter(order_date__lte=end_date)
                except Exception:
                    pass

            # Pesquisa livre (ILIKE) em campos principais
            search = request.GET.get("search")
            if search:
                search = search.strip()
                # Reuse Q and include contacts (phone/email) and product fields (temporary or real)
                q = (
                    models.Q(renter__name__icontains=search)
                    | models.Q(renter__cpf__icontains=search)
                    | models.Q(event__name__icontains=search)
                    | models.Q(employee__name__icontains=search)
                    | models.Q(attendant__name__icontains=search)
                    | models.Q(renter__contacts__phone__icontains=search)
                    | models.Q(renter__contacts__email__icontains=search)
                    | models.Q(items__temporary_product__description__icontains=search)
                    | models.Q(items__temporary_product__extras__icontains=search)
                    | models.Q(items__temporary_product__brand__icontains=search)
                    | models.Q(items__product__nome_produto__icontains=search)
                    | models.Q(items__product__marca__icontains=search)
                )
                if search.isdigit():
                    try:
                        q |= models.Q(id=int(search))
                    except Exception:
                        pass

                # Use distinct to avoid duplicate ServiceOrder rows due to joins
                orders_qs = orders_qs.filter(q).distinct()

            # Ordenacao
            ordering_param = request.GET.get("ordering", "-order_date")
            ALLOWED_ORDERING_FIELDS = {
                'order_date', 'prova_date', 'retirada_date', 'devolucao_date',
                'production_date', 'data_finalizado', 'total_value',
                'remaining_payment', 'id', 'renter__name', 'event__event_date',
            }

            ordering_fields = []
            for field in ordering_param.split(','):
                field = field.strip()
                field_name = field.lstrip('-')
                if field_name in ALLOWED_ORDERING_FIELDS:
                    ordering_fields.append(field)

            if ordering_fields:
                orders_qs = orders_qs.order_by(*ordering_fields)
            else:
                orders_qs = orders_qs.order_by('-order_date')

            # Paginação
            paginator = Paginator(orders_qs, page_size)
            try:
                page_obj = paginator.page(page)
            except EmptyPage:
                return Response({"error": "Página não encontrada"}, status=404)

            results = []
            for order in page_obj.object_list:
                # Reaproveitar construção do payload igual ao V1
                client_data = {
                    "id": order.renter.id,
                    "name": order.renter.name,
                    "cpf": order.renter.cpf,
                    "person_type": (
                        {
                            "id": order.renter.person_type.id,
                            "type": order.renter.person_type.type,
                        }
                        if order.renter.person_type
                        else None
                    ),
                }

                contact = order.renter.contacts.order_by("-date_created", "-id").first()
                client_data["contacts"] = []
                if contact:
                    client_data["contacts"].append(
                        {
                            "id": contact.id,
                            "email": contact.email,
                            "phone": contact.phone,
                        }
                    )

                address = order.renter.personsadresses_set.order_by(
                    "-date_created", "-id"
                ).first()
                client_data["addresses"] = []
                if address:
                    city_data = None
                    if address.city:
                        city_data = {
                            "id": address.city.id,
                            "name": address.city.name,
                            "uf": address.city.uf,
                        }

                    client_data["addresses"].append(
                        {
                            "id": address.id,
                            "cep": address.cep,
                            "rua": address.street,
                            "numero": address.number,
                            "bairro": address.neighborhood,
                            "complemento": address.complemento or "",
                            "cidade": city_data,
                        }
                    )

                order_data = {
                    "id": order.id,
                    "total_value": order.total_value,
                    "advance_payment": order.advance_payment,
                    "remaining_payment": order.remaining_payment,
                    "esta_atrasada": order.esta_atrasada,
                    "employee_name": order.employee.name if order.employee else "",
                    "attendant_name": order.attendant.name if order.attendant else "",
                    "order_date": order.order_date,
                    "prova_date": order.prova_date,
                    "retirada_date": order.retirada_date,
                    "devolucao_date": order.devolucao_date,
                    "production_date": order.production_date,
                    "data_recusa": order.data_recusa,
                    "data_finalizado": order.data_finalizado,
                    "client": client_data,
                    "justification_refusal": order.justification_refusal,
                    "justification_reason": (
                        order.justification_reason.name
                        if order.justification_reason
                        else None
                    ),
                    "event_date": (
                        order.event.event_date.date()
                        if order.event
                        and order.event.event_date
                        and hasattr(order.event.event_date, "date")
                        else order.event.event_date if order.event else None
                    ),
                    "event_name": order.event.name if order.event else None,
                }

                # Calcular justificativa do atraso como no V1
                if phase.name == "ATRASADO":
                    event_date = None
                    if order.event and order.event.event_date:
                        if hasattr(order.event.event_date, "date"):
                            event_date = order.event.event_date.date()
                        else:
                            event_date = order.event.event_date

                    if (
                        order.devolucao_date
                        and order.devolucao_date < today
                        and event_date
                        and event_date > today
                    ):
                        order_data["justificativa_atraso"] = (
                            "Cliente ainda não devolveu"
                        )
                    elif (
                        order.retirada_date
                        and order.retirada_date < today
                        and event_date
                        and event_date > today
                    ):
                        order_data["justificativa_atraso"] = "Cliente não retirou"
                    elif (
                        order.data_devolvido is None
                        and event_date
                        and event_date < today
                    ):
                        order_data["justificativa_atraso"] = (
                            "Cliente ainda não devolveu (evento passou)"
                        )
                    else:
                        order_data["justificativa_atraso"] = None
                else:
                    order_data["justificativa_atraso"] = None

                # Itens e acessórios (mesma lógica resumida)
                itens = []
                acessorios = []
                for item in order.items.all():
                    temp_product = item.temporary_product
                    product = item.product

                    if temp_product:
                        if temp_product.product_type in [
                            "paleto",
                            "camisa",
                            "calca",
                            "colete",
                        ]:
                            item_data = {
                                "tipo": temp_product.product_type,
                                "cor": temp_product.color or "",
                                "extras": temp_product.extras
                                or temp_product.description
                                or "",
                                "venda": temp_product.venda or False,
                                "extensor": False,
                            }
                            if temp_product.product_type in ["paleto", "camisa"]:
                                item_data.update(
                                    {
                                        "numero": temp_product.size or "",
                                        "manga": temp_product.sleeve_length or "",
                                        "marca": temp_product.brand or "",
                                        "ajuste": item.adjustment_notes or "",
                                    }
                                )
                            elif temp_product.product_type == "calca":
                                item_data.update(
                                    {
                                        "numero": temp_product.size,
                                        "cintura": temp_product.waist_size or "",
                                        "perna": temp_product.leg_length or "",
                                        "marca": temp_product.brand or "",
                                        "ajuste_cintura": temp_product.ajuste_cintura
                                        or "",
                                        "ajuste_comprimento": temp_product.ajuste_comprimento
                                        or "",
                                    }
                                )
                            elif temp_product.product_type == "colete":
                                item_data.update({"marca": temp_product.brand or ""})
                            itens.append(item_data)
                        else:
                            acessorio_data = {
                                "tipo": temp_product.product_type,
                                "numero": temp_product.size or "",
                                "cor": temp_product.color or "",
                                "descricao": temp_product.description or "",
                                "marca": temp_product.brand or "",
                                "extensor": temp_product.extensor or False,
                                "venda": temp_product.venda or False,
                            }
                            acessorios.append(acessorio_data)
                    elif product:
                        if product.tipo.lower() in [
                            "paleto",
                            "camisa",
                            "calça",
                            "colete",
                        ]:
                            item_data = {
                                "tipo": product.tipo.lower(),
                                "cor": product.cor or "",
                                "extras": product.nome_produto or "",
                                "venda": False,
                                "extensor": False,
                            }
                            if product.tipo.lower() in ["paleto", "camisa"]:
                                item_data.update(
                                    {
                                        "numero": (
                                            str(product.tamanho)
                                            if product.tamanho
                                            else ""
                                        ),
                                        "manga": "",
                                        "marca": product.marca or "",
                                        "ajuste": item.adjustment_notes or "",
                                    }
                                )
                            elif product.tipo.lower() == "calça":
                                item_data.update(
                                    {
                                        "numero": (
                                            str(product.tamanho)
                                            if product.tamanho
                                            else ""
                                        ),
                                        "cintura": "",
                                        "perna": "",
                                        "marca": product.marca or "",
                                        "ajuste_cintura": "",
                                        "ajuste_comprimento": "",
                                    }
                                )
                            elif product.tipo.lower() == "colete":
                                item_data.update({"marca": product.marca or ""})
                            itens.append(item_data)
                        else:
                            acessorio_data = {
                                "tipo": product.tipo.lower(),
                                "numero": (
                                    str(product.tamanho) if product.tamanho else ""
                                ),
                                "cor": product.cor or "",
                                "descricao": product.nome_produto or "",
                                "marca": product.marca or "",
                                "extensor": False,
                                "venda": False,
                            }
                            acessorios.append(acessorio_data)

                ordem_servico_data = {
                    "data_pedido": order.order_date,
                    "data_evento": (
                        order.event.event_date.date()
                        if order.event
                        and order.event.event_date
                        and hasattr(order.event.event_date, "date")
                        else order.event.event_date if order.event else None
                    ),
                    "data_retirada": order.retirada_date,
                    "data_devolucao": order.devolucao_date,
                    "modalidade": order.service_type or "Aluguel",
                    "itens": itens,
                    "acessorios": acessorios,
                    "pagamento": {
                        "total": float(order.total_value) if order.total_value else 0,
                        "sinal": (
                            float(order.advance_payment) if order.advance_payment else 0
                        ),
                        "restante": (
                            float(order.remaining_payment)
                            if order.remaining_payment
                            else 0
                        ),
                        "forma_pagamento": order.payment_method or "",
                    },
                }

                order_data.update({"ordem_servico": ordem_servico_data})
                results.append(order_data)

            response = {
                "count": paginator.count,
                "page": page,
                "page_size": page_size,
                "total_pages": paginator.num_pages,
                "ordering": ordering_fields if ordering_fields else ['-order_date'],
                "results": results,
            }

            return Response(response)

        except Exception as e:
            return Response(
                {"error": f"Erro ao listar OS (v2): {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Criar OS virtual para lançamento de pagamento",
    description="Cria uma OS virtual apenas para registro de pagamento. Não aparece em listagens de fases ou histórico, apenas no endpoint de finanças.",
    request=VirtualServiceOrderCreateSerializer,
    responses={
        201: {"description": "OS virtual criada com sucesso"},
        400: {"description": "Dados inválidos"},
        404: {"description": "Cliente não encontrado"},
        500: {"description": "Erro interno do servidor"},
    },
    examples=[
        OpenApiExample(
            "Exemplo de requisição",
            value={
                "renter_id": 123,
                "total_value": "500.00",
                "sinal": {
                    "amount": "200.00",
                    "forma_pagamento": "pix",
                    "data": "2025-11-10T10:00:00"
                },
                "restante": {
                    "amount": "300.00",
                    "forma_pagamento": "debito",
                    "data": "2025-11-15T14:30:00"
                },
                "observations": "Pagamento retroativo"
            },
            request_only=True,
        )
    ],
)
class VirtualServiceOrderCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = VirtualServiceOrderCreateSerializer

    def post(self, request):
        """Criar OS virtual para lançamento de pagamento"""
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data

            renter = None
            if data.get("renter_id"):
                try:
                    renter = Person.objects.get(id=data["renter_id"])
                except Person.DoesNotExist:
                    return Response(
                        {"error": "Cliente não encontrado"},
                        status=status.HTTP_404_NOT_FOUND,
                    )

            payment_details = []
            advance_payment = Decimal("0")
            payment_methods = []

            if data.get("sinal"):
                sinal = data["sinal"]
                sinal_amount = Decimal(str(sinal["amount"]))
                sinal_data = sinal.get("data") or timezone.now()
                if isinstance(sinal_data, str):
                    sinal_data_str = sinal_data
                else:
                    sinal_data_str = sinal_data.isoformat()

                payment_details.append({
                    "amount": float(sinal_amount),
                    "forma_pagamento": sinal["forma_pagamento"],
                    "tipo": "sinal",
                    "data": sinal_data_str
                })
                advance_payment += sinal_amount
                if sinal["forma_pagamento"] not in payment_methods:
                    payment_methods.append(sinal["forma_pagamento"])

            if data.get("restante"):
                restante = data["restante"]
                restante_amount = Decimal(str(restante["amount"]))
                restante_data = restante.get("data") or timezone.now()
                if isinstance(restante_data, str):
                    restante_data_str = restante_data
                else:
                    restante_data_str = restante_data.isoformat()

                payment_details.append({
                    "amount": float(restante_amount),
                    "forma_pagamento": restante["forma_pagamento"],
                    "tipo": "restante",
                    "data": restante_data_str
                })
                advance_payment += restante_amount
                if restante["forma_pagamento"] not in payment_methods:
                    payment_methods.append(restante["forma_pagamento"])

            service_order = ServiceOrder.objects.create(
                renter=renter,
                order_date=timezone.now().date(),
                total_value=data["total_value"],
                advance_payment=advance_payment,
                payment_details=payment_details,
                payment_method=", ".join(payment_methods) if payment_methods else None,
                observations=data.get("observations", ""),
                is_virtual=True,
                created_by=request.user,
            )

            return Response(
                {
                    "success": True,
                    "message": "OS virtual criada com sucesso",
                    "service_order_id": service_order.id,
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as e:
            return Response(
                {"error": f"Erro ao criar OS virtual: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Resumo financeiro - transações por forma de pagamento",
    description=(
        "Retorna resumo financeiro com lista de transações e suas formas de pagamento. "
        "Considera 'sinal' (advance_payment) sempre que presente e 'restante' "
        "(remaining_payment) apenas quando a OS estiver em fase FINALIZADO. "
        "Opcionalmente filtra por intervalo de `start_date` e `end_date` (YYYY-MM-DD) aplicados sobre `order_date`."
    ),
    parameters=[
        OpenApiParameter(
            name="start_date",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filtrar ordens a partir desta data (inclusive)",
            required=False,
        ),
        OpenApiParameter(
            name="end_date",
            type=OpenApiTypes.DATE,
            location=OpenApiParameter.QUERY,
            description="Filtrar ordens até esta data (inclusive)",
            required=False,
        ),
    ],
    responses={200: ServiceOrderFinanceSummarySerializer},
    examples=[
        OpenApiExample(
            "Exemplo de resposta",
            value={
                "total_transactions": 3,
                "total_amount": "450.00",
                "transactions": [
                    {
                        "order_id": 123,
                        "transaction_type": "sinal",
                        "amount": "150.00",
                        "payment_method": "debito",
                        "date": "2025-11-10",
                    },
                    {
                        "order_id": 123,
                        "transaction_type": "sinal",
                        "amount": "150.00",
                        "payment_method": "pix",
                        "date": "2025-11-10",
                    },
                    {
                        "order_id": 123,
                        "transaction_type": "restante",
                        "amount": "150.00",
                        "payment_method": "pix",
                        "date": "2025-11-12",
                    },
                ],
                "totals_by_method": {"debito": "150.00", "pix": "300.00"},
            },
            response_only=True,
            status_codes=["200"],
        )
    ],
)
class ServiceOrderFinanceSummaryAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderFinanceSummarySerializer

    def get(self, request):
        """Retorna total de transações e forma de pagamento de cada uma"""

        start_date = request.GET.get("start_date")
        end_date = request.GET.get("end_date")

        # Paginação
        try:
            page = int(request.GET.get("page", 1))
        except ValueError:
            page = 1
        if page <= 0:
            page = 1

        try:
            page_size = int(request.GET.get("page_size", 50))
        except ValueError:
            page_size = 50
        if page_size <= 0:
            page_size = 50

        orders = ServiceOrder.objects.select_related("service_order_phase")

        if start_date:
            orders = orders.filter(order_date__gte=start_date)
        if end_date:
            orders = orders.filter(order_date__lte=end_date)

        transactions = []
        total_amount = Decimal("0")

        CANDIDATE_EXCLUDED = {"RECUSADA", "CANCELADO", "CANCELADA", "CONCLUÍDO"}
        existing_excluded = set(
            ServiceOrderPhase.objects.filter(name__in=CANDIDATE_EXCLUDED).values_list(
                "name", flat=True
            )
        )

        # Fallback to 'RECUSADA' if nothing found (defensive)
        EXCLUDED_PHASES = existing_excluded or {"RECUSADA"}

        for order in orders:
            if (
                order.service_order_phase
                and order.service_order_phase.name in EXCLUDED_PHASES
            ):
                continue

            try:
                adv = order.advance_payment if order.advance_payment is not None else 0
            except Exception:
                adv = 0

            if adv and float(adv) > 0:
                if order.payment_details and isinstance(order.payment_details, list):
                    for pag in order.payment_details:
                        amt = Decimal(str(pag.get("amount", 0)))
                        pm = pag.get("forma_pagamento", "NÃO INFORMADO")
                        tipo = pag.get("tipo", "sinal")
                        pag_data = pag.get("data")
                        if pag_data:
                            if isinstance(pag_data, str):
                                pag_date = pag_data[:10]
                            else:
                                pag_date = str(pag_data)[:10]
                        else:
                            pag_date = str(order.order_date)
                        if amt > 0:
                            transactions.append({
                                "order_id": order.id,
                                "transaction_type": tipo,
                                "amount": amt,
                                "payment_method": pm,
                                "date": pag_date,
                                "is_virtual": order.is_virtual,
                            })
                            total_amount += amt
                else:
                    amt = Decimal(str(float(adv)))
                    pm = order.payment_method or "NÃO INFORMADO"
                    transactions.append({
                        "order_id": order.id,
                        "transaction_type": "sinal",
                        "amount": amt,
                        "payment_method": pm,
                        "date": order.order_date,
                        "is_virtual": order.is_virtual,
                    })
                    total_amount += amt

            if (
                order.service_order_phase
                and order.service_order_phase.name == "FINALIZADO"
            ):
                try:
                    rem = (
                        order.remaining_payment
                        if order.remaining_payment is not None
                        else 0
                    )
                except Exception:
                    rem = 0

                if rem and float(rem) > 0:
                    amt = Decimal(str(float(rem)))
                    pm = order.payment_method or "NÃO INFORMADO"
                    transactions.append(
                        {
                            "order_id": order.id,
                            "transaction_type": "restante",
                            "amount": amt,
                            "payment_method": pm,
                            "date": order.data_devolvido or order.order_date,
                            "is_virtual": order.is_virtual,
                        }
                    )
                    total_amount += amt

        # build totals_by_method (sobre TODAS as transações, não paginado)
        totals_by_method = {}
        for t in transactions:
            key = t.get("payment_method") or "NÃO INFORMADO"
            if key not in totals_by_method:
                totals_by_method[key] = Decimal("0")
            totals_by_method[key] += Decimal(str(t.get("amount")))

        # Aplicar paginação às transações
        total_transactions = len(transactions)
        total_pages = (total_transactions + page_size - 1) // page_size if page_size > 0 else 1

        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_transactions = transactions[start_idx:end_idx]

        summary = {
            "count": total_transactions,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages,
            "total_transactions": total_transactions,
            "total_amount": total_amount,
            "transactions": paginated_transactions,
            "totals_by_method": totals_by_method,
        }

        return Response(summary)


@extend_schema(
    tags=["service-orders"],
    summary="Listar ordens de serviço por cliente",
    description="Retorna a lista de ordens de serviço de um cliente específico com dados completos",
    responses={
        200: ServiceOrderListByPhaseSerializer(many=True),
        404: {"description": "Cliente não encontrado"},
        500: {"description": "Erro interno do servidor"},
    },
)
class ServiceOrderListByClientAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderListByPhaseSerializer

    def get(self, request, renter_id):
        """Listar ordens de serviço por cliente com dados completos"""
        try:
            # Verificar se o cliente existe
            try:
                client = Person.objects.get(id=renter_id, person_type__type="CLIENTE")
            except Person.DoesNotExist:
                return Response(
                    {"error": "Cliente não encontrado"},
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Buscar todas as OS do cliente (exceto virtuais)
            orders = (
                ServiceOrder.objects.filter(renter=client, is_virtual=False)
                .select_related(
                    "renter",
                    "employee",
                    "attendant",
                    "renter__person_type",
                    "service_order_phase",
                    "event",
                )
                .prefetch_related("items__temporary_product", "items__product")
                .order_by("-order_date")
            )

            data = []
            for order in orders:
                # Dados da OS
                order_data = {
                    "id": order.id,
                    "total_value": order.total_value,
                    "advance_payment": order.advance_payment,
                    "remaining_payment": order.remaining_payment,
                    "employee_name": order.employee.name if order.employee else "",
                    "attendant_name": order.attendant.name if order.attendant else "",
                    "order_date": order.order_date,
                    "prova_date": order.prova_date,
                    "retirada_date": order.retirada_date,
                    "devolucao_date": order.devolucao_date,
                    "data_recusa": order.data_recusa,
                    "data_finalizado": order.data_finalizado,
                    "justification_refusal": order.justification_refusal,
                    "phase": (
                        order.service_order_phase.name
                        if order.service_order_phase
                        else None
                    ),
                    "phase_status": (
                        order.service_order_phase.name
                        if order.service_order_phase
                        else None
                    ),
                    "event_date": (
                        order.event.event_date.date()
                        if order.event
                        and order.event.event_date
                        and hasattr(order.event.event_date, "date")
                        else order.event.event_date if order.event else None
                    ),
                    "event_name": order.event.name if order.event else None,
                }

                # Processar itens da OS
                itens = []
                acessorios = []

                for item in order.items.all():
                    # Determinar se é produto temporário ou produto real
                    temp_product = item.temporary_product
                    product = item.product

                    if temp_product:
                        # Produto temporário
                        if temp_product.product_type in [
                            "paleto",
                            "camisa",
                            "calca",
                            "colete",
                        ]:
                            # Item de roupa
                            item_data = {
                                "tipo": temp_product.product_type,
                                "cor": temp_product.color or "",
                                "extras": temp_product.extras
                                or temp_product.description
                                or "",
                                "venda": temp_product.venda or False,
                                "extensor": False,
                            }

                            # Campos específicos por tipo
                            if temp_product.product_type in ["paleto", "camisa"]:
                                item_data.update(
                                    {
                                        "numero": temp_product.size or "",
                                        "manga": temp_product.sleeve_length or "",
                                        "marca": temp_product.brand or "",
                                        "ajuste": item.adjustment_notes or "",
                                    }
                                )
                            elif temp_product.product_type == "calca":
                                item_data.update(
                                    {
                                        "numero": temp_product.size,
                                        "cintura": temp_product.waist_size or "",
                                        "perna": temp_product.leg_length or "",
                                        "marca": temp_product.brand or "",
                                        "ajuste_cintura": temp_product.ajuste_cintura
                                        or "",
                                        "ajuste_comprimento": temp_product.ajuste_comprimento
                                        or "",
                                    }
                                )
                            elif temp_product.product_type == "colete":
                                item_data.update({"marca": temp_product.brand or ""})

                            itens.append(item_data)
                        else:
                            # Acessório
                            acessorio_data = {
                                "tipo": temp_product.product_type,
                                "numero": temp_product.size or "",
                                "cor": temp_product.color or "",
                                "descricao": temp_product.description or "",
                                "marca": temp_product.brand or "",
                                "extensor": temp_product.extensor or False,
                                "venda": temp_product.venda or False,
                            }
                            acessorios.append(acessorio_data)

                    elif product:
                        # Produto real do estoque
                        if product.tipo.lower() in [
                            "paleto",
                            "camisa",
                            "calça",
                            "colete",
                        ]:
                            # Item de roupa
                            item_data = {
                                "tipo": product.tipo.lower(),
                                "cor": product.cor or "",
                                "extras": product.nome_produto or "",
                                "venda": False,
                                "extensor": False,
                            }

                            # Campos específicos por tipo
                            if product.tipo.lower() in ["paleto", "camisa"]:
                                item_data.update(
                                    {
                                        "numero": (
                                            str(product.tamanho)
                                            if product.tamanho
                                            else ""
                                        ),
                                        "manga": "",
                                        "marca": product.marca or "",
                                        "ajuste": item.adjustment_notes or "",
                                    }
                                )
                            elif product.tipo.lower() == "calça":
                                item_data.update(
                                    {
                                        "numero": (
                                            str(product.tamanho)
                                            if product.tamanho
                                            else ""
                                        ),
                                        "cintura": "",
                                        "perna": "",
                                        "marca": product.marca or "",
                                        "ajuste_cintura": "",
                                        "ajuste_comprimento": "",
                                    }
                                )
                            elif product.tipo.lower() == "colete":
                                item_data.update({"marca": product.marca or ""})

                            itens.append(item_data)
                        else:
                            # Acessório
                            acessorio_data = {
                                "tipo": product.tipo.lower(),
                                "numero": (
                                    str(product.tamanho) if product.tamanho else ""
                                ),
                                "cor": product.cor or "",
                                "descricao": product.nome_produto or "",
                                "marca": product.marca or "",
                                "extensor": False,
                                "venda": False,
                            }
                            acessorios.append(acessorio_data)

                # Dados da ordem de serviço no formato esperado pelo frontend
                ordem_servico_data = {
                    "data_pedido": order.order_date,
                    "data_evento": (
                        order.event.event_date.date()
                        if order.event
                        and order.event.event_date
                        and hasattr(order.event.event_date, "date")
                        else order.event.event_date if order.event else None
                    ),
                    "data_retirada": order.retirada_date,
                    "data_devolucao": order.devolucao_date,
                    "modalidade": order.service_type or "Aluguel",
                    "itens": itens,
                    "acessorios": acessorios,
                    "pagamento": {
                        "total": float(order.total_value) if order.total_value else 0,
                        "sinal": (
                            float(order.advance_payment) if order.advance_payment else 0
                        ),
                        "restante": (
                            float(order.remaining_payment)
                            if order.remaining_payment
                            else 0
                        ),
                        "forma_pagamento": order.payment_method or "",
                    },
                }

                # Adicionar dados completos ao response
                order_data.update({"ordem_servico": ordem_servico_data})

                data.append(order_data)

            return Response(data)

        except Exception as e:
            return Response(
                {"error": f"Erro ao listar OS do cliente: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Dados do cliente da ordem de serviço",
    description="Retorna os dados completos do cliente de uma ordem de serviço",
    responses={
        200: ServiceOrderClientSerializer,
        404: {"description": "Ordem de serviço não encontrada"},
    },
)
class ServiceOrderClientAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ServiceOrderClientSerializer

    def get(self, request, order_id):
        """Buscar dados do cliente de uma ordem de serviço"""
        try:
            service_order = get_object_or_404(ServiceOrder, id=order_id)
            person = service_order.renter

            # Buscar contato mais recente baseado em date_created
            contact = person.contacts.order_by("-date_created", "-id").first()

            # Buscar endereço mais recente baseado em date_created
            address = person.personsadresses_set.order_by("-date_created", "-id").first()

            data = {
                "id": person.id,
                "name": person.name,
                "cpf": person.cpf,
                "email": contact.email if contact else "",
                "phone": contact.phone if contact else "",
                "address": (
                    {
                        "street": address.street if address else "",
                        "number": address.number if address else "",
                        "neighborhood": address.neighborhood if address else "",
                        "city": address.city.name if address else "",
                        "cep": address.cep if address else "",
                        "complemento": address.complemento if address else "",
                    }
                    if address
                    else None
                ),
            }

            return Response(data)

        except ServiceOrder.DoesNotExist:
            return Response(
                {"error": "Ordem de serviço não encontrada"},
                status=status.HTTP_404_NOT_FOUND,
            )


@extend_schema(
    tags=["service-orders"],
    summary="Triagem/Pré-OS (criação por recepção)",
    description="Permite que um usuário do tipo RECEPÇÃO crie uma pré-ordem de serviço (OS) pendente, associando um atendente responsável.",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "cliente_nome": {"type": "string", "description": "Nome do cliente"},
                "telefone": {
                    "type": "string",
                    "description": "Telefone do cliente (opcional)",
                },
                "email": {
                    "type": "string",
                    "format": "email",
                    "description": "Email do cliente (opcional)",
                },
                "cpf": {"type": "string", "description": "CPF do cliente (opcional na triagem - será obrigatório no update da OS)"},
                "atendente_id": {
                    "type": "integer",
                    "description": "ID do atendente responsável (opcional)",
                },
                "origem": {"type": "string", "description": "Origem do pedido"},
                "data_evento": {
                    "type": "string",
                    "format": "date",
                    "description": "Data do evento",
                },
                "tipo_servico": {
                    "type": "string",
                    "description": "Tipo de serviço (Aluguel/Compra)",
                },
                "papel_evento": {"type": "string", "description": "Papel no evento"},
                "endereco": {
                    "type": "object",
                    "properties": {
                        "cep": {"type": "string"},
                        "rua": {"type": "string"},
                        "numero": {"type": "string"},
                        "bairro": {"type": "string"},
                        "cidade": {"type": "string"},
                        "complemento": {
                            "type": "string",
                            "description": "Complemento do endereço (opcional)",
                        },
                    },
                },
                "event_id": {
                    "type": "integer",
                    "description": "ID do evento para vincular à OS (opcional)",
                },
            },
            "required": [
                "cliente_nome",
                "origem",
                "data_evento",
                "tipo_servico",
                "papel_evento",
            ],
        }
    },
    responses={
        201: {
            "description": "Pré-ordem de serviço criada com sucesso",
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
                "order_id": {"type": "integer"},
                "service_order": {"$ref": "#/components/schemas/ServiceOrder"},
            },
        },
        400: {"description": "Dados inválidos"},
        403: {"description": "Permissão negada"},
        500: {"description": "Erro interno do servidor"},
    },
)
class ServiceOrderPreTriageAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """Criação de pré-ordem de serviço pela recepção ou administrador"""
        try:
            data = request.data
            cpf_raw = data.get("cpf", "") or ""
            cpf = cpf_raw.replace(".", "").replace("-", "").strip()
            
            # CPF é opcional na triagem - se fornecido, deve ser válido
            if cpf and len(cpf) != 11:
                return Response(
                    {"error": "CPF inválido. Deve conter 11 dígitos ou ser deixado em branco."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pt, _ = PersonType.objects.get_or_create(type="CLIENTE")
            
            # Se CPF foi fornecido, buscar ou criar pessoa por CPF
            # Se não, criar nova pessoa sem CPF (temporária até update da OS)
            if cpf:
                person, _ = Person.objects.get_or_create(
                    cpf=cpf,
                    defaults={
                        "name": data.get("cliente_nome", "").upper(),
                        "person_type": pt,
                        "created_by": request.user,
                    },
                )
            else:
                # Criar pessoa temporária sem CPF
                person = Person.objects.create(
                    name=data.get("cliente_nome", "").upper(),
                    cpf=None,  # Será preenchido no update da OS
                    person_type=pt,
                    created_by=request.user,
                )

            # Processar contatos apenas se fornecidos
            email = data.get("email") or ""
            telefone = data.get("telefone") or ""

            email = email.strip() if email else None
            telefone = telefone.strip() if telefone else None

            # Criar contato apenas se pelo menos um (email ou telefone) foi fornecido
            if email or telefone:
                PersonsContacts.objects.get_or_create(
                    phone=telefone,
                    person=person,
                    defaults={"email": email, "created_by": request.user},
                )
            endereco = data.get("endereco", {})
            cidade_nome = endereco.get("cidade")
            if cidade_nome:
                city_obj = City.objects.filter(name__iexact=cidade_nome.upper()).first()
                if city_obj:
                    PersonsAdresses.objects.get_or_create(
                        person=person,
                        street=endereco.get("rua") or "",
                        number=endereco.get("numero") or "",
                        cep=endereco.get("cep") or "",
                        complemento=endereco.get("complemento") or "",
                        neighborhood=endereco.get("bairro") or "",
                        city=city_obj,
                        defaults={"created_by": request.user},
                    )
            # Atendente é opcional - será vinculado depois na criação da OS
            atendente_id = data.get("atendente_id")
            atendente = None
            if atendente_id:
                atendente = Person.objects.filter(id=atendente_id).first()
                if not atendente:
                    return Response(
                        {"error": "Atendente não encontrado."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            event_obj = None
            event_id = data.get("event_id")
            if event_id:
                try:
                    event_obj = Event.objects.get(id=event_id)
                except Event.DoesNotExist:
                    return Response(
                        {"error": f"Evento com ID {event_id} não encontrado."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                except ValueError:
                    return Response(
                        {"error": "ID do evento inválido."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            service_order_phase = ServiceOrderPhase.objects.filter(
                name="PENDENTE"
            ).first()

            # tipo_servico é opcional na triagem - será definido posteriormente via modalidade
            tipo_servico = data.get("tipo_servico")
            purchase = tipo_servico == "Venda" if tipo_servico else False

            service_order = ServiceOrder.objects.create(
                renter=person,
                employee=atendente,
                attendant=request.user.person,
                order_date=date.today(),
                renter_role=data.get("papel_evento", "").upper(),
                purchase=purchase,
                service_type=tipo_servico,  # Pode ser None
                came_from=data.get("origem", "").upper(),
                service_order_phase=service_order_phase,
                event=event_obj,
            )
            return Response(
                {
                    "success": True,
                    "message": "Pré-OS criada com sucesso",
                    "order_id": service_order.id,
                    "service_order": ServiceOrderSerializer(service_order).data,
                },
                status=status.HTTP_201_CREATED,
            )
        except Exception as e:
            return Response(
                {"error": f"Erro ao criar pré-OS: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EventCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["events"],
        summary="Criar evento",
        description="Cria um novo evento com nome, descrição opcional e data",
        request=EventCreateSerializer,
        responses={201: EventSerializer},
    )
    def post(self, request):
        serializer = EventCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        name = serializer.validated_data["name"].upper()
        description = serializer.validated_data.get("description", "")
        event_date = serializer.validated_data.get("event_date")

        event = Event.objects.create(
            name=name,
            description=description,
            event_date=event_date,
            created_by=request.user,
        )

        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)


class EventUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["events"],
        summary="Atualizar evento",
        description="Atualiza um evento existente (nome, descrição e/ou data). Atualiza automaticamente o campo date_updated.",
        request=EventUpdateSerializer,
        responses={
            200: EventSerializer,
            404: {"description": "Evento não encontrado"},
            400: {"description": "Dados inválidos"},
        },
    )
    def put(self, request, event_id):
        """Atualizar evento existente"""
        try:
            event = get_object_or_404(Event, id=event_id)

            serializer = EventUpdateSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Atualizar apenas os campos fornecidos
            updated = False

            if "name" in serializer.validated_data:
                event.name = serializer.validated_data["name"].upper()
                updated = True

            if "description" in serializer.validated_data:
                event.description = serializer.validated_data["description"]
                updated = True

            if "event_date" in serializer.validated_data:
                event.event_date = serializer.validated_data["event_date"]
                updated = True

            # Atualizar date_updated se algum campo foi modificado
            if updated:
                event.date_updated = timezone.now()
                event.save()

            return Response(EventSerializer(event).data, status=status.HTTP_200_OK)

        except Event.DoesNotExist:
            return Response(
                {"error": "Evento não encontrado"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"error": f"Erro ao atualizar evento: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EventAddParticipantsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["events"],
        summary="Adicionar pessoas a um evento",
        request=EventAddParticipantsSerializer,
        responses={200: EventSerializer},
    )
    def post(self, request, event_id: int):
        event = get_object_or_404(Event, id=event_id)
        serializer = EventAddParticipantsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        participant_ids = serializer.validated_data["participant_ids"]

        existing_person_ids = set(
            EventParticipant.objects.filter(event=event).values_list(
                "person_id", flat=True
            )
        )

        people = Person.objects.filter(id__in=participant_ids).exclude(
            id__in=existing_person_ids
        )
        EventParticipant.objects.bulk_create(
            [EventParticipant(event=event, person=p) for p in people]
        )

        event.refresh_from_db()
        return Response(EventSerializer(event).data, status=status.HTTP_200_OK)


class EventOpenListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["events"],
        summary="Listar eventos com OS em andamento",
        responses={200: EventSerializer(many=True)},
    )
    def get(self, request):
        finalizadas = ["FINALIZADO", "RECUSADA"]
        eventos_ids = (
            ServiceOrder.objects.filter(
                event__isnull=False,
                service_order_phase__isnull=False,
                date_canceled__isnull=True,
            )
            .exclude(service_order_phase__name__in=finalizadas)
            .values_list("event_id", flat=True)
            .distinct()
        )
        eventos = Event.objects.filter(id__in=eventos_ids)
        return Response(EventSerializer(eventos, many=True).data)


class EventLinkServiceOrderAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["events"],
        summary="Vincular ordem de serviço a evento",
        description="Vincula uma ordem de serviço existente a um evento através dos IDs",
        request=EventLinkServiceOrderSerializer,
        responses={
            200: {
                "description": "Ordem de serviço vinculada com sucesso",
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "message": {"type": "string"},
                    "service_order_id": {"type": "integer"},
                    "event_id": {"type": "integer"},
                },
            },
            404: {"description": "Ordem de serviço ou evento não encontrado"},
            400: {"description": "Dados inválidos"},
        },
    )
    def post(self, request):
        """Vincular ordem de serviço a um evento"""
        try:
            serializer = EventLinkServiceOrderSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            service_order_id = serializer.validated_data["service_order_id"]
            event_id = serializer.validated_data["event_id"]

            # Verificar se a ordem de serviço existe
            service_order = get_object_or_404(ServiceOrder, id=service_order_id)

            # Verificar se o evento existe
            event = get_object_or_404(Event, id=event_id)

            # Vincular a ordem de serviço ao evento
            service_order.event = event
            service_order.save()

            return Response(
                {
                    "success": True,
                    "message": f"OS {service_order_id} vinculada ao evento '{event.name}' com sucesso",
                    "service_order_id": service_order_id,
                    "event_id": event_id,
                }
            )

        except Exception as e:
            return Response(
                {"error": f"Erro ao vincular OS ao evento: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EventListWithStatusAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["events"],
        summary="Listar eventos com status",
        description="Lista todos os eventos com contagem de ordens de serviço e status calculado",
        parameters=[
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Número da página (1-based)",
                required=False,
            ),
            OpenApiParameter(
                name="page_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Número de itens por página",
                required=False,
            ),
            OpenApiParameter(
                name="start_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Filtrar eventos a partir desta data (inclusive) - formato YYYY-MM-DD",
                required=False,
            ),
            OpenApiParameter(
                name="end_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                description="Filtrar eventos até esta data (inclusive) - formato YYYY-MM-DD",
                required=False,
            ),
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Pesquisa livre (ILIKE) em nome do evento ou descrição",
                required=False,
            ),
        ],
        responses={200: EventListWithStatusSerializer},
    )
    def get(self, request):
        """Listar eventos com contagem de OS e status"""
        try:
            from datetime import date

            today = date.today()

            # Paginação
            try:
                page = int(request.GET.get("page", 1))
            except ValueError:
                page = 1
            if page <= 0:
                page = 1

            try:
                page_size = int(request.GET.get("page_size", 50))
            except ValueError:
                page_size = 50
            if page_size <= 0:
                page_size = 50

            # Buscar todos os eventos
            events = Event.objects.all().order_by("-date_created")

            # Aplicar filtros opcionais
            start_date = request.GET.get("start_date")
            end_date = request.GET.get("end_date")
            if start_date:
                try:
                    events = events.filter(event_date__gte=start_date)
                except Exception:
                    pass
            if end_date:
                try:
                    events = events.filter(event_date__lte=end_date)
                except Exception:
                    pass

            # Pesquisa livre
            search = request.GET.get("search")
            if search:
                search = search.strip()
                events = events.filter(
                    models.Q(name__icontains=search) | models.Q(description__icontains=search)
                )

            result_data = []

            for event in events:
                # Contar ordens de serviço vinculadas ao evento
                service_orders = ServiceOrder.objects.filter(event=event)
                service_orders_count = service_orders.count()

                # Calcular status do evento
                status_evento = self._calculate_event_status(
                    event, service_orders, today
                )

                event_data = {
                    "id": event.id,
                    "name": event.name,
                    "description": event.description or "",
                    "event_date": (
                        event.event_date.date()
                        if event.event_date and hasattr(event.event_date, "date")
                        else event.event_date
                    ),
                    "service_orders_count": service_orders_count,
                    "status": status_evento,
                    "date_created": event.date_created,
                    "date_updated": event.date_updated,
                }

                result_data.append(event_data)

            # Aplicar paginação
            total_events = len(result_data)
            total_pages = (total_events + page_size - 1) // page_size if page_size > 0 else 1

            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            paginated_events = result_data[start_idx:end_idx]

            summary = {
                "count": total_events,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "events": paginated_events,
            }

            return Response(summary)

        except Exception as e:
            return Response(
                {"error": f"Erro ao listar eventos: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _calculate_event_status(self, event, service_orders, today):
        """Calcula o status do evento baseado nas ordens de serviço"""

        # Se não tem data do evento definida, não podemos calcular status
        if not event.event_date:
            return "N/A"

        # Garantir que event_date seja datetime.date para comparação
        event_date = event.event_date
        if hasattr(event.event_date, "date"):
            event_date = event.event_date.date()

        # Se o evento ainda não passou da data
        if event_date >= today:
            return "AGENDADO"

        # Evento já passou da data
        if service_orders.count() == 0:
            # Evento passou da data e não possui nenhuma OS vinculada
            return "CANCELADO"

        # Verificar status das OS vinculadas
        os_finalizadas = service_orders.filter(
            service_order_phase__name="FINALIZADO"
        ).count()

        os_em_andamento = service_orders.filter(
            service_order_phase__name__in=[
                "PENDENTE",
                "EM_PRODUCAO",
                "AGUARDANDO_RETIRADA",
                "AGUARDANDO_DEVOLUCAO",
            ]
        ).count()

        # Se todas as OS foram finalizadas
        if os_finalizadas == service_orders.count():
            return "FINALIZADO"

        # Se ainda há OS em andamento após a data do evento
        if os_em_andamento > 0:
            return "POSSUI PENDÊNCIAS"

        # Caso geral - evento passou e tem OS mas não finalizadas corretamente
        return "CANCELADO"

    def _get_most_recent_update_date(self, event, service_orders):
        """Calcula a data de atualização mais recente entre evento e suas OS"""
        from datetime import datetime, time

        from django.utils import timezone as django_timezone

        dates_to_compare = []

        # Função auxiliar para normalizar datas para timezone-aware
        def normalize_date(date_value):
            if date_value is None:
                return None

            # Se é um datetime já timezone-aware, usar como está
            if hasattr(date_value, "tzinfo") and date_value.tzinfo is not None:
                return date_value

            # Se é um datetime naive, converter para timezone-aware
            if hasattr(date_value, "date") and hasattr(date_value, "time"):
                return django_timezone.make_aware(date_value)

            # Se é um date, converter para datetime timezone-aware
            if hasattr(date_value, "year") and not hasattr(date_value, "time"):
                naive_datetime = datetime.combine(date_value, time.min)
                return django_timezone.make_aware(naive_datetime)

            return date_value

        # Adicionar date_updated do evento se existir, senão date_created
        if event.date_updated:
            dates_to_compare.append(normalize_date(event.date_updated))
        else:
            dates_to_compare.append(normalize_date(event.date_created))

        # Adicionar date_updated de cada OS se existir, senão date_created (order_date)
        for order in service_orders:
            if hasattr(order, "date_updated") and order.date_updated:
                dates_to_compare.append(normalize_date(order.date_updated))
            else:
                # Se não tem date_updated, usar date_created (data e hora de criação da OS)
                dates_to_compare.append(normalize_date(order.date_created))

        # Filtrar valores None
        dates_to_compare = [d for d in dates_to_compare if d is not None]

        # Retornar a data mais recente, ou date_created do evento se não houver nada
        if dates_to_compare:
            return max(dates_to_compare)
        else:
            return normalize_date(event.date_created)


class EventDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        tags=["events"],
        summary="Detalhar evento por ID",
        description="Retorna os detalhes completos de um evento específico com dados das OS vinculadas, contagem, status, etc.",
        responses={
            200: EventDetailSerializer,
            404: {"description": "Evento não encontrado"},
            500: {"description": "Erro interno do servidor"},
        },
    )
    def get(self, request, event_id):
        """Detalhar evento específico com contagem de OS, status e dados das OS vinculadas"""
        try:
            from datetime import date

            today = date.today()

            # Buscar o evento específico
            event = get_object_or_404(Event, id=event_id)

            # Buscar ordens de serviço vinculadas ao evento com dados relacionados
            service_orders = (
                ServiceOrder.objects.filter(event=event)
                .select_related("service_order_phase", "renter")
                .order_by("-order_date")
            )
            service_orders_count = service_orders.count()

            # Calcular status do evento usando o mesmo método da listagem
            status_evento = self._calculate_event_status(event, service_orders, today)

            # Preparar dados das ordens de serviço
            service_orders_data = []
            for order in service_orders:
                order_data = {
                    "id": order.id,
                    "date_created": order.date_created,  # date_created com hora completa (datetime)
                    "phase": (
                        order.service_order_phase.name
                        if order.service_order_phase
                        else None
                    ),
                    "total_value": (
                        float(order.total_value) if order.total_value else 0.0
                    ),
                    "client_name": order.renter.name if order.renter else None,
                }
                service_orders_data.append(order_data)

            # Calcular date_updated mais recente
            most_recent_date = self._get_most_recent_update_date(event, service_orders)

            event_data = {
                "id": event.id,
                "name": event.name,
                "description": event.description or "",
                "event_date": event.event_date,
                "service_orders_count": service_orders_count,
                "status": status_evento,
                "date_created": event.date_created,
                "date_updated": most_recent_date,
                "service_orders": service_orders_data,
            }

            return Response(event_data)

        except Exception as e:
            return Response(
                {"error": f"Erro ao buscar evento: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _calculate_event_status(self, event, service_orders, today):
        """Calcula o status do evento baseado nas ordens de serviço"""

        # Se não tem data do evento definida, não podemos calcular status
        if not event.event_date:
            return "N/A"

        # Garantir que event_date seja datetime.date para comparação
        event_date = event.event_date
        if hasattr(event.event_date, "date"):
            event_date = event.event_date.date()

        # Se o evento ainda não passou da data
        if event_date >= today:
            return "AGENDADO"

        # Evento já passou da data
        if service_orders.count() == 0:
            # Evento passou da data e não possui nenhuma OS vinculada
            return "CANCELADO"

        # Verificar status das OS vinculadas
        os_finalizadas = service_orders.filter(
            service_order_phase__name="FINALIZADO"
        ).count()

        os_em_andamento = service_orders.filter(
            service_order_phase__name__in=[
                "PENDENTE",
                "EM_PRODUCAO",
                "AGUARDANDO_RETIRADA",
                "AGUARDANDO_DEVOLUCAO",
            ]
        ).count()

        # Se todas as OS foram finalizadas
        if os_finalizadas == service_orders.count():
            return "FINALIZADO"

        # Se ainda há OS em andamento após a data do evento
        if os_em_andamento > 0:
            return "POSSUI PENDÊNCIAS"

        # Caso geral - evento passou e tem OS mas não finalizadas corretamente
        return "CANCELADO"

    def _get_most_recent_update_date(self, event, service_orders):
        """Calcula a data de atualização mais recente entre evento e suas OS"""
        from datetime import datetime, time

        from django.utils import timezone as django_timezone

        dates_to_compare = []

        # Função auxiliar para normalizar datas para timezone-aware
        def normalize_date(date_value):
            if date_value is None:
                return None

            # Se é um datetime já timezone-aware, usar como está
            if hasattr(date_value, "tzinfo") and date_value.tzinfo is not None:
                return date_value

            # Se é um datetime naive, converter para timezone-aware
            if hasattr(date_value, "date") and hasattr(date_value, "time"):
                return django_timezone.make_aware(date_value)

            # Se é um date, converter para datetime timezone-aware
            if hasattr(date_value, "year") and not hasattr(date_value, "time"):
                naive_datetime = datetime.combine(date_value, time.min)
                return django_timezone.make_aware(naive_datetime)

            return date_value

        # Adicionar date_updated do evento se existir, senão date_created
        if event.date_updated:
            dates_to_compare.append(normalize_date(event.date_updated))
        else:
            dates_to_compare.append(normalize_date(event.date_created))

        # Adicionar date_updated de cada OS se existir, senão date_created (order_date)
        for order in service_orders:
            if hasattr(order, "date_updated") and order.date_updated:
                dates_to_compare.append(normalize_date(order.date_updated))
            else:
                # Se não tem date_updated, usar date_created (data e hora de criação da OS)
                dates_to_compare.append(normalize_date(order.date_created))

        # Filtrar valores None
        dates_to_compare = [d for d in dates_to_compare if d is not None]

        # Retornar a data mais recente, ou date_created do evento se não houver nada
        if dates_to_compare:
            return max(dates_to_compare)
        else:
            return normalize_date(event.date_created)
