"""
Nexus Closer — Módulo Financeiro.

Responsabilidade: calcular indicadores financeiros da semana corrente
com base nas tarefas da lista de Pipeline.

Métricas produzidas:
  - Faturamento Bruto total da semana.
  - Faturamento Líquido total da semana.
  - Comissão total acumulada.
  - Volume (quantidade + financeiro) segmentado por Plano.
"""

from datetime import datetime, timedelta, timezone

from src.models import RelatorioFinanceiro, Tarefa, VolumeporPlano


# ------------------------------------------------------------------
# Funções auxiliares de período
# ------------------------------------------------------------------

def _inicio_semana_atual() -> datetime:
    """Retorna a segunda-feira da semana corrente às 00:00 UTC."""
    hoje = datetime.now(tz=timezone.utc)
    dias_ate_segunda = hoje.weekday()  # Segunda=0, Domingo=6
    segunda = hoje - timedelta(days=dias_ate_segunda)
    return segunda.replace(hour=0, minute=0, second=0, microsecond=0)


def _fim_semana_atual() -> datetime:
    """Retorna o domingo da semana corrente às 23:59:59 UTC."""
    inicio = _inicio_semana_atual()
    return inicio + timedelta(days=6, hours=23, minutes=59, seconds=59)


def _tarefa_e_da_semana(tarefa: Tarefa, inicio: datetime, fim: datetime) -> bool:
    """
    Verifica se a tarefa foi atualizada dentro do intervalo da semana.

    Usa data_atualizacao como referência de quando o negócio foi movimentado.
    """
    data = tarefa.data_atualizacao
    if data.tzinfo is None:
        data = data.replace(tzinfo=timezone.utc)
    return inicio <= data <= fim


# ------------------------------------------------------------------
# Funções de cálculo
# ------------------------------------------------------------------

def _agregar_por_plano(tarefas: list[Tarefa]) -> list[VolumeporPlano]:
    """
    Agrupa tarefas por Plano e soma os indicadores financeiros de cada grupo.

    Tarefas sem plano definido são agrupadas em "Não definido".
    """
    acumulado: dict[str, dict] = {}

    for tarefa in tarefas:
        plano = tarefa.plano.strip() if tarefa.plano.strip() else "Não definido"

        if plano not in acumulado:
            acumulado[plano] = {
                "quantidade": 0,
                "faturamento_bruto": 0.0,
                "comissao": 0.0,
            }

        acumulado[plano]["quantidade"] += 1
        acumulado[plano]["faturamento_bruto"] += tarefa.faturamento_bruto
        acumulado[plano]["comissao"] += tarefa.comissao

    # Ordena por faturamento bruto decrescente para melhor visualização
    volumes = [
        VolumeporPlano(
            plano=plano,
            quantidade=dados["quantidade"],
            faturamento_bruto=dados["faturamento_bruto"],
            comissao=dados["comissao"],
        )
        for plano, dados in acumulado.items()
    ]
    return sorted(volumes, key=lambda v: v.faturamento_bruto, reverse=True)


# ------------------------------------------------------------------
# Ponto de entrada público do módulo
# ------------------------------------------------------------------

def calcular_financeiro(tarefas_pipeline: list[Tarefa]) -> RelatorioFinanceiro:
    """
    Calcula os indicadores financeiros da semana corrente.

    Filtra tarefas pela data de atualização dentro da semana atual
    (segunda-feira às 00:00 até domingo às 23:59 UTC).

    Args:
        tarefas_pipeline: Lista completa de Tarefa do Pipeline.

    Returns:
        RelatorioFinanceiro com todos os indicadores calculados.
    """
    inicio = _inicio_semana_atual()
    fim = _fim_semana_atual()

    tarefas_da_semana = [
        t for t in tarefas_pipeline
        if _tarefa_e_da_semana(t, inicio, fim)
    ]

    faturamento_bruto = sum(t.faturamento_bruto for t in tarefas_da_semana)
    faturamento_liquido = sum(t.faturamento_liquido for t in tarefas_da_semana)

    # Comissão acumulada considera TODAS as tarefas, não só da semana
    comissao_total = sum(t.comissao for t in tarefas_pipeline)

    return RelatorioFinanceiro(
        faturamento_bruto_semana=faturamento_bruto,
        faturamento_liquido_semana=faturamento_liquido,
        comissao_total=comissao_total,
        volume_por_plano=_agregar_por_plano(tarefas_da_semana),
        semana_inicio=inicio,
        semana_fim=fim,
    )
