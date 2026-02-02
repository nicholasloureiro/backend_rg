from django.contrib.auth.models import User
from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers

from .models import City, Person, PersonsAdresses, PersonsContacts, PersonType


class CitySerializer(serializers.ModelSerializer):
    class Meta:
        model = City
        fields = "__all__"


class PersonTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonType
        fields = "__all__"


class PersonsContactsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonsContacts
        fields = "__all__"


class PersonsAdressesSerializer(serializers.ModelSerializer):
    class Meta:
        model = PersonsAdresses
        fields = "__all__"


class PersonSerializer(serializers.ModelSerializer):
    contacts = PersonsContactsSerializer(many=True, read_only=True)

    class Meta:
        model = Person
        fields = "__all__"


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Exemplo de registro de funcionário",
            value={
                "name": "João Silva",
                "cpf": "12345678901",
                "email": "joao.silva@email.com",
                "phone": "(11) 99999-9999",
                "role": "ATENDENTE",
            },
            request_only=True,
        )
    ]
)
class EmployeeRegisterSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=255, help_text="Nome completo do funcionário"
    )
    cpf = serializers.CharField(
        max_length=20, help_text="CPF do funcionário (apenas números)"
    )
    email = serializers.EmailField(
        help_text="Email do funcionário", required=False, allow_blank=True, allow_null=True
    )
    phone = serializers.CharField(
        max_length=255, help_text="Telefone do funcionário", required=False, allow_blank=True
    )
    role = serializers.ChoiceField(
        choices=[
            ("ADMINISTRADOR", "ADMINISTRADOR"),
            ("ATENDENTE", "ATENDENTE"),
            ("RECEPÇÃO", "RECEPÇÃO"),
        ],
        help_text="Cargo/função do funcionário",
    )

    def validate_cpf(self, value):
        cpf = "".join(filter(str.isdigit, value))
        if len(cpf) != 11:
            raise serializers.ValidationError("CPF inválido.")
        if User.objects.filter(username=cpf).exists():
            raise serializers.ValidationError("CPF já cadastrado como login.")
        if Person.objects.filter(cpf=cpf).exists():
            raise serializers.ValidationError("Funcionário com este CPF já existe.")
        return cpf

    def create(self, validated_data):
        import random
        import string

        password = "".join(random.choices(string.ascii_uppercase + string.digits, k=7))
        cpf = validated_data["cpf"]
        user = User.objects.create_user(username=cpf, password=password, is_active=True)
        employee_type, _ = PersonType.objects.get_or_create(type=validated_data["role"])
        person = Person.objects.create(
            user=user,
            name=validated_data["name"].upper(),
            cpf=cpf,
            person_type=employee_type,
        )
        # Email e telefone são opcionais
        email = validated_data.get("email") or None
        phone = validated_data.get("phone") or ""
        if email or phone:
            PersonsContacts.objects.create(
                email=email, phone=phone, person=person
            )
        return {"person": person, "password": password}


# Serializers adicionais para corrigir erros do Swagger


class PasswordResetSerializer(serializers.Serializer):
    old_password = serializers.CharField(
        max_length=20, help_text="Senha antiga do usuário para reset de senha"
    )
    new_password = serializers.CharField(
        max_length=20, help_text="Nova senha do usuário para reset de senha"
    )


class ClientRegisterSerializer(serializers.Serializer):
    nome = serializers.CharField(max_length=255, help_text="Nome completo do cliente")
    cpf = serializers.CharField(max_length=20, help_text="CPF do cliente")
    email = serializers.EmailField(
        help_text="Email do cliente", required=False, allow_blank=True, allow_null=True
    )
    telefone = serializers.CharField(
        max_length=255, help_text="Telefone do cliente", required=False, allow_blank=True
    )
    # Dados de endereço (opcionais)
    cep = serializers.CharField(
        max_length=10, help_text="CEP do endereço", required=False, allow_blank=True
    )
    rua = serializers.CharField(
        max_length=255, help_text="Rua do endereço", required=False, allow_blank=True
    )
    numero = serializers.CharField(
        max_length=10, help_text="Número do endereço", required=False, allow_blank=True
    )
    bairro = serializers.CharField(
        max_length=255, help_text="Bairro do endereço", required=False, allow_blank=True
    )
    cidade = serializers.CharField(
        max_length=255, help_text="Nome da cidade", required=False, allow_blank=True
    )
    complemento = serializers.CharField(
        max_length=255,
        help_text="Complemento do endereço",
        required=False,
        allow_blank=True,
    )


class ClientSearchSerializer(serializers.Serializer):
    cpf = serializers.CharField(max_length=20, help_text="CPF do cliente para busca")


class EmployeeToggleStatusSerializer(serializers.Serializer):
    person_id = serializers.IntegerField(help_text="ID da pessoa/funcionário")
    active = serializers.BooleanField(help_text="Status ativo/inativo")


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Exemplo de atualização de funcionário",
            value={
                "name": "João Silva Atualizado",
                "email": "joao.novo@email.com",
                "phone": "(11) 88888-8888",
                "role": "ATENDENTE",
            },
            request_only=True,
        )
    ]
)
class EmployeeUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(
        max_length=255, help_text="Nome completo do funcionário", required=False
    )
    email = serializers.EmailField(
        help_text="Email do funcionário", required=False, allow_blank=True, allow_null=True
    )
    phone = serializers.CharField(
        max_length=255, help_text="Telefone do funcionário", required=False, allow_blank=True
    )
    role = serializers.ChoiceField(
        choices=[
            ("ADMINISTRADOR", "ADMINISTRADOR"),
            ("ATENDENTE", "ATENDENTE"),
            ("RECEPÇÃO", "RECEPÇÃO"),
        ],
        help_text="Cargo/função do funcionário",
        required=False,
    )


class ClientSerializer(serializers.Serializer):
    """Serializer para dados de cliente na listagem"""

    id = serializers.IntegerField()
    name = serializers.CharField()
    cpf = serializers.CharField(allow_null=True, allow_blank=True)
    is_infant = serializers.BooleanField(
        help_text="Se True, cliente é infantil e CPF é um placeholder INFANT-xxx"
    )
    email = serializers.CharField()
    phone = serializers.CharField()
    address = serializers.DictField(required=False, allow_null=True)


class ClientListSerializer(serializers.Serializer):
    """Serializer para listagem paginada de clientes"""

    count = serializers.IntegerField(help_text="Número total de clientes")
    page = serializers.IntegerField(help_text="Página atual (1-based)")
    page_size = serializers.IntegerField(help_text="Quantidade de itens por página")
    total_pages = serializers.IntegerField(help_text="Total de páginas disponíveis")
    clients = ClientSerializer(many=True, help_text="Lista de clientes da página atual")
