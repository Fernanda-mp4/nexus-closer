"""
Nexus Closer — Módulo Reporter.

Responsabilidade: compilar os dados do Radar e Financeiro em um
Resumo Semanal profissional exibido no terminal via rich.

Formato de saída: painéis, tabelas e texto formatado em português.
Nenhum dado sensível (tokens, IDs internos) é exibido.
"""

from datetime import datetime, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.models import RelatorioFinanceiro, RelatorioRadar

console = Console()


# ------------------------------------------------------------------
# Formatadores auxiliares
# ------------------------------------------------------------------

def _formatar_moeda(valor: float) -> str:
    """Formata um valor float para o padrão monetário brasileiro."""
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _formatar_data(dt: datetime) -> str:
    """Formata um datetime para DD/MM/YYYY."""
    dt_local = dt.astimezone() if dt.tzinfo else dt
    return dt_local.strftime("%d/%m/%Y")


def _formatar_data_hora(dt: datetime) -> str:
    """Formata um datetime para DD/MM/YYYY HH:MM."""
    dt_local = dt.astimezone() if dt.tzinfo else dt
    return dt_local.strftime("%d/%m/%Y %H:%M")


# ------------------------------------------------------------------
# Seções do relatório
# ------------------------------------------------------------------

def _secao_cabecalho(financeiro: RelatorioFinanceiro) -> Panel:
    """Painel de título com o período da semana."""
    periodo = (
        f"{_formatar_data(financeiro.semana_inicio)} "
        f"a {_formatar_data(financeiro.semana_fim)}"
    )
    gerado_em = datetime.now(tz=timezone.utc).astimezone().strftime("%d/%m/%Y às %H:%M")

    titulo = Text(justify="center")
    titulo.append("NEXUS CLOSER\n", style="bold white")
    titulo.append("RESUMO SEMANAL DE PERFORMANCE\n\n", style="bold cyan")
    titulo.append(f"Período: {periodo}\n", style="dim white")
    titulo.append(f"Gerado em: {gerado_em}", style="dim white")

    return Panel(titulo, border_style="cyan", padding=(1, 6))


def _secao_financeiro(financeiro: RelatorioFinanceiro) -> Panel:
    """Tabela com os indicadores financeiros da semana."""
    tabela = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
    tabela.add_column("Indicador", style="dim white", min_width=28)
    tabela.add_column("Valor", style="bold white", justify="right")

    tabela.add_row("Faturamento Bruto (semana)",  _formatar_moeda(financeiro.faturamento_bruto_semana))
    tabela.add_row("Faturamento Líquido (semana)", _formatar_moeda(financeiro.faturamento_liquido_semana))
    tabela.add_row("─" * 28, "─" * 16)
    tabela.add_row("[bold]Comissão Acumulada (total)[/bold]", f"[bold green]{_formatar_moeda(financeiro.comissao_total)}[/bold green]")

    return Panel(tabela, title="[bold cyan]FINANCEIRO[/bold cyan]", border_style="cyan", padding=(1, 2))


def _secao_volume_planos(financeiro: RelatorioFinanceiro) -> Panel:
    """Tabela de volume por plano."""
    tabela = Table(show_header=True, header_style="bold cyan", box=None, padding=(0, 2))
    tabela.add_column("Plano",              style="bold white",  min_width=16)
    tabela.add_column("Qtd",               style="white",        justify="center")
    tabela.add_column("Faturamento Bruto", style="bold green",   justify="right")
    tabela.add_column("Comissão",          style="cyan",         justify="right")

    if not financeiro.volume_por_plano:
        tabela.add_row("[dim]Sem fechamentos na semana[/dim]", "—", "—", "—")
    else:
        for vol in financeiro.volume_por_plano:
            tabela.add_row(
                vol.plano,
                str(vol.quantidade),
                _formatar_moeda(vol.faturamento_bruto),
                _formatar_moeda(vol.comissao),
            )

    return Panel(tabela, title="[bold cyan]VOLUME POR PLANO[/bold cyan]", border_style="cyan", padding=(1, 2))


def _secao_radar_48h(radar: RelatorioRadar) -> Panel:
    """Lista de leads paradas além do limite de 48h úteis."""
    if not radar.alertas_48h:
        conteudo = Text("Nenhum alerta de estagnação. Todas as leads estão em dia.", style="bold green")
        return Panel(conteudo, title="[bold green]RADAR — ESTAGNAÇÃO (48h+)[/bold green]", border_style="green", padding=(1, 2))

    tabela = Table(show_header=True, header_style="bold red", box=None, padding=(0, 2))
    tabela.add_column("Lead",     style="bold white", min_width=28)
    tabela.add_column("Status",   style="dim white",  min_width=14)
    tabela.add_column("Motivo",   style="yellow",     min_width=34)
    tabela.add_column("Link",     style="cyan")

    for alerta in radar.alertas_48h:
        tabela.add_row(
            alerta.tarefa.nome,
            alerta.tarefa.status,
            alerta.motivo,
            alerta.tarefa.link,
        )

    titulo = f"[bold red]RADAR — ESTAGNAÇÃO (48h+)  •  {len(radar.alertas_48h)} alerta(s)[/bold red]"
    return Panel(tabela, title=titulo, border_style="red", padding=(1, 2))


def _secao_radar_followup(radar: RelatorioRadar) -> Panel:
    """Lista de leads nos gatilhos de follow-up S1–S12."""
    if not radar.alertas_followup:
        conteudo = Text("Nenhuma lead em gatilho de follow-up ativo.", style="bold green")
        return Panel(conteudo, title="[bold green]RADAR — FOLLOW-UP (S1–S12)[/bold green]", border_style="green", padding=(1, 2))

    tabela = Table(show_header=True, header_style="bold yellow", box=None, padding=(0, 2))
    tabela.add_column("Lead",          style="bold white", min_width=28)
    tabela.add_column("Etapa",         style="bold yellow", min_width=8)
    tabela.add_column("Status",        style="dim white",  min_width=14)
    tabela.add_column("Últ. atualiz.", style="dim white",  min_width=16)
    tabela.add_column("Link",          style="cyan")

    for alerta in radar.alertas_followup:
        tabela.add_row(
            alerta.tarefa.nome,
            alerta.tarefa.etapa_followup,
            alerta.tarefa.status,
            _formatar_data_hora(alerta.tarefa.data_atualizacao),
            alerta.tarefa.link,
        )

    titulo = f"[bold yellow]RADAR — FOLLOW-UP (S1–S12)  •  {len(radar.alertas_followup)} lead(s)[/bold yellow]"
    return Panel(tabela, title=titulo, border_style="yellow", padding=(1, 2))


def _secao_auditoria(radar: RelatorioRadar, total_contratos: int) -> Panel:
    """Painel de auditoria com totais e links consolidados."""
    tabela = Table(show_header=False, box=None, padding=(0, 2))
    tabela.add_column("Métrica", style="dim white", min_width=30)
    tabela.add_column("Valor",   style="bold white")

    tabela.add_row("Total de leads no Pipeline",   str(radar.total_pipeline))
    tabela.add_row("Total de Contratos",            str(total_contratos))
    tabela.add_row("Alertas de estagnação (48h+)",  str(len(radar.alertas_48h)))
    tabela.add_row("Leads em follow-up (S1–S12)",   str(len(radar.alertas_followup)))

    return Panel(tabela, title="[bold cyan]AUDITORIA[/bold cyan]", border_style="cyan", padding=(1, 2))


# ------------------------------------------------------------------
# Ponto de entrada público do módulo
# ------------------------------------------------------------------

def gerar_relatorio(
    radar: RelatorioRadar,
    financeiro: RelatorioFinanceiro,
    total_contratos: int,
) -> None:
    """
    Imprime o Resumo Semanal completo no terminal.

    Compila as seções de Financeiro, Radar e Auditoria em painéis
    formatados com a biblioteca rich.

    Args:
        radar:            Relatório produzido pelo módulo Radar.
        financeiro:       Relatório produzido pelo módulo Financeiro.
        total_contratos:  Número total de tarefas na lista de Contratos.
    """
    console.print()
    console.print(_secao_cabecalho(financeiro))
    console.print()
    console.print(_secao_financeiro(financeiro))
    console.print(_secao_volume_planos(financeiro))
    console.print()
    console.print(_secao_radar_48h(radar))
    console.print(_secao_radar_followup(radar))
    console.print()
    console.print(_secao_auditoria(radar, total_contratos))
    console.print()
