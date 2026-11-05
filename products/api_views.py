"""
Views API para o app products
"""

import base64
import io
import os

import pandas as pd
import qrcode
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample, OpenApiParameter, extend_schema
from rest_framework import status, viewsets
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    Brand,
    Button,
    Color,
    ColorCatalogue,
    ColorIntensity,
    Fabric,
    Lapel,
    Model,
    Pattern,
    Product,
    ProductType,
)
from .serializers import (
    BrandSerializer,
    ButtonSerializer,
    CatalogListSerializer,
    ColorCatalogueSerializer,
    ColorCombinationSerializer,
    ColorIntensitySerializer,
    FabricSerializer,
    LapelSerializer,
    ModelSerializer,
    PatternSerializer,
    ProductSerializer,
    ProductTypeSerializer,
    ProductUpdateSerializer,
    TemporaryProductCreateSerializer,
    TemporaryProductSerializer,
    ColorWithIntensitySerializer,
)


@extend_schema(
    tags=["products"],
    summary="Dashboard de produtos",
    description="Retorna estatísticas e métricas dos produtos",
    responses={
        200: {
            "description": "Estatísticas dos produtos",
            "type": "object",
            "properties": {
                "total_products": {"type": "integer"},
                "in_stock": {"type": "integer"},
                "out_of_stock": {"type": "integer"},
                "products_by_type": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                },
                "products_by_brand": {
                    "type": "object",
                    "additionalProperties": {"type": "integer"},
                },
            },
        }
    },
)
class ProductDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Dashboard de produtos com estatísticas"""
        total_products = Product.objects.count()

        # Produtos por tipo
        products_by_type = {}
        for tipo in Product.objects.values_list("tipo", flat=True).distinct():
            count = Product.objects.filter(tipo=tipo).count()
            products_by_type[tipo] = count

        # Produtos por marca
        products_by_brand = {}
        for marca in Product.objects.values_list("marca", flat=True).distinct():
            count = Product.objects.filter(marca=marca).count()
            products_by_brand[marca] = count

        return Response(
            {
                "total_products": total_products,
                "products_by_type": products_by_type,
                "products_by_brand": products_by_brand,
            }
        )


@extend_schema(
    tags=["products"],
    summary="Lista de produtos",
    description="Retorna a lista de produtos com filtros opcionais",
    parameters=[
        OpenApiParameter(
            name="tipo",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filtrar por tipo de produto (Paletó, Calça, Colete)",
            required=False,
        ),
        OpenApiParameter(
            name="marca",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Filtrar por marca",
            required=False,
        ),
    ],
    responses={200: ProductSerializer(many=True)},
)
class ProductListAPIView(ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer
    queryset = Product.objects.all()

    def get_queryset(self):
        queryset = Product.objects.all()

        # Filtros
        tipo = self.request.GET.get("tipo")
        marca = self.request.GET.get("marca")

        if tipo:
            queryset = queryset.filter(tipo__icontains=tipo)
        if marca:
            queryset = queryset.filter(marca__icontains=marca)

        # Adicionar ordenamento alfabético por tipo e marca
        queryset = queryset.order_by("tipo", "marca")

        return queryset

    def list(self, request, *args, **kwargs):
        """Sobrescreve o método list para converter tamanho de float para inteiro"""
        response = super().list(request, *args, **kwargs)

        # Converter tamanho de float para inteiro em cada produto
        if response.data and "results" in response.data:
            for product in response.data["results"]:
                if "tamanho" in product and product["tamanho"] is not None:
                    # Converter para inteiro, arredondando se necessário
                    product["tamanho"] = int(round(float(product["tamanho"])))
        elif response.data and isinstance(response.data, list):
            # Se a resposta for uma lista direta (sem paginação)
            for product in response.data:
                if "tamanho" in product and product["tamanho"] is not None:
                    product["tamanho"] = int(round(float(product["tamanho"])))

        return response


class ProductUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ProductUpdateSerializer

    def put(self, request, product_id):
        """Atualizar produto"""
        try:
            product = Product.objects.get(id=product_id)
            serializer = ProductSerializer(product, data=request.data, partial=True)

            if serializer.is_valid():
                product = serializer.save(updated_by=request.user)
                return Response(
                    {"success": True, "product": ProductSerializer(product).data}
                )

            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Product.DoesNotExist:
            return Response(
                {"error": "Produto não encontrado"}, status=status.HTTP_404_NOT_FOUND
            )


@extend_schema(
    tags=["products"],
    summary="Importar produtos via Excel",
    description="Importa produtos de um arquivo Excel, criando novos produtos ou atualizando existentes baseado no ID. Valida campos obrigatórios para evitar dados inválidos.",
    request={
        "multipart/form-data": {
            "type": "object",
            "properties": {
                "excel_file": {
                    "type": "string",
                    "format": "binary",
                    "description": "Arquivo Excel (.xlsx, .xls) com dados dos produtos. Deve conter colunas obrigatórias: Tipo, ID, Nome do produto, Marca, Material, Cor, Intensidade de cor, Tamanho",
                }
            },
        },
    },
    responses={
        200: {
            "description": "Produtos importados com sucesso",
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "message": {"type": "string"},
                "products_created": {"type": "integer"},
                "products_updated": {"type": "integer"},
                "errors": {"type": "array", "items": {"type": "string"}},
            },
        },
        400: {
            "description": "Arquivo não fornecido, formato inválido ou dados obrigatórios ausentes"
        },
        500: {"description": "Erro interno do servidor"},
    },
)
class ProductStockUpdateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        """Importar produtos via arquivo Excel"""
        try:
            # Verificar se foi enviado um arquivo
            if "excel_file" not in request.FILES:
                return Response(
                    {"error": "Arquivo Excel não fornecido"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            excel_file = request.FILES["excel_file"]

            # Validar extensão do arquivo
            if not excel_file.name.endswith((".xlsx", ".xls")):
                return Response(
                    {"error": "Apenas arquivos Excel (.xlsx, .xls) são permitidos"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Processar o arquivo Excel
            result = self._process_excel_file(excel_file)

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            return Response(
                {"error": f"Erro ao processar arquivo Excel: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def _process_excel_file(self, excel_file):
        """Processa o arquivo Excel e salva os produtos"""

        products_created = 0
        products_updated = 0
        errors = []

        try:
            # Ler o arquivo Excel
            df = pd.read_excel(excel_file)

            # Validar colunas obrigatórias
            required_columns = [
                "Tipo",
                "ID",
                "Nome do produto",
                "Marca",
                "Material",
                "Cor",
                "Intensidade de cor",
                "Tamanho",
            ]
            missing_columns = [col for col in required_columns if col not in df.columns]

            if missing_columns:
                return {
                    "error": f"Colunas obrigatórias não encontradas: {', '.join(missing_columns)}"
                }

            # Processar cada linha
            for index, row in df.iterrows():
                try:
                    # Verificar se o produto já existe pelo ID
                    id_produto = self._validate_required_field(
                        row.get("ID"), "ID", index
                    )

                    # Verificar se produto já existe
                    existing_product = Product.objects.filter(
                        id_produto=id_produto
                    ).first()

                    if existing_product:
                        # Atualizar produto existente
                        self._update_product_from_row(existing_product, row, index)
                        products_updated += 1
                    else:
                        # Criar novo produto
                        self._create_product_from_row(row, index)
                        products_created += 1

                except Exception as e:
                    errors.append(f"Linha {index + 2}: {str(e)}")

            return {
                "success": True,
                "message": f"Processamento concluído. {products_created} produtos criados, {products_updated} atualizados",
                "products_created": products_created,
                "products_updated": products_updated,
                "errors": errors,
            }

        except Exception as e:
            return {"error": f"Erro ao ler arquivo Excel: {str(e)}"}

    def _validate_required_field(self, value, field_name, row_index):
        """Valida se um campo obrigatório está preenchido e não é 'nan'"""
        if (
            pd.isna(value)
            or str(value).strip() == ""
            or str(value).strip().lower() == "nan"
        ):
            raise ValueError(
                f"Linha {row_index + 2}: Campo '{field_name}' é obrigatório e não pode estar vazio ou 'nan'"
            )
        return str(value).strip()

    def _validate_tamanho_field(self, value, row_index):
        """Valida se o campo tamanho é um número válido"""
        if (
            pd.isna(value)
            or str(value).strip() == ""
            or str(value).strip().lower() == "nan"
        ):
            raise ValueError(
                f"Linha {row_index + 2}: Campo 'Tamanho' é obrigatório e não pode estar vazio ou 'nan'"
            )

        try:
            tamanho = float(value)
            if tamanho <= 0:
                raise ValueError(
                    f"Linha {row_index + 2}: Campo 'Tamanho' deve ser um número maior que zero"
                )
            return tamanho
        except (ValueError, TypeError):
            raise ValueError(
                f"Linha {row_index + 2}: Campo 'Tamanho' deve ser um número válido"
            )

    def _create_product_from_row(self, row, index):
        """Cria um novo produto a partir de uma linha do Excel"""
        try:
            # Validar e extrair campos obrigatórios
            tipo = self._validate_required_field(row.get("Tipo"), "Tipo", index)
            id_produto = self._validate_required_field(row.get("ID"), "ID", index)
            nome_produto = self._validate_required_field(
                row.get("Nome do produto"), "Nome do produto", index
            )
            marca = self._validate_required_field(row.get("Marca"), "Marca", index)
            material = self._validate_required_field(
                row.get("Material"), "Material", index
            )
            cor = self._validate_required_field(row.get("Cor"), "Cor", index)
            intensidade_cor = self._validate_required_field(
                row.get("Intensidade de cor"), "Intensidade de cor", index
            )
            tamanho = self._validate_tamanho_field(row.get("Tamanho"), index)

            # Campos opcionais (podem ser None)
            padronagem = (
                str(row.get("Padronagem", "")).strip()
                if pd.notna(row.get("Padronagem"))
                else ""
            )
            botoes = (
                str(row.get("Botões", "")).strip()
                if pd.notna(row.get("Botões"))
                else None
            )
            lapela = (
                str(row.get("Lapela", "")).strip()
                if pd.notna(row.get("Lapela"))
                else None
            )
            foto_path = (
                str(row.get("Foto", "")).strip() if pd.notna(row.get("Foto")) else None
            )

            # Validar se campos opcionais não são 'nan' quando fornecidos
            if botoes and botoes.lower() == "nan":
                botoes = None
            if lapela and lapela.lower() == "nan":
                lapela = None
            if foto_path and foto_path.lower() == "nan":
                foto_path = None

            # Criar produto
            product = Product(
                tipo=tipo,
                id_produto=id_produto,
                nome_produto=nome_produto,
                marca=marca,
                material=material,
                cor=cor,
                intensidade_cor=intensidade_cor,
                padronagem=padronagem,
                botoes=botoes,
                lapela=lapela,
                tamanho=tamanho,
            )

            # Processar foto se existir
            if foto_path:
                self._process_photo(product, foto_path)

            product.save()

        except Exception as e:
            raise ValueError(f"Erro ao criar produto: {str(e)}")

    def _update_product_from_row(self, product, row, index):
        """Atualiza um produto existente a partir de uma linha do Excel"""
        try:
            # Validar e atualizar campos obrigatórios
            product.tipo = self._validate_required_field(row.get("Tipo"), "Tipo", index)
            product.nome_produto = self._validate_required_field(
                row.get("Nome do produto"), "Nome do produto", index
            )
            product.marca = self._validate_required_field(
                row.get("Marca"), "Marca", index
            )
            product.material = self._validate_required_field(
                row.get("Material"), "Material", index
            )
            product.cor = self._validate_required_field(row.get("Cor"), "Cor", index)
            product.intensidade_cor = self._validate_required_field(
                row.get("Intensidade de cor"), "Intensidade de cor", index
            )
            product.tamanho = self._validate_tamanho_field(row.get("Tamanho"), index)

            # Campos opcionais
            product.padronagem = (
                str(row.get("Padronagem", "")).strip()
                if pd.notna(row.get("Padronagem"))
                else ""
            )

            # Campos opcionais que podem ser None
            botoes = (
                str(row.get("Botões", "")).strip()
                if pd.notna(row.get("Botões"))
                else None
            )
            lapela = (
                str(row.get("Lapela", "")).strip()
                if pd.notna(row.get("Lapela"))
                else None
            )
            foto_path = (
                str(row.get("Foto", "")).strip() if pd.notna(row.get("Foto")) else None
            )

            # Validar se campos opcionais não são 'nan' quando fornecidos
            if botoes and botoes.lower() == "nan":
                product.botoes = None
            else:
                product.botoes = botoes

            if lapela and lapela.lower() == "nan":
                product.lapela = None
            else:
                product.lapela = lapela

            # Processar foto se existir
            if foto_path and foto_path.lower() != "nan":
                self._process_photo(product, foto_path)

            product.save()

        except Exception as e:
            raise ValueError(f"Erro ao atualizar produto: {str(e)}")

    def _process_photo(self, product, foto_path):
        """Processa a foto do produto e converte para base64"""
        try:
            # Verificar se o caminho da foto existe
            if os.path.exists(foto_path):
                with open(foto_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
                    product.foto_base64 = encoded_string
            else:
                # Se o caminho não existir, tentar buscar na pasta do projeto
                project_path = os.path.join(os.getcwd(), foto_path)
                if os.path.exists(project_path):
                    with open(project_path, "rb") as image_file:
                        encoded_string = base64.b64encode(image_file.read()).decode(
                            "utf-8"
                        )
                        product.foto_base64 = encoded_string
                else:
                    print(f"Arquivo de foto não encontrado: {foto_path}")

        except Exception as e:
            print(f"Erro ao processar foto {foto_path}: {str(e)}")


@extend_schema(
    tags=["products"],
    summary="Gerar QR Code",
    description="Gera um QR Code para um produto específico",
    parameters=[
        OpenApiParameter(
            name="product_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.PATH,
            description="ID do produto",
        )
    ],
    responses={
        200: {
            "description": "QR Code gerado com sucesso",
            "type": "object",
            "properties": {
                "success": {"type": "boolean"},
                "qr_code": {"type": "string", "description": "QR Code em base64"},
                "id_produto": {"type": "string"},
                "product_info": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "tipo": {"type": "string"},
                        "nome_produto": {"type": "string"},
                        "marca": {"type": "string"},
                        "cor": {"type": "string"},
                    },
                },
            },
        },
        404: {"description": "Produto não encontrado"},
    },
)
class ProductQRCodeAPIView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ProductSerializer

    def get(self, request, product_id):
        """Gerar QR Code para um produto"""
        try:
            product = Product.objects.get(id=product_id)

            # Criar QR Code
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(f"Produto: {product.id_produto}")
            qr.make(fit=True)

            # Converter para imagem
            img = qr.make_image(fill_color="black", back_color="white")

            # Converter para base64
            buffer = io.BytesIO()
            img.save(buffer, format="PNG")
            qr_code_base64 = base64.b64encode(buffer.getvalue()).decode()

            return Response(
                {
                    "success": True,
                    "qr_code": f"data:image/png;base64,{qr_code_base64}",
                    "id_produto": product.id_produto,
                    "product_info": {
                        "id": product.id,
                        "tipo": product.tipo,
                        "nome_produto": product.nome_produto,
                        "marca": product.marca,
                        "cor": product.cor,
                    },
                }
            )

        except Product.DoesNotExist:
            return Response(
                {"error": "Produto não encontrado"}, status=status.HTTP_404_NOT_FOUND
            )


@extend_schema(
    tags=["products"],
    summary="Lista de cores e combinações",
    description="Retorna todas as cores do catálogo e todas as combinações possíveis com intensidades, incluindo versões sem intensidade",
    responses={
        200: {
            "description": "Lista de cores e combinações",
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "color": {"type": "string", "description": "Nome da cor"},
                    "intensity": {
                        "type": "string",
                        "description": "Intensidade da cor (null se sem intensidade)",
                    },
                    "combined": {
                        "type": "string",
                        "description": "String combinada para pesquisa (ex: 'Preto FOSCO', 'Azul')",
                    },
                },
            },
        }
    },
    examples=[
        OpenApiExample(
            "Exemplo de resposta",
            value=[
                {"color": "Preto", "intensity": None, "combined": "Preto"},
                {"color": "Preto", "intensity": "FOSCO", "combined": "Preto FOSCO"},
                {"color": "Azul", "intensity": "BRILHO", "combined": "Azul BRILHO"},
            ],
            response_only=True,
            status_codes=["200"],
        )
    ],
)
class ColorListAPIView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ColorCombinationSerializer

    def get(self, request):
        """Lista todas as cores e combinações possíveis com intensidades"""
        from .models import ColorCatalogue, ColorIntensity

        # Buscar todas as cores do catálogo ordenadas alfabeticamente
        colors = ColorCatalogue.objects.all().order_by("description")
        # Buscar todas as intensidades ordenadas alfabeticamente
        intensities = ColorIntensity.objects.all().order_by("description")
        result = []

        # 1. Adicionar cores sem intensidade (apenas do catálogo)
        for color in colors:
            result.append(
                {
                    "color": color.description,
                    "intensity": None,
                    "combined": color.description,
                }
            )

        # 2. Adicionar todas as combinações possíveis de cor + intensidade
        for color in colors:
            for intensity in intensities:
                result.append(
                    {
                        "color": color.description,
                        "intensity": intensity.description,
                        "combined": f"{color.description} {intensity.description}",
                    }
                )

        # Ordenar o resultado final alfabeticamente por cor e depois por intensidade
        result.sort(key=lambda x: (x["color"], x["intensity"] or ""))

        return Response(result)


@extend_schema(
    tags=["products"],
    summary="Lista de marcas",
    description="Retorna todas as marcas disponíveis no sistema",
    responses={
        200: {
            "description": "Lista de marcas",
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer", "description": "ID da marca"},
                    "description": {"type": "string", "description": "Nome da marca"},
                },
            },
        }
    },
    examples=[
        OpenApiExample(
            "Exemplo de resposta",
            value=[
                {"id": 1, "description": "Armani"},
                {"id": 2, "description": "Zara"},
                {"id": 3, "description": "Hugo Boss"},
            ],
            response_only=True,
            status_codes=["200"],
        )
    ],
)
class BrandListAPIView(APIView):
    permission_classes = [AllowAny]
    serializer_class = BrandSerializer

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="search",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Busca por nome da marca (case insensitive)",
                required=False,
            ),
        ],
    )
    def get(self, request):
        """Lista todas as marcas disponíveis com suporte a busca"""
        brands = Brand.objects.all().order_by("description")
        
        # Filtro de busca
        search = request.query_params.get("search")
        if search:
            brands = brands.filter(description__icontains=search)
        
        data = [
            {
                "id": brand.id,
                "description": brand.description,
            }
            for brand in brands
        ]
        return Response(data)


@extend_schema(
    tags=["Brands"],
    parameters=[
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Busca por nome da marca (case insensitive)",
            required=False,
        ),
    ],
)
class BrandListNoPaginationAPIView(ListAPIView):
    """Lista todas as marcas sem paginação, com 'SEM MARCA' primeiro"""
    permission_classes = [IsAuthenticated]
    serializer_class = BrandSerializer
    pagination_class = None

    def get_queryset(self):
        from django.db.models import Case, When, Value
        queryset = Brand.objects.annotate(
            order_priority=Case(
                When(description='SEM MARCA', then=Value(0)),
                default=Value(1),
            )
        ).order_by('order_priority', 'description')
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(description__icontains=search)
        return queryset

    def get(self, request, *args, **kwargs):
        """Lista todas as marcas sem paginação"""
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class ColorWithIntensityListAPIView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ColorWithIntensitySerializer

    def get(self, request):
        """Lista todas as combinações de cor e intensidade"""
        combos = (
            Color.objects.select_related("color", "color_intensity")
            .all()
            .order_by("color__description", "color_intensity__description")
        )
        data = [
            {
                "id": combo.id,
                "color_id": combo.color.id,
                "color": combo.color.description,
                "intensity_id": combo.color_intensity.id,
                "intensity": combo.color_intensity.description,
            }
            for combo in combos
        ]
        return Response(data)


class TemporaryProductCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TemporaryProductCreateSerializer

    def post(self, request):
        """Criar produto temporário"""
        serializer = TemporaryProductSerializer(data=request.data)

        if serializer.is_valid():
            temp_product = serializer.save(created_by=request.user)
            return Response(
                {
                    "success": True,
                    "temporary_product": TemporaryProductSerializer(temp_product).data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CatalogListAPIView(APIView):
    permission_classes = [AllowAny]
    serializer_class = CatalogListSerializer

    def get(self, request):
        """Lista todos os catálogos (marcas, tecidos, etc.)"""
        catalogs = {
            "brands": BrandSerializer(
                Brand.objects.all().order_by("description"), many=True
            ).data,
            "fabrics": FabricSerializer(
                Fabric.objects.all().order_by("description"), many=True
            ).data,
            "colors": ColorCatalogueSerializer(
                ColorCatalogue.objects.all().order_by("description"), many=True
            ).data,
            "patterns": PatternSerializer(
                Pattern.objects.all().order_by("description"), many=True
            ).data,
            "buttons": ButtonSerializer(
                Button.objects.all().order_by("description"), many=True
            ).data,
            "lapels": LapelSerializer(
                Lapel.objects.all().order_by("description"), many=True
            ).data,
            "models": ModelSerializer(
                Model.objects.all().order_by("description"), many=True
            ).data,
            "product_types": ProductTypeSerializer(
                ProductType.objects.all().order_by("description"), many=True
            ).data,
        }

        return Response(catalogs)


@extend_schema(
    tags=["Brands"],
    parameters=[
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Busca por nome da marca (case insensitive)",
            required=False,
        ),
    ],
)
class BrandViewSet(viewsets.ModelViewSet):
    """CRUD for Brand model with search support"""
    serializer_class = BrandSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        from django.db.models import Case, When, Value
        queryset = Brand.objects.annotate(
            order_priority=Case(
                When(description='SEM MARCA', then=Value(0)),
                default=Value(1),
            )
        ).order_by('order_priority', 'description')
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(description__icontains=search)
        return queryset


@extend_schema(
    tags=["Color Catalogues"],
    parameters=[
        OpenApiParameter(
            name="search",
            type=OpenApiTypes.STR,
            location=OpenApiParameter.QUERY,
            description="Busca por nome da cor (case insensitive)",
            required=False,
        ),
    ],
)
class ColorCatalogueViewSet(viewsets.ModelViewSet):
    """CRUD for ColorCatalogue model with search support"""
    serializer_class = ColorCatalogueSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = ColorCatalogue.objects.all().order_by("description")
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(description__icontains=search)
        return queryset


@extend_schema(tags=["Color Intensities"])
class ColorIntensityViewSet(viewsets.ModelViewSet):
    """CRUD for ColorIntensity model"""
    queryset = ColorIntensity.objects.all()
    serializer_class = ColorIntensitySerializer
    permission_classes = [IsAuthenticated]
