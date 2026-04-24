"""
Nexus Closer — Descritivos de Entregáveis por Tipo de Demanda e Plano.

Alinhado com TipoDemanda em calculator.py:
  A — TCC / Monografia / Dissertação / Tese
  B — Pré-Projeto / Pré-Projeto + TCC / Pré-Projeto + TCC + Apresentação Visual
  C — Revisão Ortográfica + Formatação / Revisão Crítica / Revisão Crítica + Apresentação Visual
  D — Demanda Específica (orçamento personalizado via Redator-Chefe)

Dados estáticos em memória — nenhuma consulta à API ou banco necessária.
"""

from __future__ import annotations

# Estrutura: {tipo_value: {plano_value: str}}
_DESCRITIVOS: dict[str, dict[str, str]] = {

    # ── Tipo A: TCC / Monografia / Dissertação / Tese ──────────────────
    "A": {
        "Essencial": (
            "✅  Tipo A — Plano Essencial\n"
            "• Produção completa: Introdução, Desenvolvimento e Conclusão\n"
            "• Referências bibliográficas (ABNT/APA conforme instituição)\n"
            "• Formatação acadêmica padrão da instituição\n"
            "• Revisão ortográfica e gramatical incluída"
        ),
        "Full": (
            "✅  Tipo A — Plano Full\n"
            "• Tudo do Plano Essencial, mais:\n"
            "• TCC 2 — correções e ajustes pós-avaliação do orientador\n"
            "• Apresentação Visual (mínimo 15 lâminas, layout profissional)\n"
            "• 1 rodada de revisão após entrega inicial"
        ),
        "Master": (
            "✅  Tipo A — Plano Master\n"
            "• Tudo do Plano Full, mais:\n"
            "• Revisão metodológica aprofundada com fundamentação teórica ampliada\n"
            "• Suporte à defesa: roteiro de apresentação oral e simulação de perguntas\n"
            "• Cronograma orientado às datas da banca\n"
            "• Atendimento prioritário via canal exclusivo"
        ),
    },

    # ── Tipo B: Pré-Projeto / Pré-Projeto + TCC / Pré-Projeto + TCC + Slides ──
    "B": {
        "Essencial": (
            "✅  Tipo B — Plano Essencial\n"
            "• Pré-Projeto standalone\n"
            "• Estrutura: Tema, Justificativa, Objetivos, Metodologia e Cronograma\n"
            "• Formatação conforme normas da instituição\n"
            "• Revisão ortográfica e gramatical incluída"
        ),
        "Full": (
            "✅  Tipo B — Plano Full\n"
            "• Tudo do Plano Essencial, mais:\n"
            "• TCC completo vinculado ao Pré-Projeto aprovado\n"
            "• Coerência metodológica garantida entre Pré-Projeto e TCC\n"
            "• 1 rodada de revisão após entrega do TCC"
        ),
        "Master": (
            "✅  Tipo B — Plano Master\n"
            "• Tudo do Plano Full, mais:\n"
            "• Apresentação visual profissional (mínimo 15 lâminas)\n"
            "• Suporte à defesa: roteiro oral e simulação de perguntas da banca\n"
            "• Atendimento prioritário via canal exclusivo"
        ),
    },

    # ── Tipo C: Revisão Ortográfica+Formatação / Revisão Crítica / Revisão+Slides ──
    "C": {
        "Essencial": (
            "✅  Tipo C — Plano Essencial\n"
            "• Revisão ortográfica e gramatical completa\n"
            "• Formatação acadêmica padrão da instituição\n"
            "• Adequação de referências bibliográficas (ABNT/APA)\n"
            "• Entrega com relatório de alterações realizadas"
        ),
        "Full": (
            "✅  Tipo C — Plano Full\n"
            "• Tudo do Plano Essencial, mais:\n"
            "• Revisão crítica: coesão argumentativa, estrutura lógica e consistência\n"
            "• Sugestões de reescrita em trechos com baixa clareza ou coerência\n"
            "• 1 rodada de ajustes pós-entrega"
        ),
        "Master": (
            "✅  Tipo C — Plano Master\n"
            "• Tudo do Plano Full, mais:\n"
            "• Apresentação visual profissional baseada no conteúdo revisado\n"
            "• Layout e design alinhados à identidade acadêmica da instituição\n"
            "• Atendimento prioritário via canal exclusivo"
        ),
    },

    # ── Tipo D: Demanda Específica ──────────────────────────────────────
    "D": {
        "Essencial": (
            "⚠️  Tipo D — Demanda Específica\n"
            "• Escopo personalizado — requer consulta ao Redator-Chefe\n"
            "• Prazo, entregáveis e valor definidos após briefing detalhado\n"
            "• Nenhum plano padrão aplicável: orçamento sob medida"
        ),
        "Full": (
            "⚠️  Tipo D — Demanda Específica\n"
            "• Escopo personalizado — requer consulta ao Redator-Chefe\n"
            "• Prazo, entregáveis e valor definidos após briefing detalhado\n"
            "• Nenhum plano padrão aplicável: orçamento sob medida"
        ),
        "Master": (
            "⚠️  Tipo D — Demanda Específica\n"
            "• Escopo personalizado — requer consulta ao Redator-Chefe\n"
            "• Prazo, entregáveis e valor definidos após briefing detalhado\n"
            "• Nenhum plano padrão aplicável: orçamento sob medida"
        ),
    },
}


def obter_descritivo(tipo: str, plano: str) -> str:
    """
    Retorna o descritivo de entregáveis para a combinação Tipo × Plano.

    Args:
        tipo:  "A", "B", "C" ou "D"
        plano: "Essencial", "Full" ou "Master"

    Returns:
        String multilinha com os entregáveis incluídos no plano.
        Retorna string vazia se a combinação não for encontrada.
    """
    return _DESCRITIVOS.get(tipo, {}).get(plano, "")
