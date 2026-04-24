"""
Nexus Closer — Motor de Cálculo de Orçamentos.

Regras do Guia de Precificação II:
  - Preço base por Tipo (A/B/C/D) × Nível × Páginas padrão incluídas  ← preço do plano FULL
  - Páginas excedentes: R$15 (Grad/Pós) ou R$20 (Mest/Dout)
  - Planos: Full (base) | Essencial (−R$100) | Master (+R$250)
  - Prazo:  Baixa 20d (0%) | Normal 15d (+20%) | Alta 12d (+35%) | Urgente 10d (+50%)
  - Prazo mínimo absoluto: 10 dias úteis (Urgente). Nenhuma entrega abaixo disso.
  - Parcelamento 12x: +15% sobre o valor final
  - Desconto manual máximo: 15% (trava de segurança)
"""

from dataclasses import dataclass
from enum import Enum


class TipoDemanda(str, Enum):
    A = "A"   # TCC / Monografia / Dissertação / Tese 
    B = "B"   # Pré projeto / Pré projeto + TCC / Pré projeto + TCC + Apresentação visual
    C = "C"   # Revisão ortográfica + Formatação / Revisão crítica / Revisão crítica + Apresentação visual
    D = "D"   # Demanda específica (consultar Redator-Chefe para validação e orçamento personalizado)


class Nivel(str, Enum):
    GRAD_POS  = "Graduação/Pós"
    MESTRADO  = "Mestrado"
    DOUTORADO = "Doutorado"


class Plano(str, Enum):
    ESSENCIAL = "Essencial"
    FULL      = "Full"
    MASTER    = "Master"


class Prazo(str, Enum):
    BAIXA   = "Baixa (20d)"
    NORMAL  = "Normal (15d)"
    ALTA    = "Alta (12d)"
    URGENTE = "Urgente (10d)"
    CRITICO = "Crítico (<10d)"   # Exclusivo Tipo C e D — exige consulta ao Redator-Chefe


# ------------------------------------------------------------------
# Tabela base: preço do plano Essencial para a faixa de páginas padrão incluídas
# Estrutura: {TipoDemanda: {Nivel: (preco_base, paginas_inclusas)}}
# ------------------------------------------------------------------
_TABELA_BASE: dict[TipoDemanda, dict[Nivel, tuple[float, int]]] = {
    TipoDemanda.A: {
        Nivel.GRAD_POS:  (997.98,  10),
        Nivel.MESTRADO:  (1497.98, 15),
        Nivel.DOUTORADO: (1997.98, 20),
    },
    TipoDemanda.B: {
        Nivel.GRAD_POS:  (1497.98, 15),
        Nivel.MESTRADO:  (1997.98, 20),
        Nivel.DOUTORADO: (2497.98, 25),
    },
    TipoDemanda.C: {
        Nivel.GRAD_POS:  (1997.98, 20),
        Nivel.MESTRADO:  (2497.98, 25),
        Nivel.DOUTORADO: (2997.98, 30),
    },
    TipoDemanda.D: {
        Nivel.GRAD_POS:  (697.98,  8),
        Nivel.MESTRADO:  (997.98,  10),
        Nivel.DOUTORADO: (1297.98, 12),
    },
}

# Custo por página excedente
_CUSTO_PAGINA_EXTRA: dict[Nivel, float] = {
    Nivel.GRAD_POS:  15.0,
    Nivel.MESTRADO:  20.0,
    Nivel.DOUTORADO: 20.0,
}

# Diferença de plano em relação ao Full (base da tabela)
# Full = preço base  |  Essencial = Full − R$100  |  Master = Full + R$250
_ADICIONAL_PLANO: dict[Plano, float] = {
    Plano.ESSENCIAL: -100.0,
    Plano.FULL:         0.0,
    Plano.MASTER:     250.0,
}

# Dias úteis representativos por prazo (referência para validação)
_DIAS_PRAZO: dict[Prazo, int] = {
    Prazo.BAIXA:   20,
    Prazo.NORMAL:  15,
    Prazo.ALTA:    12,
    Prazo.URGENTE: 10,
    Prazo.CRITICO: 0,    # < 10 dias; permitido apenas para Tipo C e D
}

# Taxa de urgência aplicada sobre o subtotal
_TAXA_URGENCIA: dict[Prazo, float] = {
    Prazo.BAIXA:   0.00,
    Prazo.NORMAL:  0.20,
    Prazo.ALTA:    0.35,
    Prazo.URGENTE: 0.50,
    Prazo.CRITICO: 0.50,   # mesma taxa máxima; requer aprovação do Redator-Chefe
}

# Tipos com prazo mínimo de 10 dias úteis (sem exceção)
_TIPOS_PRAZO_MINIMO = {TipoDemanda.A, TipoDemanda.B}

# Tipos que PERMITEM prazo Crítico (<10d) com aprovação do Redator-Chefe
_TIPOS_PRAZO_FLEXIVEL = {TipoDemanda.C, TipoDemanda.D}

# Adicional de parcelamento
_TAXA_PARCELAMENTO = 0.15
_DESCONTO_MAX      = 0.15   # trava: máximo 15%


@dataclass(frozen=True)
class ResultadoOrcamento:
    preco_base:        float
    paginas_excedentes: int
    custo_excedente:   float
    adicional_plano:   float
    subtotal:          float
    taxa_urgencia_pct: float
    valor_urgencia:    float
    total_avista:      float
    total_parcelado:   float  # +15%
    desconto_aplicado: float
    total_com_desconto: float
    aviso_desconto:    str    # "" ou mensagem de aviso


def calcular_orcamento(
    tipo:     TipoDemanda,
    nivel:    Nivel,
    plano:    Plano,
    paginas:  int,
    prazo:    Prazo,
    desconto: float = 0.0,   # valor absoluto em R$
) -> ResultadoOrcamento:
    """
    Calcula o orçamento completo conforme o Guia de Precificação II.

    Args:
        tipo:     Tipo de demanda (A/B/C/D)
        nivel:    Nível acadêmico
        plano:    Plano escolhido
        paginas:  Total de páginas do trabalho
        prazo:    Prazo de entrega (mínimo absoluto: Urgente = 10 dias úteis)
        desconto: Desconto manual em R$ (máximo 15% do total)

    Raises:
        ValueError: Se Tipo A ou B for solicitado com prazo inferior a 10 dias úteis.

    Returns:
        ResultadoOrcamento com todos os valores detalhados.
    """
    # Trava de prazo mínimo — Guia de Demandas Urgentes
    # Tipos A e B: mínimo absoluto de 10 dias úteis, sem exceção
    # Tipos C e D: permitem Crítico (<10d) COM aprovação do Redator-Chefe (validado na UI)
    if _DIAS_PRAZO[prazo] < 10:
        raise ValueError(
            "Prazo inferior a 10 dias exige autorização do Redator-Chefe / Setor de Orçamentos. "
            f"Tipo {tipo.value} — prazo mínimo sem autorização: Urgente (10d)."
        )

    preco_base, paginas_inclusas = _TABELA_BASE[tipo][nivel]

    # Páginas excedentes
    excedentes    = max(0, paginas - paginas_inclusas)
    custo_extra   = excedentes * _CUSTO_PAGINA_EXTRA[nivel]

    # Adicional de plano
    adicional_plano = _ADICIONAL_PLANO[plano]

    # Subtotal antes da urgência
    subtotal = preco_base + custo_extra + adicional_plano

    # Taxa de urgência
    taxa_pct      = _TAXA_URGENCIA[prazo]
    valor_urgencia = subtotal * taxa_pct
    total_avista  = subtotal + valor_urgencia

    # Parcelamento
    total_parcelado = total_avista * (1 + _TAXA_PARCELAMENTO)

    # Trava de desconto — máximo 15% do total à vista
    limite_desconto = total_avista * _DESCONTO_MAX
    aviso           = ""
    if desconto > limite_desconto:
        aviso    = (
            f"⚠️  Desconto limitado a 15% (R$ {limite_desconto:.2f}). "
            "Solicite autorização para valores maiores."
        )
        desconto = limite_desconto

    total_com_desconto = max(0.0, total_avista - desconto)

    return ResultadoOrcamento(
        preco_base=preco_base,
        paginas_excedentes=excedentes,
        custo_excedente=custo_extra,
        adicional_plano=adicional_plano,
        subtotal=subtotal,
        taxa_urgencia_pct=taxa_pct * 100,
        valor_urgencia=valor_urgencia,
        total_avista=total_avista,
        total_parcelado=total_parcelado,
        desconto_aplicado=desconto,
        total_com_desconto=total_com_desconto,
        aviso_desconto=aviso,
    )
