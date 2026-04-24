"""
Nexus Closer — Sales Score (FSS).

Calcula a nota de organização do CRM (1-4) e os alertas de bônus
com base no faturamento semanal coletado.

Regras:
  - Organização CRM: % de leads com plano + estagio_lead + valor_orcamento > 0
      0–40% = 1 (Iniciante)  |  40–65% = 2 (Bom)
      65–85% = 3 (Ótimo)     |  >85%   = 4 (Excepcional)
  - Faixas de bônus: R$5k / R$10k / R$15k / R$20k
  - Bônus Elite (2% extra): score_crm == 4
"""

from __future__ import annotations

from dataclasses import dataclass

# Faixas de bônus semanais em ordem crescente
_FAIXAS_BONUS: list[float] = [5_000.0, 10_000.0, 15_000.0, 20_000.0]


@dataclass(frozen=True)
class ResultadoFSS:
    score_crm:      int           # 1-4 — nota de organização do CRM
    nivel_crm:      str           # "Iniciante" / "Bom" / "Ótimo" / "Excepcional"
    faturamento:    float         # faturamento bruto semanal atual
    meta_atingida:  float         # última faixa de bônus já ultrapassada (0 se nenhuma)
    proxima_meta:   float | None  # próxima faixa; None se acima de todas
    valor_faltante: float | None  # quanto falta para proxima_meta
    bonus_elite:    bool          # True se score_crm == 4
    leads_total:    int
    leads_completas: int
    mensagem:       str           # mensagem motivacional principal
    alerta_bonus:   str           # "" ou texto do alerta de faixa


def calcular_fss(pipeline: list, faturamento_semana: float) -> ResultadoFSS:
    """
    Calcula o FSS Score a partir das leads ativas do pipeline.

    Args:
        pipeline:          Lista de Tarefa (todas — filtro interno exclui finais).
        faturamento_semana: Faturamento bruto coletado na semana atual.
    """
    _STATUS_FINAIS = {
        "fechado", "ganho", "perdido", "perdida", "cancelado",
        "arquivado", "arquivada", "encerrado", "encerrada",
        "closed", "won", "lost", "cancelled", "archived",
    }

    leads_ativas = [
        t for t in pipeline
        if t.status.lower() not in _STATUS_FINAIS
    ]
    total = len(leads_ativas)

    if total == 0:
        return ResultadoFSS(
            score_crm=1, nivel_crm="Iniciante",
            faturamento=faturamento_semana,
            meta_atingida=0.0, proxima_meta=_FAIXAS_BONUS[0],
            valor_faltante=max(0.0, _FAIXAS_BONUS[0] - faturamento_semana),
            bonus_elite=False,
            leads_total=0, leads_completas=0,
            mensagem="Nenhuma lead ativa no pipeline. Hora de prospectar!",
            alerta_bonus="",
        )

    # Completude: lead é "completa" se tem plano + estagio_lead + valor_orcamento > 0
    completas = sum(
        1 for t in leads_ativas
        if t.plano and t.estagio_lead and t.valor_orcamento > 0
    )
    ratio = completas / total

    if ratio > 0.85:
        score_crm, nivel_crm = 4, "Excepcional"
    elif ratio > 0.65:
        score_crm, nivel_crm = 3, "Ótimo"
    elif ratio > 0.40:
        score_crm, nivel_crm = 2, "Bom"
    else:
        score_crm, nivel_crm = 1, "Iniciante"

    # Faixas de bônus
    meta_atingida  = 0.0
    proxima_meta   = _FAIXAS_BONUS[0]
    valor_faltante = max(0.0, _FAIXAS_BONUS[0] - faturamento_semana)

    for faixa in _FAIXAS_BONUS:
        if faturamento_semana >= faixa:
            meta_atingida = faixa
        else:
            proxima_meta   = faixa
            valor_faltante = faixa - faturamento_semana
            break
    else:
        proxima_meta   = None
        valor_faltante = None

    # Mensagem motivacional baseada no score + faixa
    mensagem = _gerar_mensagem(score_crm, faturamento_semana, proxima_meta)

    # Alerta de bônus: mostra se falta menos de 20% da faixa
    alerta_bonus = ""
    if proxima_meta and valor_faltante is not None:
        limiar = proxima_meta * 0.20
        if valor_faltante <= limiar:
            vf = f"R$ {valor_faltante:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            alerta_bonus = f"Falta apenas {vf} para o próximo nível de bônus! Foque nas leads quentes."

    return ResultadoFSS(
        score_crm=score_crm,
        nivel_crm=nivel_crm,
        faturamento=faturamento_semana,
        meta_atingida=meta_atingida,
        proxima_meta=proxima_meta,
        valor_faltante=valor_faltante,
        bonus_elite=(score_crm == 4),
        leads_total=total,
        leads_completas=completas,
        mensagem=mensagem,
        alerta_bonus=alerta_bonus,
    )


def _gerar_mensagem(score_crm: int, faturamento: float, proxima_meta: float | None) -> str:
    if score_crm == 4:
        return (
            "Performance Impecável! CRM atualizado = bônus de 2% extra sobre a comissão. "
            "Continue registrando todos os históricos."
        )
    if score_crm == 3:
        return (
            "Ótima organização! Preencha o estágio e valor de orçamento nas leads restantes "
            "para atingir o nível Excepcional e desbloquear o bônus elite."
        )
    if score_crm == 2:
        return (
            "CRM no caminho certo. Lembre de registrar o plano e o valor do orçamento "
            "em cada lead para subir sua nota e garantir mais bônus."
        )
    # score 1
    return (
        "Organize o CRM agora: preencha Plano, Estágio e Valor do Orçamento "
        "em cada lead ativa para destravá-los no pipeline."
    )
