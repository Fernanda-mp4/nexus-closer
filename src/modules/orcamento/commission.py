"""
Nexus Closer — Motor de Comissionamento Dinâmico.

Lê as taxas do banco config_business (sem hardcode).
Segue a arquitetura de CRMs como Salesforce: as regras vivem no banco,
não no código. O gestor pode alterar qualquer taxa sem redeploy.

Fórmula:
  1. taxa_base = base_comissao_propria  se lead_propria == True
               | base_comissao_empresa  caso contrário
  2. taxa_elite = taxa_bonus_elite      se fss_score == 16  (Status: ELITE)
                | 0                    caso contrário
  3. comissao = valor_final × (taxa_base + taxa_elite) / 100
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResultadoComissao:
    valor_base:           float   # valor final do orçamento usado como base
    taxa_base_pct:        float   # ex: 8.0 ou 10.0
    taxa_elite_pct:       float   # 0.0 ou taxa_bonus_elite
    taxa_total_pct:       float   # base + elite
    comissao_total:       float   # valor_base × taxa_total / 100
    is_lead_propria:      bool
    is_elite:             bool    # fss_score == 16
    trilha:               str     # descrição legível da trilha aplicada


def calcular_comissao(
    valor_final:   float,
    lead_propria:  bool,
    fss_score:     int,
    config:        dict[str, str],   # resultado de db.get_all_config()
) -> ResultadoComissao:
    """
    Calcula a comissão do vendedor com base nas variáveis de negócio do banco.

    Args:
        valor_final:  Total à vista do orçamento (após urgência, antes de desconto).
        lead_propria: True se a lead foi prospectada pelo próprio vendedor.
        fss_score:    Nota FSS atual do vendedor (1–16). 16 = Elite.
        config:       Dict com as variáveis de config_business.

    Returns:
        ResultadoComissao com breakdown completo.
    """
    def _f(chave: str, default: float) -> float:
        try:
            return float(config.get(chave, str(default)))
        except ValueError:
            return default

    taxa_base  = _f("base_comissao_propria", 10.0) if lead_propria \
                 else _f("base_comissao_empresa", 8.0)

    is_elite   = fss_score == 16
    taxa_elite = _f("taxa_bonus_elite", 2.0) if is_elite else 0.0
    taxa_total = taxa_base + taxa_elite

    comissao   = valor_final * taxa_total / 100.0

    trilha = "Lead Própria (Prospecção Ativa)" if lead_propria else "Lead da Empresa"
    if is_elite:
        trilha += f"  +  Bônus Elite FSS 16 (+{taxa_elite:.1f}%)"

    return ResultadoComissao(
        valor_base=valor_final,
        taxa_base_pct=taxa_base,
        taxa_elite_pct=taxa_elite,
        taxa_total_pct=taxa_total,
        comissao_total=comissao,
        is_lead_propria=lead_propria,
        is_elite=is_elite,
        trilha=trilha,
    )
