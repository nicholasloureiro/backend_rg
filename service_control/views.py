# =============================================================================
# ARQUIVO LIMPO - MIGRAÇÃO PARA API REST COMPLETA
# =============================================================================
#
# Todas as views legadas foram removidas e migradas para api_views.py
#
# Views removidas:
# - service_control_view() -> (removido - não necessário em API REST)
# - create_pre_service_order() -> ServiceOrderCreateAPIView
# - update_service_order() -> ServiceOrderUpdateAPIView
# - pre_register_view() -> (removido - não necessário)
# - pre_service_order_view() -> (removido - não necessário)
# - list_pending_service_orders() -> ServiceOrderListByPhaseAPIView
# - list_awaiting_payment_service_orders() -> ServiceOrderListByPhaseAPIView
# - os_view() -> (removido - não necessário)
# - get_service_order_client() -> ServiceOrderClientAPIView
# - mark_service_order_paid() -> ServiceOrderMarkPaidAPIView
# - list_finished_service_orders() -> ServiceOrderListByPhaseAPIView
# - refuse_service_order() -> ServiceOrderRefuseAPIView
# - list_overdue_service_orders() -> ServiceOrderListByPhaseAPIView
# - list_refused_service_orders() -> ServiceOrderListByPhaseAPIView
# - dashboard_metrics_view() -> ServiceOrderDashboardAPIView
# - ServiceOrderDashboardAPIView() -> (já em api_views.py)
# - ServiceOrderListAPIView() -> (já em api_views.py)
#
# Função mantida (usada pela API):
def advance_service_order_phases():
    """
    Função para avançar automaticamente as fases das OS baseado no tempo de devolução
    """
    from datetime import date

    from .models import ServiceOrder, ServiceOrderPhase

    today = date.today()

    # Fases-alvo buscadas UMA vez (evita um SELECT por OS dentro do loop).
    overdue_phase = ServiceOrderPhase.objects.filter(name="EM ATRASO").first()
    in_progress_phase = ServiceOrderPhase.objects.filter(name="EM ANDAMENTO").first()

    # Se nenhuma fase-alvo existe, nenhuma OS pode avançar. Retorna cedo para
    # não varrer a tabela inteira a cada request (esta função roda no dashboard).
    if overdue_phase is None and in_progress_phase is None:
        return

    # Busca todas as OS que precisam de avanço de fase
    service_orders = ServiceOrder.objects.filter(
        service_order_phase__name__in=["PENDENTE", "EM ANDAMENTO", "FINALIZADO"]
    ).select_related("service_order_phase")

    for os in service_orders:
        # Lógica de avanço baseada em datas
        if os.devolucao_date and os.devolucao_date < today:
            # OS em atraso - mudar para "EM ATRASO"
            if overdue_phase is not None and os.service_order_phase != overdue_phase:
                os.service_order_phase = overdue_phase
                os.save()
                print(f"OS {os.id} marcada como EM ATRASO")

        elif (
            os.retirada_date
            and os.retirada_date <= today
            and os.service_order_phase.name == "FINALIZADO"
        ):
            # OS finalizada e data de retirada chegou - mudar para "EM ANDAMENTO"
            if in_progress_phase is not None:
                os.service_order_phase = in_progress_phase
                os.save()
                print(f"OS {os.id} avançada para EM ANDAMENTO")


# Todas as funcionalidades agora estão disponíveis via API REST:
# - /api/v1/service-orders/dashboard/
# - /api/v1/service-orders/
# - /api/v1/service-orders/create/
# - /api/v1/service-orders/{id}/
# - /api/v1/service-orders/{id}/update/
# - /api/v1/service-orders/{id}/mark-paid/
# - /api/v1/service-orders/{id}/refuse/
# - /api/v1/service-orders/{id}/client/
# - /api/v1/service-orders/phase/{phase_name}/
#
# Documentação completa: /api/docs/
# =============================================================================
