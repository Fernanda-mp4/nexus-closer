"""
Nexus Closer — Modelos de Dados (DTOs).

Define as estruturas de dados imutáveis trafegadas entre os módulos.
Nenhuma lógica de negócio aqui — apenas contratos de dados.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Tarefa:
    """
    Representação limpa de uma tarefa do ClickUp.

    Todos os campos são extraídos e normalizados pelo ClickUpService.
    Campos financeiros estão em reais (float). Timestamps são datetime UTC.
    """

    nome: str
    status: str
    link: str
    origem: str                  # "pipeline" ou "contratos"
    data_criacao: datetime
    data_atualizacao: datetime
    faturamento_bruto: float
    faturamento_liquido: float
    comissao: float
    valor_orcamento: float
    estagio_lead: str
    plano: str
    objecao: str
    whatsapp: str
    etapa_followup: str
    closer_id: str = ""     # ID numérico do closer atribuído no ClickUp
    closer_nome: str = ""   # Nome do closer atribuído (ex: "João Silva")


@dataclass(frozen=True)
class DadosFaltando:
    """Lead com campos críticos vazios — alerta de dados incompletos."""

    tarefa: Tarefa
    campos_vazios: tuple         # ex: ("WhatsApp", "Proposta")
    dias_desde_criacao: int


@dataclass(frozen=True)
class AlertaRadar:
    """Um lead que disparou algum gatilho de monitoramento."""

    tarefa: Tarefa
    motivo: str          # Ex.: "Sem atualização há 52h úteis"
    horas_parado: float  # 0.0 para alertas que não são de tempo


@dataclass(frozen=True)
class RelatorioRadar:
    """Saída do módulo Radar após análise das leads."""

    alertas_48h: list[AlertaRadar]
    alertas_followup: list[AlertaRadar]
    total_pipeline: int


@dataclass(frozen=True)
class VolumeporPlano:
    """Agregado financeiro de um único plano."""

    plano: str
    quantidade: int
    faturamento_bruto: float
    comissao: float


@dataclass(frozen=True)
class RelatorioFinanceiro:
    """Saída do módulo Financeiro."""

    faturamento_bruto_semana: float
    faturamento_liquido_semana: float
    comissao_total: float
    volume_por_plano: list[VolumeporPlano]
    semana_inicio: datetime
    semana_fim: datetime
