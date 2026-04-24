"""
Nexus Closer — Módulo Radar.

Responsabilidade: analisar as leads do Pipeline e disparar alertas
com base nas regras FSS definidas no CLAUDE.md:

  - Janela de 48h úteis sem atualização → alerta de estagnação.
  - Leads em etapas de follow-up (S1–S12) → alerta de acompanhamento.
  - Ciclo de 60 dias sem conversão → sinalização para Break-up.
"""

from datetime import datetime, timedelta, timezone

from src.models import AlertaRadar, RelatorioRadar, Tarefa

# ------------------------------------------------------------------
# Constantes das regras FSS
# ------------------------------------------------------------------

# Limite de horas úteis (seg–sex, 24h/dia) sem atualização
LIMITE_HORAS_UTEIS = 48.0

# Etapas de follow-up monitoradas (S1 a S12)
ETAPAS_FOLLOWUP = {f"S{i}" for i in range(1, 13)}

# Dias máximos no pipeline antes do Break-up
LIMITE_DIAS_CICLO = 60


# ------------------------------------------------------------------
# Funções auxiliares de tempo
# ------------------------------------------------------------------

def horas_uteis_desde(data_inicio: datetime) -> float:
    """
    Calcula quantas horas úteis (segunda a sexta, 24h/dia) se passaram
    desde uma data até o momento atual.

    Itera hora a hora — eficiente para o range máximo do sistema (60 dias).

    Args:
        data_inicio: Datetime com ou sem timezone. Tratado como UTC se naive.

    Returns:
        Total de horas úteis decorridas como float.
    """
    fim = datetime.now(tz=timezone.utc)
    inicio = (
        data_inicio
        if data_inicio.tzinfo
        else data_inicio.replace(tzinfo=timezone.utc)
    )

    if inicio >= fim:
        return 0.0

    horas = 0.0
    cursor = inicio

    while cursor < fim:
        proximo = min(cursor + timedelta(hours=1), fim)
        if cursor.weekday() < 5:  # Segunda (0) a Sexta (4)
            horas += (proximo - cursor).total_seconds() / 3600
        cursor = proximo

    return horas


def dias_desde(data_inicio: datetime) -> int:
    """Retorna quantos dias corridos se passaram desde uma data."""
    fim = datetime.now(tz=timezone.utc)
    inicio = (
        data_inicio
        if data_inicio.tzinfo
        else data_inicio.replace(tzinfo=timezone.utc)
    )
    return max(0, (fim - inicio).days)


# ------------------------------------------------------------------
# Funções de análise por regra FSS
# ------------------------------------------------------------------

def _verificar_estagnacao(tarefas: list[Tarefa]) -> list[AlertaRadar]:
    """
    Regra FSS: leads sem atualização há mais de 48h úteis.

    Ignora tarefas com status final (closed, won, lost, break-up).
    """
    STATUS_FINAIS = {"closed", "won", "lost", "break-up", "encerrado"}
    alertas: list[AlertaRadar] = []

    for tarefa in tarefas:
        if tarefa.status.lower() in STATUS_FINAIS:
            continue

        horas = horas_uteis_desde(tarefa.data_atualizacao)
        if horas >= LIMITE_HORAS_UTEIS:
            alertas.append(
                AlertaRadar(
                    tarefa=tarefa,
                    motivo=f"Sem atualização há {horas:.0f}h úteis (limite: {LIMITE_HORAS_UTEIS:.0f}h)",
                    horas_parado=horas,
                )
            )

    # Ordena do mais crítico (mais parado) para o menos crítico
    return sorted(alertas, key=lambda a: a.horas_parado, reverse=True)


def _verificar_followup(tarefas: list[Tarefa]) -> list[AlertaRadar]:
    """
    Regra FSS: leads nas etapas S1–S12 que precisam de acompanhamento.

    Considera qualquer lead em etapa de follow-up como candidata a alerta,
    priorizando as mais antigas sem atualização.
    """
    alertas: list[AlertaRadar] = []

    for tarefa in tarefas:
        # Verifica se a etapa_followup contém um código S1–S12
        etapa = tarefa.etapa_followup.strip().upper()
        if etapa not in ETAPAS_FOLLOWUP:
            continue

        horas = horas_uteis_desde(tarefa.data_atualizacao)
        alertas.append(
            AlertaRadar(
                tarefa=tarefa,
                motivo=f"Gatilho de follow-up ativo: {etapa}",
                horas_parado=horas,
            )
        )

    return sorted(alertas, key=lambda a: a.horas_parado, reverse=True)


def _verificar_ciclo_60_dias(tarefas: list[Tarefa]) -> list[AlertaRadar]:
    """
    Regra FSS: leads no ciclo há 60+ dias sem conversão → sinalizar Break-up.
    """
    STATUS_FINAIS = {"closed", "won", "lost", "break-up", "encerrado"}
    alertas: list[AlertaRadar] = []

    for tarefa in tarefas:
        if tarefa.status.lower() in STATUS_FINAIS:
            continue

        dias = dias_desde(tarefa.data_criacao)
        if dias >= LIMITE_DIAS_CICLO:
            alertas.append(
                AlertaRadar(
                    tarefa=tarefa,
                    motivo=f"Ciclo de {dias} dias sem conversão — indicado para Break-up",
                    horas_parado=float(dias * 24),
                )
            )

    return sorted(alertas, key=lambda a: a.horas_parado, reverse=True)


# ------------------------------------------------------------------
# Ponto de entrada público do módulo
# ------------------------------------------------------------------

def analisar_leads(tarefas_pipeline: list[Tarefa]) -> RelatorioRadar:
    """
    Analisa todas as leads do Pipeline e gera o relatório de alertas FSS.

    Args:
        tarefas_pipeline: Lista de Tarefa vindas da lista de Pipeline.

    Returns:
        RelatorioRadar com os alertas segmentados por regra.
    """
    alertas_48h = _verificar_estagnacao(tarefas_pipeline)
    alertas_followup = _verificar_followup(tarefas_pipeline)
    alertas_60d = _verificar_ciclo_60_dias(tarefas_pipeline)

    # Unifica alertas de 48h e 60 dias em uma única lista de estagnação
    alertas_48h_combinados = alertas_48h + [
        a for a in alertas_60d if a not in alertas_48h
    ]

    return RelatorioRadar(
        alertas_48h=alertas_48h_combinados,
        alertas_followup=alertas_followup,
        total_pipeline=len(tarefas_pipeline),
    )
