"""
Nexus Closer — Fonte única de preços e configurações (CLAUDE.md §6).

Nenhuma lógica aqui — apenas constantes imutáveis.
Preços base do pacote Essencial variam por Guia; configure via config_business no DB.
"""

from typing import Final

# ── Modos de demanda ────────────────────────────────────────────────
GUIA_BAIXA_DEMANDA: Final[str] = "Guia I"
GUIA_ALTA_DEMANDA:  Final[str] = "Guia II"

# ── Pacotes — deltas em relação ao Full (base da tabela) ────────────
# Full     = preço base da tabela
# Essencial = Full − R$100
# Master    = Full + R$250
DELTA_FULL_PARA_ESSENCIAL: Final[float] = -100.0
DELTA_FULL_PARA_MASTER:    Final[float] =  250.0

# ── Urgência — prazo e acréscimo percentual ──────────────────────────
class Urgencia:
    """Configuração de um nível de urgência."""
    __slots__ = ("label", "prazo_dias", "acrescimo")

    def __init__(self, label: str, prazo_dias: int, acrescimo: float) -> None:
        self.label       = label
        self.prazo_dias  = prazo_dias
        self.acrescimo   = acrescimo   # ex: 0.20 = +20%

    def __repr__(self) -> str:
        return f"Urgencia({self.label!r}, {self.prazo_dias}d, +{self.acrescimo:.0%})"


URGENCIA_NORMAL:  Final[Urgencia] = Urgencia("Normal",  prazo_dias=15, acrescimo=0.20)
URGENCIA_ALTA:    Final[Urgencia] = Urgencia("Alta",    prazo_dias=12, acrescimo=0.35)
URGENCIA_URGENTE: Final[Urgencia] = Urgencia("Urgente", prazo_dias=10, acrescimo=0.50)

URGENCIAS: Final[tuple[Urgencia, ...]] = (URGENCIA_NORMAL, URGENCIA_ALTA, URGENCIA_URGENTE)

# ── Trava de prazo mínimo ────────────────────────────────────────────
# Prazos abaixo deste limite para A/B exigem autorização do Redator-Chefe.
PRAZO_MINIMO_TRAVA_DIAS: Final[int] = 10

# ── Estágios oficiais do ClickUp (CLAUDE.md §14 — NÃO ALTERAR) ───────
ESTAGIO_COLETANDO_DADOS:     Final[str] = "Coletando dados"
ESTAGIO_ENVIAR_ORCAMENTO:    Final[str] = "Enviar orçamento"
ESTAGIO_ORCAMENTO_ENVIADO:   Final[str] = "Orçamento enviado"
ESTAGIO_FOLLOWUP:            Final[str] = "Follow-up"
ESTAGIO_CONTRATO_ENVIADO:    Final[str] = "Contrato enviado"
ESTAGIO_CONTRATO_ASSINADO:   Final[str] = "Contrato assinado"
ESTAGIO_AGUARDANDO_PAGAMENTO: Final[str] = "Aguardando pagamento"
ESTAGIO_PAGAMENTO_REALIZADO: Final[str] = "Pagamento realizado"

# Estágios considerados "ativos" para fins de auditoria PULSE
ESTAGIOS_ATIVOS: Final[tuple[str, ...]] = (
    ESTAGIO_COLETANDO_DADOS,
    ESTAGIO_ENVIAR_ORCAMENTO,
    ESTAGIO_ORCAMENTO_ENVIADO,
    ESTAGIO_FOLLOWUP,
    ESTAGIO_CONTRATO_ENVIADO,
    ESTAGIO_AGUARDANDO_PAGAMENTO,
)

# ── Thresholds de urgência por estágio (CLAUDE.md §14 — NÃO ALTERAR) ─
# Estrutura: {estagio: (horas_ambar, horas_vermelho)}
URGENCIA_ESTAGIO: Final[dict[str, tuple[int, int]]] = {
    ESTAGIO_COLETANDO_DADOS:      (24,  48),
    ESTAGIO_ENVIAR_ORCAMENTO:     ( 4,   8),
    ESTAGIO_ORCAMENTO_ENVIADO:    (48,  72),   # usa lógica de Follow-up
    ESTAGIO_FOLLOWUP:             (48,  72),
    ESTAGIO_CONTRATO_ENVIADO:     (12,  24),
    ESTAGIO_AGUARDANDO_PAGAMENTO: ( 3,   7),
}

# Horas para classificar uma lead como GARGALO ou ZOMBIE
HORAS_GARGALO: Final[int] = 5 * 24    # 5 dias
HORAS_ZOMBIE:  Final[int] = 30 * 24   # 30 dias

# Campos obrigatórios por grupo de estágios
CAMPOS_OBRIGATORIOS: Final[dict[str, list[str]]] = {
    ESTAGIO_COLETANDO_DADOS:    ["nome", "genero", "faculdade", "curso"],
    ESTAGIO_ENVIAR_ORCAMENTO:   ["nome", "genero", "faculdade", "curso", "tema", "paginas"],
    ESTAGIO_ORCAMENTO_ENVIADO:  ["nome", "genero", "faculdade", "curso", "tema", "paginas", "plano"],
    ESTAGIO_FOLLOWUP:           ["nome", "genero", "faculdade", "curso", "tema", "paginas", "plano"],
    ESTAGIO_CONTRATO_ENVIADO:   ["nome", "genero", "faculdade", "curso", "tema", "paginas", "plano",
                                  "valor_fechado", "forma_pagamento"],
}
