from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from accounts.models import BaseModel, Person
from products.models import Color, ColorCatalogue, Product, TemporaryProduct


class ServiceOrderPhase(BaseModel):
    name = models.CharField(max_length=20)


class RefusalReason(BaseModel):
    """Motivos de recusa/cancelamento de ordens de serviço"""

    name = models.CharField(
        max_length=100, unique=True, help_text="Nome do motivo de recusa"
    )

    class Meta:
        db_table = "refusal_reasons"
        verbose_name = "Motivo de Recusa"
        verbose_name_plural = "Motivos de Recusa"

    def __str__(self):
        return self.name


class ServiceOrder(BaseModel):
    renter = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="service_orders", null=True, blank=True
    )
    employee = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="employee_service_orders",
        null=True,
    )
    attendant = models.ForeignKey(
        Person,
        on_delete=models.CASCADE,
        related_name="attendant_service_orders",
        null=True,
    )
    order_date = models.DateField()
    event = models.ForeignKey(
        "Event",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders",
    )
    renter_role = models.CharField(max_length=255, null=True)
    total_value = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, null=True
    )
    advance_payment = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, null=True
    )
    remaining_payment = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, null=True
    )
    max_payment_date = models.DateField(null=True, default=None)
    payment_method = models.CharField(max_length=255, null=True)
    payment_details = models.JSONField(null=True, blank=True, help_text="Detalhes dos pagamentos [{amount, forma_pagamento}]")
    adjustment_needed = models.BooleanField(default=None, null=True)
    came_from = models.CharField(max_length=255, default=None, null=True)
    purchase = models.BooleanField(default=False)
    service_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text="Tipo de serviço (Aluguel, Compra, Aluguel + Venda)",
    )
    observations = models.TextField(null=True, blank=True)
    service_order_phase = models.ForeignKey(
        ServiceOrderPhase, on_delete=models.SET_NULL, null=True
    )
    justification_refusal = models.TextField(null=True, blank=True, default=None)
    justification_reason = models.ForeignKey(
        RefusalReason,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="service_orders",
        help_text="Motivo de recusa/cancelamento",
    )
    prova_date = models.DateField(null=True, blank=True)
    retirada_date = models.DateField(null=True, blank=True)
    devolucao_date = models.DateField(null=True, blank=True)
    data_devolvido = models.DateTimeField(
        null=True, blank=True, help_text="Data e hora em que foi devolvido"
    )
    data_retirado = models.DateTimeField(
        null=True, blank=True, help_text="Data e hora em que foi retirado"
    )
    # Data e hora em que a OS foi recusada (quando fase passa para RECUSADA)
    data_recusa = models.DateField(
        null=True, blank=True, help_text="Data em que a OS foi recusada"
    )
    # Data em que a OS foi finalizada (quando marcada como paga / FINALIZADO)
    data_finalizado = models.DateField(
        null=True, blank=True, help_text="Data em que a OS foi finalizada"
    )
    esta_atrasada = models.BooleanField(
        default=False,
        help_text="Flag indicando se a OS está atrasada (retirada ou devolução)",
    )
    production_date = models.DateField(
        null=True,
        blank=True,
        help_text="Data em que a OS foi movida para produção",
    )
    is_virtual = models.BooleanField(
        default=False,
        help_text="OS virtual apenas para registro de pagamento",
    )
    client_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Nome do cliente (para OS virtual sem cliente cadastrado)",
    )

    class Meta:
        db_table = "service_orders"

    def __str__(self):
        return f"OS {self.id} - {self.renter.name}"

    def save(self, *args, **kwargs):
        # Calcula automaticamente o valor restante
        if self.total_value is not None and self.advance_payment is not None:
            self.remaining_payment = self.total_value - self.advance_payment
        super().save(*args, **kwargs)

    def is_atrasada(self):
        today = timezone.now().date()
        # Considera atraso se devolução já passou e não está concluída
        return (
            self.devolucao_date
            and self.devolucao_date < today
            and self.service_order_phase
            and self.service_order_phase.name not in ["FINALIZADO", "RECUSADA"]
        )

    def is_hoje(self):
        today = timezone.now().date()
        return (
            (
                self.prova_date == today
                or self.retirada_date == today
                or self.devolucao_date == today
            )
            and self.service_order_phase
            and self.service_order_phase.name not in ["FINALIZADO", "RECUSADA"]
        )

    def is_proximos_10_dias(self):
        today = timezone.now().date()
        in_10 = today + timezone.timedelta(days=10)
        return (
            (self.devolucao_date and today < self.devolucao_date <= in_10)
            and self.service_order_phase
            and self.service_order_phase.name not in ["FINALIZADO", "RECUSADA"]
        )

    def tipo_evento(self):
        # Retorna o tipo do evento para dashboard: prova, retirada, devolucao
        if self.prova_date:
            return "prova"
        if self.retirada_date:
            return "retirada"
        if self.devolucao_date:
            return "devolucao"
        return "outro"


class ServiceOrderItem(BaseModel):
    service_order = models.ForeignKey(
        ServiceOrder, related_name="items", on_delete=models.CASCADE
    )
    temporary_product = models.ForeignKey(
        TemporaryProduct,
        related_name="order_items",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    product = models.ForeignKey(
        Product,
        related_name="order_items",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    color_catalogue = models.ForeignKey(
        ColorCatalogue,
        related_name="order_items",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    color = models.ForeignKey(
        Color,
        related_name="order_items_color",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    adjustment_needed = models.BooleanField(default=False)
    adjustment_value = models.IntegerField(null=True)
    adjustment_notes = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        db_table = "service_order_items"

    def __str__(self):
        prod_desc = self.product if self.product else self.temporary_product
        return f"{self.service_order.id} - {prod_desc}"

    def clean(self):
        # Garante que só um dos campos seja preenchido
        if not self.product and not self.temporary_product:
            raise ValidationError("Item deve ter um produto ou produto temporário")
        if self.product and self.temporary_product:
            raise ValidationError(
                "Item não pode ter produto e produto temporário simultaneamente"
            )


class Event(BaseModel):
    name = models.CharField(max_length=255, db_index=True)
    description = models.TextField(null=True, blank=True)
    event_date = models.DateField(null=True, blank=True, help_text="Data do evento")

    class Meta:
        db_table = "events"

    def __str__(self):
        return f"Evento: {self.name} - {self.event_date}"


class EventParticipant(BaseModel):
    event = models.ForeignKey(
        Event, related_name="participants", on_delete=models.CASCADE
    )
    person = models.ForeignKey(
        Person, related_name="event_participations", on_delete=models.CASCADE
    )

    class Meta:
        db_table = "event_participants"
        constraints = [
            models.UniqueConstraint(
                fields=["event", "person"], name="unique_event_person"
            )
        ]

    def __str__(self):
        return f"{self.person.name} em {self.event.name}"
