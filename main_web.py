"""
Nexus Closer — Backend pywebview (V19).
Expõe funções Python ao JS via classe Api().
BotConversaWorker roda em thread separada (asyncio).
"""

import asyncio
import json
import logging
import re
import threading
from datetime import date, timedelta
from datetime import datetime, timezone
from pathlib import Path

import webview
from dotenv import load_dotenv

from src.models import Tarefa
from src.services.botconversa_service import BotConversaWorker
from src.services.clickup_service import ClickUpService
from src.services.database_manager import DatabaseManager

load_dotenv()

# Garante que o diretório de dados existe antes de configurar logging
(Path(__file__).resolve().parent / "data").mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(Path(__file__).resolve().parent / "data" / "nexus.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

_logger = logging.getLogger(__name__)


# ── Formatação de proposta para copy-paste ────────────────────────────

def _formatar_proposta(
    lead: str,
    tipo: str,
    nivel: str,
    plano: str,
    paginas: int,
    prazo: str,
    r: object,
    descritivo: str,
) -> str:
    """Gera texto limpo pronto para copiar no sistema."""
    sep = "─" * 44
    linhas = [
        f"PROPOSTA — {lead.upper()}",
        sep,
        f"Tipo: {tipo}  |  Nível: {nivel}  |  Plano: {plano}",
        f"Páginas: {paginas}  |  Prazo: {prazo}",
        "",
        descritivo,
        "",
        sep,
        f"Preço Base:           R$ {r.preco_base:>10,.2f}",
    ]
    if r.paginas_excedentes > 0:
        linhas.append(
            f"Páginas Excedentes:   R$ {r.custo_excedente:>10,.2f}"
            f"  (+{r.paginas_excedentes} pág.)"
        )
    if r.adicional_plano > 0:
        linhas.append(f"Adicional {plano}:  R$ {r.adicional_plano:>10,.2f}")
    if r.taxa_urgencia_pct > 0:
        linhas.append(
            f"Urgência ({r.taxa_urgencia_pct:.0f}%):       R$ {r.valor_urgencia:>10,.2f}"
        )
    linhas += [
        sep,
        f"TOTAL À VISTA:        R$ {r.total_avista:>10,.2f}",
        f"TOTAL PARCELADO 12x:  R$ {r.total_parcelado:>10,.2f}  (+15%)",
    ]
    if r.desconto_aplicado > 0:
        linhas.append(f"COM DESCONTO:         R$ {r.total_com_desconto:>10,.2f}")
    if r.aviso_desconto:
        linhas += ["", r.aviso_desconto]
    return "\n".join(linhas)


# ── Serialização de Tarefa para o JS ──────────────────────────────────

def _tarefa_para_js(t: Tarefa) -> dict:
    return {
        "nome":             t.nome,
        "status":           t.status,
        "link":             t.link,
        "estagio_lead":     t.estagio_lead,
        "valor_orcamento":  t.valor_orcamento,
        "whatsapp":         t.whatsapp,
        "etapa_followup":   t.etapa_followup,
        "data_atualizacao": t.data_atualizacao.isoformat(),
        "plano":            t.plano,
        "objecao":          t.objecao,
        # Dr./Dra. não é campo do ClickUp — tratamento de gênero feito pela UI
        # via regex no nome quando o Closer abre o plano de ação
        "titulo":           "",
        "closer_id":        t.closer_id,
        "closer_nome":      t.closer_nome,
        "data_criacao":     t.data_criacao.isoformat(),
        # FSS: calculado por closer em sincronizar_radar()
        "fss":              0,
    }


# ── API exposta ao JS ──────────────────────────────────────────────

class Api:
    """Todos os métodos acessíveis via window.pywebview.api."""

    def __init__(self) -> None:
        self._window: "webview.Window | None" = None
        self._db = DatabaseManager()

    def _bind(self, window: "webview.Window") -> None:
        self._window = window

    def _js(self, expr: str) -> None:
        """Avalia expressão JS na janela, se disponível."""
        if self._window is not None:
            try:
                self._window.evaluate_js(expr)
            except Exception as exc:
                _logger.warning("evaluate_js: %s", exc)

    def _log(self, mensagem: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        linha = f"[{ts}] {mensagem}"
        self._js(f"receberLog({json.dumps(linha)})")

    # ── Utilitários ────────────────────────────────────────────────

    def obter_clipboard(self) -> str:
        """Retorna texto do clipboard via tkinter (funciona em file:// do pywebview)."""
        try:
            import tkinter as tk
            root = tk.Tk()
            root.withdraw()
            texto = root.clipboard_get()
            root.destroy()
            return texto
        except Exception:
            return ""

    # ── Notificações ───────────────────────────────────────────────

    def resolver_notificacao(self, nid: int) -> None:
        try:
            self._db.resolver_notificacao(nid)
        except Exception as exc:
            _logger.error("resolver_notificacao: %s", exc)
            self._log(f"[ERR] resolver_notificacao: {exc}")

    def adiar_notificacao(self, nid: int) -> None:
        amanha = (date.today() + timedelta(days=1)).isoformat()
        try:
            self._db.adiar_notificacao(nid, amanha)
        except Exception as exc:
            _logger.error("adiar_notificacao: %s", exc)
            self._log(f"[ERR] adiar_notificacao: {exc}")

    def carregar_notificacoes_pendentes(self) -> None:
        """Carrega notificações pendentes do banco e envia ao JS."""
        hoje = date.today().isoformat()
        try:
            notifs = self._db.carregar_notificacoes_pendentes(hoje)
            for n in notifs:
                self._js(
                    f"mostrarNotificacao("
                    f"{json.dumps(n['tipo'])},"
                    f"{json.dumps(n['titulo'])},"
                    f"{json.dumps(n['mensagem'])},"
                    f"{json.dumps(n['id'])})"
                )
        except Exception as exc:
            _logger.error("carregar_notificacoes_pendentes: %s", exc)
            self._log(f"[ERR] notificações: {exc}")

    # ── PDF ─────────────────────────────────────────────────────────

    def gerar_pdf_proposta(
        self,
        nome_lead: str,
        titulo: str,          # "Dr." ou "Dra."
        tipo: str,
        nivel: str,
        plano: str,
        paginas: int,
        prazo: str,
        desconto: float = 0.0,
    ) -> dict:
        """
        Gera PDF da proposta sobre o template Canva.
        Template esperado: assets/template_proposta.pdf
        Quando o template não existir, retorna status 'template_pendente'.
        """
        from src.modules.orcamento.calculator import (
            TipoDemanda, Nivel, Plano, Prazo, calcular_orcamento,
        )

        _base     = Path(__file__).resolve().parent
        _template = _base / "assets" / "template_proposta.pdf"
        _saida    = _base / "assets" / "propostas"

        if not _template.exists():
            return {"status": "template_pendente"}

        try:
            import fitz  # PyMuPDF

            resultado = calcular_orcamento(
                tipo=TipoDemanda(tipo),
                nivel=Nivel(nivel),
                plano=Plano(plano),
                paginas=int(paginas),
                prazo=Prazo(prazo),
                desconto=float(desconto),
            )

            # ── Dados a injetar (coordenadas serão definidas após receber o template) ──
            # campos: titulo, nome_lead, nivel, plano, paginas, prazo,
            #         resultado.total_avista, resultado.total_parcelado,
            #         resultado.total_com_desconto
            # TODO: preencher _CAMPOS_PDF com as coordenadas do template Canva
            _CAMPOS_PDF: list[dict] = [
                # Exemplo de estrutura:
                # {"page": 0, "x": 100, "y": 200, "texto": f"{titulo} {nome_lead}",
                #  "fontsize": 14, "cor": (0, 0, 0)}
            ]

            # Validação M-3: prefixo Dr./Dra. não deve estar no nome do ClickUp
            if re.search(r'\bDr\.\s|\bDra\.\s', nome_lead, re.IGNORECASE):
                return {
                    "status": "alerta",
                    "mensagem": (
                        "O nome da lead contém 'Dr.' ou 'Dra.'. "
                        "Remova o prefixo no ClickUp — o sistema insere automaticamente na proposta."
                    ),
                }

            # Validação M-3: caracteres inválidos no nome de arquivo Windows
            _CHARS_INVALIDOS = r'[<>:"/\\|?*]'
            if re.search(_CHARS_INVALIDOS, nome_lead):
                chars = set(re.findall(_CHARS_INVALIDOS, nome_lead))
                return {
                    "status": "alerta",
                    "mensagem": (
                        f"O nome da lead contém caracteres inválidos: {' '.join(sorted(chars))}. "
                        "Corrija o nome no ClickUp antes de gerar a proposta."
                    ),
                }

            _saida.mkdir(parents=True, exist_ok=True)
            hoje = date.today().strftime("%d.%m.%Y")
            nome_arquivo = f"Proposta Comercial - {titulo} {nome_lead} [{hoje}].pdf"
            caminho_pdf  = _saida / nome_arquivo

            doc = fitz.open(str(_template))
            for campo in _CAMPOS_PDF:
                pg = doc[campo["page"]]
                pg.insert_text(
                    (campo["x"], campo["y"]),
                    campo["texto"],
                    fontsize=campo.get("fontsize", 12),
                    color=campo.get("cor", (0, 0, 0)),
                )
            doc.save(str(caminho_pdf))
            doc.close()

            import os
            os.startfile(str(caminho_pdf))

            return {"status": "ok", "caminho": str(caminho_pdf)}

        except Exception as exc:
            _logger.error("gerar_pdf_proposta: %s", exc)
            return {"status": "erro", "mensagem": str(exc)}

    # ── Pipeline ────────────────────────────────────────────────────

    def sincronizar_radar(self) -> list:
        """Sincroniza leads do ClickUp (delta sync). Retorna lista de dicts ao JS."""
        self._log("[SYS] SINCRONIZANDO RADAR...")
        try:
            clickup = ClickUpService()
        except EnvironmentError as exc:
            self._log(f"[WARN] ClickUp não configurado: {exc}")
            return []

        try:
            desde_ms = self._db.ultima_sincronizacao_ms(clickup.lista_pipeline_id)
            tarefas = clickup.buscar_pipeline(desde_ms=desde_ms)

            if tarefas:
                self._db.salvar_tarefas(tarefas)
                self._db.registrar_sincronizacao(clickup.lista_pipeline_id, tarefas)

            leads_qualif  = self._db.leads_qualificacao()
            leads_fu      = self._db.leads_followup()
            leads_ativas  = leads_qualif + leads_fu

            # Fallback: se estagio_lead não estiver preenchido, exibe todas as ativas
            if not leads_ativas:
                leads_ativas = self._db.leads_ativas()
                self._log(f"[WARN] estagio_lead vazio no DB — exibindo {len(leads_ativas)} leads ativas (fallback)")

            self._log(f"[OK] RADAR SYNC — {len(tarefas)} delta(s) | {len(leads_ativas)} lead(s) ativas")

            # ── FSS Score: calcula apenas para leads do closer atual ──
            try:
                from src.modules.fss.score import calcular_fss
                usuario_id = ""
                try:
                    usuario = clickup.fetch_current_user()
                    usuario_id = usuario.get("id", "")
                except Exception:
                    pass

                todas_pipeline = leads_ativas
                leads_do_closer = (
                    [t for t in todas_pipeline if t.closer_id == usuario_id]
                    if usuario_id else todas_pipeline
                )
                fss_resultado = calcular_fss(leads_do_closer, faturamento_semana=0.0)
                self._js(
                    f"receberFssScore({fss_resultado.score_crm}, "
                    f"{json.dumps(fss_resultado.nivel_crm)}, "
                    f"{fss_resultado.leads_total}, "
                    f"{fss_resultado.leads_completas})"
                )
            except Exception as exc:
                _logger.warning("FSS score calc: %s", exc)

            return [_tarefa_para_js(t) for t in leads_ativas]

        except Exception as exc:
            _logger.error("sincronizar_radar: %s", exc)
            self._log(f"[ERR] sincronizar_radar: {exc}")
            return []

    def auditar_pipeline(self, forcado: bool = False) -> dict:
        """
        Sincroniza o ClickUp (full sync) e audita estágios de todas as leads ativas.
        Chamado automaticamente pelo PULSE (07h/19h) ou via botão FORÇAR AUDITORIA.
        Envia relatório ao JS via receberRelatorioPulse().
        """
        from src.constants import (
            ESTAGIOS_ATIVOS, URGENCIA_ESTAGIO, HORAS_GARGALO, HORAS_ZOMBIE,
        )

        horario       = datetime.now().strftime("%H:%M:%S")
        tipo_relatorio = "FORÇADO" if forcado else "PULSE"
        self._log(f"[{tipo_relatorio}] AUDITORIA INICIADA — {horario}")

        # ── 1. Sincronizar ClickUp ───────────────────────────────────
        # forcado=True → full sync (sem cache, dados frescos)
        # forcado=False → delta sync (só tarefas alteradas desde última sync)
        try:
            clickup = ClickUpService()
            desde_ms = None if forcado else self._db.ultima_sincronizacao_ms(clickup.lista_pipeline_id)
            tarefas_delta = clickup.buscar_pipeline(desde_ms=desde_ms)
            if tarefas_delta:
                self._db.salvar_tarefas(tarefas_delta)
                self._db.registrar_sincronizacao(clickup.lista_pipeline_id, tarefas_delta)
            # Para auditoria, usa todas as leads ativas do DB (não só o delta)
            tarefas = self._db.leads_qualificacao() + self._db.leads_followup()
            self._log(f"[{tipo_relatorio}] Sync — {len(tarefas_delta)} delta(s) | {len(tarefas)} ativa(s) no DB")
        except EnvironmentError as exc:
            self._log(f"[WARN] ClickUp não configurado: {exc}")
            return {"status": "erro", "mensagem": str(exc)}
        except Exception as exc:
            _logger.error("auditar_pipeline sync: %s", exc)
            self._log(f"[ERR] auditar_pipeline: {exc}")
            return {"status": "erro", "mensagem": str(exc)}

        # ── 2. Auditar estágios ──────────────────────────────────────
        agora      = datetime.now(timezone.utc)
        pendencias = []
        gargalos   = []
        zombies    = []
        total_ok   = 0
        total_ativas = 0

        for t in tarefas:
            if t.estagio_lead not in ESTAGIOS_ATIVOS:
                continue
            total_ativas += 1

            dt = t.data_atualizacao
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            horas = (agora - dt).total_seconds() / 3600

            thresholds = URGENCIA_ESTAGIO.get(t.estagio_lead, (24, 48))

            if horas > HORAS_ZOMBIE:
                zombies.append({"nome": t.nome, "estagio": t.estagio_lead, "horas": round(horas, 1)})
                self._log(
                    f"[AUDIT_FAIL] Lead: {t.nome} // ZOMBIE — "
                    f"{int(horas // 24)}d em '{t.estagio_lead}'"
                )
            elif horas > HORAS_GARGALO:
                gargalos.append({"nome": t.nome, "estagio": t.estagio_lead, "horas": round(horas, 1)})
                self._log(
                    f"[AUDIT_FAIL] Lead: {t.nome} // GARGALO — "
                    f"{int(horas // 24)}d em '{t.estagio_lead}'"
                )
            elif horas > 24:
                nivel = "vermelho" if horas > thresholds[1] else "ambar"
                pendencias.append({"nome": t.nome, "estagio": t.estagio_lead, "horas": round(horas, 1), "nivel": nivel})
                self._log(
                    f"[AUDIT_FAIL] Lead: {t.nome} // "
                    f"Estágio sem atualização há {round(horas, 1)}h — '{t.estagio_lead}'"
                )
            else:
                total_ok += 1

        # ── 3. Leads sem closer atribuído > 2h ──────────────────────
        sem_closer = []
        for t in tarefas:
            if t.estagio_lead not in ESTAGIOS_ATIVOS or t.closer_id:
                continue
            dc = t.data_criacao
            if dc.tzinfo is None:
                dc = dc.replace(tzinfo=timezone.utc)
            horas_sem_closer = (agora - dc).total_seconds() / 3600
            if horas_sem_closer > 2:
                sem_closer.append({"nome": t.nome, "horas": round(horas_sem_closer, 1)})

        if sem_closer:
            def _fmt_h(h: float) -> str:
                return f"{int(h / 24)}d" if h >= 24 else f"{h:.0f}h"
            n = len(sem_closer)
            self._log(f"[AVISO] {n} lead(s) sem closer atribuído")
            detalhes = "; ".join(f"{l['nome'].split()[0]} ({_fmt_h(l['horas'])})" for l in sem_closer)
            msg = f"{n} lead(s) sem closer: {detalhes}"
            self._js(f"mostrarAviso('LEADS SEM CLOSER', {json.dumps(msg)})")

        total_falhas = len(pendencias) + len(gargalos) + len(zombies)
        pct_ok = round((total_ok / total_ativas * 100) if total_ativas > 0 else 100.0, 1)

        if total_falhas == 0:
            self._log(f"[{tipo_relatorio}] ✓ Pipeline limpo — {total_ativas} leads, 100% atualizadas")
        else:
            self._log(f"[{tipo_relatorio}] {total_falhas} pendência(s) — {pct_ok}% do pipeline atualizado")

        relatorio = {
            "status":       "ok",
            "horario":      horario,
            "tipo":         tipo_relatorio,
            "total_ativas": total_ativas,
            "total_ok":     total_ok,
            "pct_ok":       pct_ok,
            "pendencias":   pendencias,
            "gargalos":     gargalos,
            "zombies":      zombies,
            "sem_closer":   sem_closer,
        }
        self._js(f"receberRelatorioPulse({json.dumps(relatorio, ensure_ascii=False)})")
        return relatorio

    # ── PULSE PAGE — Dados para a página dedicada de relatório ─────

    def obter_relatorio_pulse(self) -> dict:
        """
        Gera dados para a página PULSE (Battle Plan 07h / Fechamento 19h).
        Categoriza todas as leads ativas por criticidade.
        """
        from src.constants import ESTAGIOS_ATIVOS, URGENCIA_ESTAGIO, HORAS_GARGALO, HORAS_ZOMBIE

        agora      = datetime.now(timezone.utc)
        hora_local = datetime.now().hour
        tipo       = "BATTLE PLAN" if hora_local < 12 else "FECHAMENTO"
        horario    = datetime.now().strftime("%H:%M")
        data_str   = datetime.now().strftime("%d/%m/%Y")

        # Sync ClickUp em background — relatório usa cache local imediatamente
        import threading as _threading
        def _sync_bg():
            try:
                cu  = ClickUpService()
                ms  = self._db.ultima_sincronizacao_ms(cu.lista_pipeline_id)
                d   = cu.buscar_pipeline(desde_ms=ms)
                if d:
                    self._db.salvar_tarefas(d)
                    self._db.registrar_sincronizacao(cu.lista_pipeline_id, d)
            except Exception as exc:
                self._log(f"[WARN] Sync pulse bg: {exc}")
        _threading.Thread(target=_sync_bg, daemon=True).start()

        tarefas = self._db.leads_qualificacao() + self._db.leads_followup()

        critico      = []
        atencao      = []
        normal       = []
        sem_estagio  = []
        followups_hoje   = []
        atualizadas_hoje = []

        # Início do dia local em UTC para filtro "atualizadas hoje"
        hoje_local      = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        hoje_inicio_utc = hoje_local.astimezone(timezone.utc)

        def _fmt_tempo(h: float) -> str:
            if h >= 48:
                return f"{int(h // 24)}d {int(h % 24)}h"
            return f"{round(h, 1)}h"

        for t in tarefas:
            dt = t.data_atualizacao
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            horas = (agora - dt).total_seconds() / 3600

            # Leads atualizadas hoje (seção Fechamento)
            if dt >= hoje_inicio_utc:
                atualizadas_hoje.append({
                    "nome":   t.nome,
                    "estagio": t.estagio_lead or t.status,
                    "link":   t.link,
                })

            # Follow-ups com etapa definida
            if t.etapa_followup:
                followups_hoje.append({
                    "nome":  t.nome,
                    "etapa": t.etapa_followup,
                    "link":  t.link,
                })

            # Classificação por criticidade
            # Se estagio_lead não preenchido, usa "Coletando dados" como padrão
            # (lead ativa mas closer ainda não registrou o estágio)
            estagio = t.estagio_lead
            estagio_ausente = not estagio or estagio not in ESTAGIOS_ATIVOS
            if estagio_ausente:
                estagio = "Coletando dados"
                sem_estagio.append({
                    "nome":         t.nome,
                    "board_status": t.status,
                    "tempo":        _fmt_tempo(horas),
                    "horas_raw":    horas,
                    "link":         t.link,
                })

            thresholds            = URGENCIA_ESTAGIO.get(estagio, (24, 48))
            h_ambar, h_vermelho   = thresholds
            info = {
                "nome":      t.nome,
                "estagio":   estagio,
                "tempo":     _fmt_tempo(horas),
                "horas_raw": horas,
                "link":      t.link,
                "motivo":    "",
            }

            if horas > HORAS_ZOMBIE:
                info["motivo"] = f"ZOMBIE — {int(horas // 24)} dias parada"
                critico.append(info)
            elif horas > HORAS_GARGALO:
                info["motivo"] = f"GARGALO — {int(horas // 24)} dias parada"
                critico.append(info)
            elif horas > h_vermelho:
                info["motivo"] = f"LIMITE CRÍTICO — {_fmt_tempo(horas)} (máx {h_vermelho}h)"
                critico.append(info)
            elif horas > h_ambar:
                info["motivo"] = f"ATENÇÃO — {_fmt_tempo(horas)} (limite {h_ambar}h)"
                atencao.append(info)
            else:
                info["motivo"] = f"OK — {_fmt_tempo(horas)} no estágio"
                normal.append(info)

        total  = len(tarefas)
        pct_ok = round((len(normal) / total * 100) if total > 0 else 100.0, 1)

        # ── Enriquecimento do relatório ─────────────────────────────────
        _ACOES_ESTAGIO = {
            "Coletando dados":      "Completar coleta: nome completo, gênero, faculdade e curso.",
            "Enviar orçamento":     "URGENTE — Enviar orçamento agora. Cada hora perdida = lead fria.",
            "Orçamento enviado":    "Follow-up do orçamento: confirme se recebeu e esclareça dúvidas.",
            "Follow-up":            "Executar follow-up ativo. Verifique resposta e avance o estágio.",
            "Contrato enviado":     "CRÍTICO — Contato imediato para checar assinatura do contrato.",
            "Contrato assinado":    "Confirmar prazo e forma de pagamento com o lead.",
            "Aguardando pagamento": "MONEY ON TABLE — Acionar lead agora para confirmação do pagamento.",
            "Pagamento realizado":  "Encaminhar para produção e registrar fechamento no ClickUp.",
        }
        _acao_padrao = "Atualizar estágio no ClickUp e realizar contato proativo."

        n_critico = len(critico)
        n_atencao = len(atencao)

        # Plano de ação — ordenado do mais antigo ao mais recente ("último pro primeiro")
        todos_leads = (
            [(l, "CRÍTICO") for l in critico] +
            [(l, "ATENÇÃO")  for l in atencao]  +
            [(l, "NORMAL")   for l in normal]
        )
        todos_leads_sorted = sorted(todos_leads, key=lambda x: x[0].get("horas_raw", 0), reverse=True)
        plano_acao = [
            {
                "passo":      i,
                "lead":       l["nome"],
                "estagio":    l.get("estagio", l.get("board_status", "—")),
                "tempo":      l["tempo"],
                "prioridade": prioridade,
                "acao":       _ACOES_ESTAGIO.get(l.get("estagio", ""), _acao_padrao),
                "motivo":     l.get("motivo", ""),
            }
            for i, (l, prioridade) in enumerate(todos_leads_sorted[:12], 1)
        ]
        urgencias = [
            f"{l['nome']} — {l.get('estagio','?')} — {l.get('motivo','')}"
            for l in critico[:5]
        ]

        # Introdução
        if tipo == "BATTLE PLAN":
            intro = (
                f"Battle Plan de {data_str}. "
                f"Pipeline com {total} lead(s) ativa(s): "
                f"{n_critico} crítica(s) exigindo ação imediata, "
                f"{n_atencao} em atenção e {len(normal)} dentro do prazo. "
                f"O plano abaixo prioriza as leads paradas há mais tempo — execute em ordem."
            )
        else:
            intro = (
                f"Relatório de Fechamento de {data_str}. "
                f"Confira abaixo o resumo do que foi realizado hoje, "
                f"o que ficou pendente e as orientações para amanhã."
            )

        # Checklist (Fechamento 19h) — pendências atualizadas vs pendentes
        atualizadas_nomes = {a["nome"] for a in atualizadas_hoje}
        checklist: list[dict] = []
        for l in critico:
            checklist.append({
                "item":    f"[CRÍTICO] {l['nome']} — {l.get('estagio','?')}",
                "status":  "ok" if l["nome"] in atualizadas_nomes else "pendente",
                "detalhe": l.get("motivo", ""),
            })
        for l in atencao[:5]:
            checklist.append({
                "item":    f"[ATENÇÃO] {l['nome']} — {l.get('estagio','?')}",
                "status":  "ok" if l["nome"] in atualizadas_nomes else "pendente",
                "detalhe": l.get("motivo", ""),
            })
        for l in sem_estagio[:3]:
            checklist.append({
                "item":    f"[ESTÁGIO] {l['nome']} — sem estágio definido",
                "status":  "ok" if l["nome"] in atualizadas_nomes else "pendente",
                "detalhe": "Atualizar estágio no ClickUp",
            })

        # Análise (Fechamento)
        feitos_n   = len(atualizadas_hoje)
        pendentes_n = sum(1 for c in checklist if c["status"] == "pendente")
        taxa       = round(feitos_n / max(total, 1) * 100, 1)
        avaliacao  = "Excelente" if taxa >= 80 else "Bom" if taxa >= 50 else "Precisa melhorar"
        analise    = {
            "feito":            feitos_n,
            "pendente":         pendentes_n,
            "total_ativo":      total,
            "taxa_atualizacao": taxa,
            "avaliacao":        avaliacao,
        }

        # Dicas (Fechamento)
        dicas: list[str] = []
        if n_critico > 0:
            dicas.append(f"Amanhã: priorize as {n_critico} lead(s) crítica(s) antes de qualquer outra atividade.")
        if sem_estagio:
            dicas.append(f"Atualize o estágio de {len(sem_estagio)} lead(s) no ClickUp antes das 8h.")
        if taxa < 50:
            dicas.append("Experimente blocos de 25 min (Pomodoro) para contatos em sequência — evita dispersão.")
        if followups_hoje:
            dicas.append(f"Você tem {len(followups_hoje)} follow-up(s) na sequência 60d — execute antes do meio-dia.")
        dicas.append("Configure lembretes matinais de follow-up para nunca perder um prazo crítico.")

        # Funil por estágio (contagem real)
        from collections import Counter as _Counter
        _funil_raw = _Counter(
            (t.estagio_lead or "Sem estágio") for t in tarefas
        )
        funil = [{"estagio": k, "total": v}
                 for k, v in sorted(_funil_raw.items(), key=lambda x: -x[1])]

        # Metas do dia (BATTLE PLAN) — específicas, mensuráveis
        metas_dia: list[str] = []
        if n_critico > 0:
            metas_dia.append(
                f"Atender {n_critico} lead(s) crítica(s) até as 10h — mais antiga primeiro")
        if followups_hoje:
            metas_dia.append(
                f"Executar {len(followups_hoje)} follow-up(s) da sequência 60 dias antes do meio-dia")
        if sem_estagio:
            metas_dia.append(
                f"Registrar estágio de {len(sem_estagio)} lead(s) sem preenchimento no ClickUp")
        metas_dia.append("Encerrar todos atendimentos concluídos com fluxo Encerramento no BotConversa")
        metas_dia.append("Verificar conversas abertas — nenhuma lead sem resposta ao final do dia")

        # Blocos de tempo estratégicos — baseados nos dados reais
        _n_norm = len(normal)
        blocos_tempo = [
            {"bloco": "08:00 – 09:30",
             "foco": "LEADS CRÍTICAS",
             "descricao": (f"Atender as {n_critico} lead(s) crítica(s) em ordem hierárquica."
                           if n_critico > 0 else
                           "Nenhuma lead crítica — adiantar leads em atenção.")},
            {"bloco": "09:30 – 09:45",
             "foco": "INTERVALO",
             "descricao": "Intervalo. Registre pendências no ClickUp antes de continuar."},
            {"bloco": "09:45 – 11:30",
             "foco": "ATENÇÃO E FOLLOW-UPS",
             "descricao": (f"Atender {n_atencao} lead(s) em atenção e "
                           f"{len(followups_hoje)} follow-up(s) do dia.")},
            {"bloco": "11:30 – 12:00",
             "foco": "PIPELINE / CLICKUP",
             "descricao": "Atualizar estágios e custom fields de todas as leads atendidas hoje."},
            {"bloco": "13:00 – 14:30",
             "foco": "BOTCONVERSA E LEADS NORMAIS",
             "descricao": (f"Verificar conversas abertas. Atender {_n_norm} lead(s) dentro do prazo.")},
            {"bloco": "14:30 – 15:00",
             "foco": "ORGANIZAÇÃO WHATSAPP",
             "descricao": "Etiquetar leads perdidas como Perdida e arquivar. Encerrar fluxos."},
        ]
        if sem_estagio:
            blocos_tempo.append({
                "bloco": "15:00 – 17:00",
                "foco": "LEADS SEM ESTÁGIO",
                "descricao": f"Preencher estágio e dados de {len(sem_estagio)} lead(s) no ClickUp."
            })

        # Conclusão — direta, sem motivacional
        if tipo == "BATTLE PLAN":
            partes = []
            if n_critico > 0:
                partes.append(f"{n_critico} crítica(s)")
            if followups_hoje:
                partes.append(f"{len(followups_hoje)} follow-up(s)")
            if sem_estagio:
                partes.append(f"{len(sem_estagio)} sem estágio")
            conclusao = (
                f"Pipeline: {total} leads ativas. "
                + (f"Pendências: {', '.join(partes)}. " if partes else "Sem pendências críticas. ")
                + "Execute o plano na ordem acima."
            )
        else:
            conclusao = (
                f"{feitos_n} de {total} leads atualizadas hoje ({taxa}%). "
                + (f"{pendentes_n} pendência(s) carregam para amanhã. " if pendentes_n > 0 else "")
                + (f"{n_critico} lead(s) crítica(s) para resolver amanhã." if n_critico > 0
                   else "Pipeline sem críticas para amanhã.")
            )

        relatorio_pulse = {
            "status":           "ok",
            "tipo":             tipo,
            "horario":          horario,
            "data":             data_str,
            "intro":            intro,
            "plano_acao":       plano_acao,
            "urgencias":        urgencias,
            "checklist":        checklist,
            "analise":          analise,
            "dicas":            dicas,
            "conclusao":        conclusao,
            "metas_dia":        metas_dia,
            "blocos_tempo":     blocos_tempo,
            "funil":            funil,
            "followups_detalhe": [{"nome": f["nome"], "etapa": f["etapa"]} for f in followups_hoje[:10]],
            "critico":          critico,
            "atencao":          atencao,
            "normal":           normal,
            "sem_estagio":      sem_estagio,
            "followups_hoje":   followups_hoje,
            "atualizadas_hoje": atualizadas_hoje,
            "stats": {
                "total":       total,
                "critico":     n_critico,
                "atencao":     n_atencao,
                "normal":      len(normal),
                "sem_estagio": len(sem_estagio),
                "pct_ok":      pct_ok,
            },
        }

        # Persiste para histórico (origem manual = gerado pelo closer na hora)
        try:
            report_id = self._db.salvar_relatorio_pulse(relatorio_pulse, origem="manual")
            relatorio_pulse["id"] = report_id
        except Exception as exc:
            _logger.warning("salvar_relatorio_pulse: %s", exc)

        return relatorio_pulse

    def listar_relatorios_pulse(self) -> list:
        """Retorna lista resumida dos relatórios PULSE para a tela de histórico."""
        try:
            return self._db.listar_relatorios_pulse()
        except Exception as exc:
            _logger.error("listar_relatorios_pulse: %s", exc)
            return []

    def obter_relatorio_pulse_por_id(self, report_id: int) -> dict:
        """Retorna o relatório completo pelo ID."""
        try:
            data = self._db.obter_relatorio_pulse_por_id(int(report_id))
            return data if data else {"status": "erro", "mensagem": "Relatório não encontrado"}
        except Exception as exc:
            _logger.error("obter_relatorio_pulse_por_id: %s", exc)
            return {"status": "erro", "mensagem": str(exc)}

    def deletar_relatorio_pulse(self, report_id: int) -> dict:
        """Deleta relatório manual do DB e apaga o PDF de Downloads se existir."""
        import os
        try:
            pdf_path = self._db.deletar_relatorio_pulse(int(report_id))
            apagado = False
            if pdf_path:
                try:
                    os.remove(pdf_path)
                    apagado = True
                except FileNotFoundError:
                    pass
                except Exception as e:
                    _logger.warning("deletar pdf %s: %s", pdf_path, e)
            return {"status": "ok", "pdf_apagado": apagado}
        except Exception as exc:
            _logger.error("deletar_relatorio_pulse: %s", exc)
            return {"status": "erro", "mensagem": str(exc)}

    def gerar_relatorios_historicos(self) -> dict:
        """
        Semeia relatórios históricos desta semana no DB (Seg–Qua + hoje 7h).
        Usa dados atuais do ClickUp com datas passadas.
        Chame apenas uma vez para popular o histórico.
        """
        from src.constants import ESTAGIOS_ATIVOS, URGENCIA_ESTAGIO, HORAS_GARGALO, HORAS_ZOMBIE

        agora   = datetime.now(timezone.utc)
        tarefas = self._db.leads_qualificacao() + self._db.leads_followup()

        def _fmt_tempo(h: float) -> str:
            return f"{int(h // 24)}d {int(h % 24)}h" if h >= 48 else f"{round(h, 1)}h"

        _ACOES = {
            "Coletando dados":      "Completar coleta: nome, gênero, faculdade e curso.",
            "Enviar orçamento":     "URGENTE — Enviar orçamento agora.",
            "Orçamento enviado":    "Follow-up: confirmar recebimento do orçamento.",
            "Follow-up":            "Executar follow-up ativo e avançar estágio.",
            "Contrato enviado":     "CRÍTICO — Checar assinatura do contrato.",
            "Contrato assinado":    "Confirmar prazo e forma de pagamento.",
            "Aguardando pagamento": "MONEY ON TABLE — Acionar para confirmação do pagamento.",
            "Pagamento realizado":  "Encaminhar para produção e registrar no ClickUp.",
        }
        _acao_padrao = "Atualizar estágio no ClickUp e realizar contato proativo."

        def _montar_relatorio(tipo: str, data_str: str, horario_str: str) -> dict:
            from collections import Counter as _Ctr
            critico, atencao, normal, sem_estagio = [], [], [], []
            for t in tarefas:
                dt = t.data_atualizacao
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                horas = (agora - dt).total_seconds() / 3600
                estagio = t.estagio_lead
                estagio_ausente = not estagio or estagio not in ESTAGIOS_ATIVOS
                if estagio_ausente:
                    estagio = "Coletando dados"
                    sem_estagio.append({"nome": t.nome, "board_status": t.status,
                                        "tempo": _fmt_tempo(horas), "horas_raw": horas, "link": t.link})
                h_amb, h_verm = URGENCIA_ESTAGIO.get(estagio, (24, 48))
                info = {"nome": t.nome, "estagio": estagio, "tempo": _fmt_tempo(horas),
                        "horas_raw": horas, "link": t.link, "motivo": ""}
                if horas > HORAS_ZOMBIE:
                    info["motivo"] = f"ZOMBIE — {int(horas // 24)} dias parada"; critico.append(info)
                elif horas > HORAS_GARGALO:
                    info["motivo"] = f"GARGALO — {int(horas // 24)} dias parada"; critico.append(info)
                elif horas > h_verm:
                    info["motivo"] = f"LIMITE CRÍTICO — {_fmt_tempo(horas)}"; critico.append(info)
                elif horas > h_amb:
                    info["motivo"] = f"ATENÇÃO — {_fmt_tempo(horas)}"; atencao.append(info)
                else:
                    info["motivo"] = f"OK — {_fmt_tempo(horas)}"; normal.append(info)

            total  = len(tarefas)
            pct_ok = round((len(normal) / total * 100) if total > 0 else 100.0, 1)
            n_c, n_a = len(critico), len(atencao)
            n_norm = len(normal)

            todos_sorted = sorted(
                [(l, "CRÍTICO") for l in critico] +
                [(l, "ATENÇÃO") for l in atencao] +
                [(l, "NORMAL")  for l in normal],
                key=lambda x: x[0].get("horas_raw", 0), reverse=True
            )
            plano_acao = [
                {"passo": i, "lead": l["nome"], "estagio": l.get("estagio", "—"),
                 "tempo": l["tempo"], "prioridade": p,
                 "acao": _ACOES.get(l.get("estagio", ""), _acao_padrao),
                 "motivo": l.get("motivo", "")}
                for i, (l, p) in enumerate(todos_sorted[:12], 1)
            ]
            urgencias = [f"{l['nome']} — {l.get('estagio','?')} — {l.get('motivo','')}" for l in critico[:5]]

            # Funil por estágio
            funil = [{"estagio": k, "total": v}
                     for k, v in sorted(_Ctr(t.estagio_lead or "Sem estágio" for t in tarefas).items(),
                                        key=lambda x: -x[1])]

            # Metas do dia
            metas_dia: list[str] = []
            if n_c > 0:
                metas_dia.append(f"Atender {n_c} lead(s) crítica(s) até as 10h — mais antiga primeiro")
            if sem_estagio:
                metas_dia.append(f"Registrar estágio de {len(sem_estagio)} lead(s) sem preenchimento no ClickUp")
            metas_dia.append("Encerrar todos atendimentos concluídos com fluxo Encerramento no BotConversa")
            metas_dia.append("Verificar conversas abertas — nenhuma lead sem resposta ao final do dia")

            # Blocos de tempo
            blocos_tempo = [
                {"bloco": "08:00 – 09:30", "foco": "LEADS CRÍTICAS",
                 "descricao": f"Atender as {n_c} lead(s) crítica(s) em ordem hierárquica." if n_c > 0
                              else "Nenhuma lead crítica — adiantar leads em atenção."},
                {"bloco": "09:30 – 09:45", "foco": "INTERVALO",
                 "descricao": "Intervalo. Registre pendências no ClickUp antes de continuar."},
                {"bloco": "09:45 – 11:30", "foco": "ATENÇÃO E LEADS NORMAIS",
                 "descricao": f"Atender {n_a} lead(s) em atenção e {n_norm} dentro do prazo."},
                {"bloco": "11:30 – 12:00", "foco": "PIPELINE / CLICKUP",
                 "descricao": "Atualizar estágios e custom fields de todas as leads atendidas hoje."},
                {"bloco": "13:00 – 14:30", "foco": "BOTCONVERSA",
                 "descricao": "Verificar conversas abertas. Encerrar atendimentos concluídos."},
                {"bloco": "14:30 – 15:00", "foco": "ORGANIZAÇÃO WHATSAPP",
                 "descricao": "Etiquetar leads perdidas como Perdida e arquivar."},
            ]

            if tipo == "BATTLE PLAN":
                intro = (f"Battle Plan de {data_str}. "
                         f"Pipeline com {total} lead(s) ativa(s): "
                         f"{n_c} crítica(s) exigindo ação imediata, "
                         f"{n_a} em atenção e {n_norm} dentro do prazo. "
                         f"Execute o plano na ordem abaixo.")
                partes = []
                if n_c: partes.append(f"{n_c} crítica(s)")
                if sem_estagio: partes.append(f"{len(sem_estagio)} sem estágio")
                conclusao = (f"Pipeline: {total} leads ativas. "
                             + (f"Pendências: {', '.join(partes)}. " if partes else "Sem pendências críticas. ")
                             + "Execute o plano na ordem acima.")
                checklist, analise, dicas = [], {"feito": 0, "pendente": n_c, "total_ativo": total,
                                                  "taxa_atualizacao": 0.0, "avaliacao": "—"}, []
            else:
                intro = (f"Relatório de Fechamento de {data_str}. "
                         f"Confira abaixo o resumo do que foi realizado, "
                         f"o que ficou pendente e as orientações para amanhã.")
                checklist = (
                    [{"item": f"[CRÍTICO] {l['nome']} — {l.get('estagio','?')}",
                      "status": "pendente", "detalhe": l.get("motivo", "")} for l in critico] +
                    [{"item": f"[ATENÇÃO] {l['nome']} — {l.get('estagio','?')}",
                      "status": "pendente", "detalhe": l.get("motivo", "")} for l in atencao[:5]]
                )
                analise = {"feito": 0, "pendente": n_c, "total_ativo": total,
                           "taxa_atualizacao": 0.0, "avaliacao": "Sem dados de fechamento"}
                dicas = (
                    ([f"Amanhã: priorize as {n_c} lead(s) crítica(s) antes de qualquer atividade."] if n_c else []) +
                    ([f"Atualize estágio de {len(sem_estagio)} lead(s) antes das 8h."] if sem_estagio else []) +
                    ["Pipeline atualizado antes da reunião de sexta é obrigatório para o FSS Score.",
                     "Leads em 'Contrato enviado' ou 'Aguardando pagamento' não podem ficar mais de 7h sem contato."]
                )
                conclusao = (f"{total} leads ativas no pipeline. "
                             + (f"{n_c} crítica(s) para amanhã." if n_c > 0
                                else "Pipeline sem críticas para amanhã."))

            return {
                "status": "ok", "tipo": tipo, "horario": horario_str, "data": data_str,
                "intro": intro, "plano_acao": plano_acao, "urgencias": urgencias,
                "checklist": checklist, "analise": analise, "dicas": dicas, "conclusao": conclusao,
                "metas_dia": metas_dia, "blocos_tempo": blocos_tempo, "funil": funil,
                "followups_detalhe": [], "followups_hoje": [], "atualizadas_hoje": [],
                "critico": critico, "atencao": atencao, "normal": normal, "sem_estagio": sem_estagio,
                "stats": {"total": total, "critico": n_c, "atencao": n_a,
                          "normal": n_norm, "sem_estagio": len(sem_estagio), "pct_ok": pct_ok},
            }

        # Limpa duplicatas antes de reinserir (botão pode ter sido clicado várias vezes)
        try:
            removidos = self._db.limpar_duplicatas_pulse()
            if removidos:
                _logger.info("gerar_relatorios_historicos: %d duplicata(s) removida(s)", removidos)
        except Exception as exc:
            _logger.warning("limpar_duplicatas_pulse: %s", exc)

        slots = [
            ("21/04/2026", "07:00", "BATTLE PLAN", "2026-04-21T07:00:00"),
            ("21/04/2026", "19:00", "FECHAMENTO",  "2026-04-21T19:00:00"),
            ("22/04/2026", "07:00", "BATTLE PLAN", "2026-04-22T07:00:00"),
            ("22/04/2026", "19:00", "FECHAMENTO",  "2026-04-22T19:00:00"),
            ("23/04/2026", "07:00", "BATTLE PLAN", "2026-04-23T07:00:00"),
            ("23/04/2026", "19:00", "FECHAMENTO",  "2026-04-23T19:00:00"),
            ("24/04/2026", "07:00", "BATTLE PLAN", "2026-04-24T07:00:00"),
        ]
        criados = 0
        for data_str, horario_str, tipo, criado_em in slots:
            try:
                rel = _montar_relatorio(tipo, data_str, horario_str)
                # upsert=True: deleta o existente para (data, horario) e reinicia limpo
                self._db.salvar_relatorio_pulse(rel, criado_em_override=criado_em, upsert=True)
                criados += 1
            except Exception as exc:
                _logger.warning("gerar_relatorio_historico %s %s: %s", data_str, tipo, exc)

        return {"status": "ok", "criados": criados}

    def atualizar_todos_relatorios(self) -> dict:
        """Regenera TODOS os relatórios existentes no DB com os dados atuais do ClickUp."""
        from src.constants import ESTAGIOS_ATIVOS, URGENCIA_ESTAGIO, HORAS_GARGALO, HORAS_ZOMBIE
        try:
            existentes = self._db.listar_relatorios_pulse()
        except Exception as exc:
            return {"status": "erro", "mensagem": str(exc)}

        if not existentes:
            return {"status": "ok", "atualizados": 0}

        agora   = datetime.now(timezone.utc)
        tarefas = self._db.leads_qualificacao() + self._db.leads_followup()

        def _fmt_tempo(h: float) -> str:
            return f"{int(h // 24)}d {int(h % 24)}h" if h >= 48 else f"{round(h, 1)}h"

        atualizados = 0
        for item in existentes:
            try:
                tipo      = item.get("tipo", "BATTLE PLAN")
                data_str  = item.get("data", datetime.now().strftime("%d/%m/%Y"))
                hora_str  = item.get("horario", "07:00")
                orig      = item.get("origem", "auto")
                criado_em = item.get("criado_em")

                from collections import Counter as _Ctr
                critico, atencao, normal, sem_estagio = [], [], [], []
                for t in tarefas:
                    dt = t.data_atualizacao
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    horas   = (agora - dt).total_seconds() / 3600
                    estagio = t.estagio_lead
                    if not estagio or estagio not in ESTAGIOS_ATIVOS:
                        estagio = "Coletando dados"
                        sem_estagio.append({"nome": t.nome, "board_status": t.status,
                                            "tempo": _fmt_tempo(horas), "horas_raw": horas})
                    h_amb, h_verm = URGENCIA_ESTAGIO.get(estagio, (24, 48))
                    info = {"nome": t.nome, "estagio": estagio, "tempo": _fmt_tempo(horas),
                            "horas_raw": horas, "link": t.link, "motivo": ""}
                    if horas > HORAS_ZOMBIE:
                        info["motivo"] = f"ZOMBIE — {int(horas//24)}d"; critico.append(info)
                    elif horas > HORAS_GARGALO:
                        info["motivo"] = f"GARGALO — {int(horas//24)}d"; critico.append(info)
                    elif horas > h_verm:
                        info["motivo"] = f"CRÍTICO — {_fmt_tempo(horas)}"; critico.append(info)
                    elif horas > h_amb:
                        info["motivo"] = f"ATENÇÃO — {_fmt_tempo(horas)}"; atencao.append(info)
                    else:
                        info["motivo"] = f"OK — {_fmt_tempo(horas)}"; normal.append(info)

                total  = len(tarefas)
                n_c, n_a = len(critico), len(atencao)
                pct_ok = round((len(normal)/total*100) if total > 0 else 100.0, 1)
                funil  = [{"estagio": k, "total": v}
                          for k, v in sorted(_Ctr(t.estagio_lead or "Sem estágio"
                                                   for t in tarefas).items(), key=lambda x: -x[1])]

                is_battle = "BATTLE" in tipo
                if is_battle:
                    intro = (f"Battle Plan de {data_str}. Pipeline: {total} leads — "
                             f"{n_c} crítica(s), {n_a} em atenção.")
                    conclusao = f"Pipeline: {total} leads. {n_c} crítica(s) para o dia."
                    checklist, analise, dicas = [], {"feito":0,"pendente":n_c,"total_ativo":total,
                                                      "taxa_atualizacao":0.0,"avaliacao":"—"}, []
                else:
                    intro = (f"Fechamento de {data_str}. Pipeline: {total} leads. "
                             f"{n_c} crítica(s) identificadas.")
                    checklist = [{"item": f"[CRÍTICO] {l['nome']} — {l.get('estagio','?')}",
                                  "status": "pendente", "detalhe": l.get("motivo","")} for l in critico]
                    analise = {"feito":0,"pendente":n_c,"total_ativo":total,
                               "taxa_atualizacao":0.0,"avaliacao":"—"}
                    dicas = ([f"Amanhã: {n_c} crítica(s) prioritárias."] if n_c else []) + \
                            ["Pipeline atualizado antes da sexta é obrigatório para o FSS."]
                    conclusao = f"{total} leads ativas. {n_c} crítica(s) para amanhã."

                todos_sorted = sorted(
                    [(l,"CRÍTICO") for l in critico]+[(l,"ATENÇÃO") for l in atencao]+
                    [(l,"NORMAL") for l in normal],
                    key=lambda x: x[0].get("horas_raw",0), reverse=True)
                _ACOES_U = {
                    "Coletando dados":"Completar coleta: nome, gênero, faculdade, curso.",
                    "Enviar orçamento":"URGENTE — Enviar orçamento agora.",
                    "Orçamento enviado":"Follow-up: confirmar recebimento.",
                    "Follow-up":"Executar follow-up e avançar estágio.",
                    "Contrato enviado":"CRÍTICO — Checar assinatura do contrato.",
                    "Aguardando pagamento":"MONEY ON TABLE — Confirmar pagamento.",
                }
                plano = [{"passo":i,"lead":l["nome"],"estagio":l.get("estagio","—"),
                          "tempo":l["tempo"],"prioridade":p,
                          "acao":_ACOES_U.get(l.get("estagio",""),"Atualizar ClickUp."),
                          "motivo":l.get("motivo","")}
                         for i,(l,p) in enumerate(todos_sorted[:12],1)]

                rel = {
                    "status":"ok","tipo":tipo,"horario":hora_str,"data":data_str,
                    "intro":intro,"plano_acao":plano,
                    "urgencias":[f"{l['nome']} — {l.get('motivo','')}" for l in critico[:5]],
                    "checklist":checklist,"analise":analise,"dicas":dicas,"conclusao":conclusao,
                    "metas_dia":([f"Atender {n_c} crítica(s) até 10h"] if n_c else []) +
                                ["Verificar BotConversa — nenhuma lead sem resposta"],
                    "blocos_tempo":[
                        {"bloco":"08:00–09:30","foco":"LEADS CRÍTICAS",
                         "descricao":f"{n_c} crítica(s) em ordem hierárquica." if n_c else "Sem críticas — adiantar atenção."},
                        {"bloco":"09:45–11:30","foco":"ATENÇÃO / FOLLOW-UPS",
                         "descricao":f"{n_a} lead(s) em atenção."},
                        {"bloco":"11:30–12:00","foco":"CLICKUP","descricao":"Atualizar estágios e custom fields."},
                    ],
                    "funil":funil,"followups_detalhe":[],"followups_hoje":[],"atualizadas_hoje":[],
                    "critico":critico,"atencao":atencao,"normal":normal,"sem_estagio":sem_estagio,
                    "stats":{"total":total,"critico":n_c,"atencao":n_a,
                             "normal":len(normal),"sem_estagio":len(sem_estagio),"pct_ok":pct_ok},
                }
                self._db.salvar_relatorio_pulse(rel, criado_em_override=criado_em,
                                                upsert=True, origem=orig)
                atualizados += 1
            except Exception as exc:
                _logger.warning("atualizar_todos_relatorios id=%s: %s", item.get("id"), exc)

        return {"status": "ok", "atualizados": atualizados}

    def gerar_pdf_pulse(self, dados_json: str, vendor_nome: str = "", vendor_cargo: str = "") -> dict:
        """Gera PDF profissional do relatório PULSE via PyMuPDF. Salva em Downloads e abre."""
        import json as _json
        import fitz
        import os
        from pathlib import Path

        try:
            d = _json.loads(dados_json)
            if d.get("status") != "ok":
                return {"status": "erro", "mensagem": "Dados do relatório inválidos"}

            tipo      = d.get("tipo", "PULSE")
            data_str  = d.get("data", "—")
            hora_str  = d.get("horario", "—")
            is_battle = "BATTLE" in tipo
            nome_v    = (vendor_nome or "VENDEDOR").strip()
            cargo_v   = (vendor_cargo or "").strip()

            # ── Documento A4 ───────────────────────────────────────
            import re as _re
            doc = fitz.open()
            W, H    = 595.28, 841.89
            ML, MR, MB    = 46, 46, 45
            MT_P1   = 148.0   # início do conteúdo na pág. 1 (após cabeçalho+stats)
            MT_CONT = 32.0    # início do conteúdo nas páginas de continuação
            y = [MT_P1]
            doc.new_page(width=W, height=H)   # página 0

            # Fontes: fontfile= garante Unicode/PT-BR completo
            _FDIR      = Path("C:/Windows/Fonts")
            _USE_ARIAL = (_FDIR / "arial.ttf").exists()
            _FREG      = str(_FDIR / "arial.ttf")
            _FBOLD     = str(_FDIR / "arialbd.ttf")

            def _san(s: str) -> str:
                """Remove emojis e caracteres fora do BMP (U+0000-FFFF)."""
                return _re.sub(r'[^\u0000-\uFFFF]', '', str(s))

            # Paleta Grayscale — sem cores
            C_BAND  = (0.08, 0.08, 0.08)
            C_MID   = (0.28, 0.28, 0.28)
            C_RULE  = (0.55, 0.55, 0.55)
            C_WHITE = (1.0,  1.0,  1.0 )
            C_BODY  = (0.10, 0.10, 0.10)
            C_MUTED = (0.42, 0.42, 0.42)

            # Sempre buscar página fresca — refs armazenadas ficam stale no PyMuPDF 1.24+
            def pg():     return doc[doc.page_count - 1]
            def _avail(): return H - MB - y[0]

            turno_label = "BATTLE PLAN — INÍCIO DO DIA" if is_battle else "FECHAMENTO — FIM DO DIA"

            def _np():
                doc.new_page(width=W, height=H)
                y[0] = MT_CONT
                _p = doc[doc.page_count - 1]
                _p.draw_rect(fitz.Rect(0, 0, W, 22), color=C_BAND, fill=C_BAND)
                _kw = {"fontfile": _FREG} if _USE_ARIAL else {"fontname": "helv"}
                _p.insert_textbox(
                    fitz.Rect(ML, 5, W - MR, 20),
                    f"NEXUS CLOSER  |  {turno_label}  |  {nome_v}  |  {data_str}",
                    fontsize=6, color=C_MUTED, align=1, **_kw)

            def _t(txt, size=9.0, bold=False, color=None, align=0, indent=0.0, gap=4.0):
                if color is None: color = C_BODY
                txt = _san(txt)
                if not txt.strip():
                    y[0] += gap; return
                kw = {"fontfile": _FBOLD if bold else _FREG} if _USE_ARIAL \
                     else {"fontname": "hebo" if bold else "helv"}
                av = _avail()
                if av < size * 2: _np(); av = _avail()
                rect = fitz.Rect(ML + indent, y[0], W - MR, y[0] + av)
                rc = pg().insert_textbox(rect, txt, fontsize=size, color=color, align=align, **kw)
                if rc < 0:
                    _np(); av = _avail()
                    rect = fitz.Rect(ML + indent, y[0], W - MR, y[0] + av)
                    rc = pg().insert_textbox(rect, txt, fontsize=size, color=color, align=align, **kw)
                used = max(av - rc, size * 1.35) if rc >= 0 else av
                y[0] += used + gap

            def _l(thick=0.4, color=None, before=3.0, after=4.0):
                if color is None: color = C_RULE
                y[0] += before
                pg().draw_line(fitz.Point(ML, y[0]), fitz.Point(W - MR, y[0]),
                               color=color, width=thick)
                y[0] += after

            def _sec(title):
                """Cabeçalho de seção — banda escura estilo terminal ciberpunk."""
                if _avail() < 32: _np()
                y[0] += 10
                bh = 17.0
                bx0, bx1 = ML - 4, W - MR + 4
                # Banda escura preenchida
                pg().draw_rect(fitz.Rect(bx0, y[0], bx1, y[0] + bh),
                               color=C_BAND, fill=C_BAND)
                # Marcas de canto (L) nos 4 cantos da banda
                ck = 8
                pg().draw_line(fitz.Point(bx0,      y[0]),
                               fitz.Point(bx0 + ck, y[0]),        color=C_WHITE, width=1.2)
                pg().draw_line(fitz.Point(bx0,      y[0]),
                               fitz.Point(bx0,      y[0] + ck),   color=C_WHITE, width=1.2)
                pg().draw_line(fitz.Point(bx1,      y[0]),
                               fitz.Point(bx1 - ck, y[0]),        color=C_WHITE, width=1.2)
                pg().draw_line(fitz.Point(bx1,      y[0]),
                               fitz.Point(bx1,      y[0] + ck),   color=C_WHITE, width=1.2)
                pg().draw_line(fitz.Point(bx0,      y[0] + bh),
                               fitz.Point(bx0 + ck, y[0] + bh),  color=C_WHITE, width=1.2)
                pg().draw_line(fitz.Point(bx0,      y[0] + bh),
                               fitz.Point(bx0,      y[0] + bh - ck), color=C_WHITE, width=1.2)
                pg().draw_line(fitz.Point(bx1,      y[0] + bh),
                               fitz.Point(bx1 - ck, y[0] + bh),  color=C_WHITE, width=1.2)
                pg().draw_line(fitz.Point(bx1,      y[0] + bh),
                               fitz.Point(bx1,      y[0] + bh - ck), color=C_WHITE, width=1.2)
                # Texto branco em negrito
                kw = {"fontfile": _FBOLD} if _USE_ARIAL else {"fontname": "hebo"}
                pg().insert_textbox(
                    fitz.Rect(bx0 + 12, y[0] + 3, bx1 - 12, y[0] + bh),
                    f"[*] {title}", fontsize=8.5, color=C_WHITE, align=0, **kw)
                y[0] += bh + 7

            # ── CABEÇALHO — banda escura full-width na página 1 ────
            _HH = 110.0   # altura da banda do cabeçalho principal
            doc[0].draw_rect(fitz.Rect(0, 0, W, _HH), color=C_BAND, fill=C_BAND)
            doc[0].draw_line(fitz.Point(0, _HH), fitz.Point(W, _HH), color=C_MID, width=2.5)
            # Marcas de canto nos 4 cantos do cabeçalho principal
            for _cx, _sd in [(ML, 1), (W - MR, -1)]:
                doc[0].draw_line(fitz.Point(_cx, 10),
                                 fitz.Point(_cx + _sd * 18, 10),       color=C_WHITE, width=1.5)
                doc[0].draw_line(fitz.Point(_cx, 10),
                                 fitz.Point(_cx, 26),                   color=C_WHITE, width=1.5)
                doc[0].draw_line(fitz.Point(_cx, _HH - 10),
                                 fitz.Point(_cx + _sd * 18, _HH - 10), color=C_WHITE, width=1.5)
                doc[0].draw_line(fitz.Point(_cx, _HH - 10),
                                 fitz.Point(_cx, _HH - 26),             color=C_WHITE, width=1.5)
            # Textos do cabeçalho (cada doc[0] é referência fresca)
            _kw_b = {"fontfile": _FBOLD} if _USE_ARIAL else {"fontname": "hebo"}
            _kw_r = {"fontfile": _FREG}  if _USE_ARIAL else {"fontname": "helv"}
            doc[0].insert_textbox(fitz.Rect(ML + 22, 12, W - MR - 22, 26),
                "NEXUS CLOSER", fontsize=7, color=C_MID, align=1, **_kw_r)
            doc[0].insert_textbox(fitz.Rect(ML + 22, 28, W - MR - 22, 64),
                turno_label, fontsize=20, color=C_WHITE, align=1, **_kw_b)
            doc[0].insert_textbox(fitz.Rect(ML + 22, 66, W - MR - 22, 80),
                nome_v + ("  ·  " + cargo_v if cargo_v else ""),
                fontsize=9, color=C_MID, align=1, **_kw_r)
            doc[0].insert_textbox(fitz.Rect(ML + 22, 80, W - MR - 22, 96),
                data_str + "  ·  " + hora_str,
                fontsize=9, color=C_MID, align=1, **_kw_r)

            # ── Barra de stats — 5 células logo abaixo do cabeçalho ─
            _sdata = d.get("stats", {})
            _slist = [
                ("TOTAL",   str(_sdata.get("total",   0))),
                ("CRITICO", str(_sdata.get("critico", 0))),
                ("ATENCAO", str(_sdata.get("atencao", 0))),
                ("NORMAL",  str(_sdata.get("normal",  0))),
                ("SAUDE",   f"{_sdata.get('pct_ok', 100)}%"),
            ]
            _cw2 = (W - ML - MR) / len(_slist)
            _sy2 = _HH + 1.0
            _ch2 = 35.0
            for _i2, (_lb2, _vl2) in enumerate(_slist):
                _cx2 = ML + _i2 * _cw2
                doc[0].draw_rect(fitz.Rect(_cx2, _sy2, _cx2 + _cw2, _sy2 + _ch2),
                                 color=C_MID, fill=None, width=0.5)
                doc[0].insert_textbox(
                    fitz.Rect(_cx2 + 3, _sy2 + 3, _cx2 + _cw2 - 3, _sy2 + 14),
                    _lb2, fontsize=6, color=C_MUTED, align=1, **_kw_r)
                doc[0].insert_textbox(
                    fitz.Rect(_cx2 + 3, _sy2 + 14, _cx2 + _cw2 - 3, _sy2 + _ch2 - 2),
                    _vl2, fontsize=13, color=C_BODY, align=1, **_kw_b)

            # ── SITUAÇÃO DO DIA ────────────────────────────────────
            _sec("SITUAÇÃO DO DIA")
            _t(d.get("intro", "—"), size=9, gap=8)

            if is_battle:
                # ══════════════════════════════════════════════════
                # BATTLE PLAN
                # ══════════════════════════════════════════════════

                # ── METAS DO DIA ───────────────────────────────────
                metas = d.get("metas_dia", [])
                if metas:
                    _sec("METAS DO DIA")
                    for i, m in enumerate(metas, 1):
                        _t(f"  {i}.  {m}", size=9, gap=3)

                # ── URGÊNCIAS ──────────────────────────────────────
                urgencias = d.get("urgencias", [])
                if urgencias:
                    _sec("URGÊNCIAS — ATENDER AGORA")
                    _t("Estas leads ultrapassaram o limite crítico de tempo. Contato imediato.",
                       size=8, color=(0.35,0.35,0.35), gap=5)
                    for u in urgencias:
                        linha = str(u) if not isinstance(u, dict) else f"{u.get('nome','?')} — {u.get('motivo','?')}"
                        _t(f"  [!]  {linha}", size=9, bold=True, gap=3)

                # ── BLOCOS DE TEMPO ────────────────────────────────
                blocos = d.get("blocos_tempo", [])
                if blocos:
                    _sec("BLOCOS DE TEMPO — AGENDA DO DIA")
                    _t("Execute cada bloco sem interrupções. Intervalo obrigatório entre blocos.",
                       size=8, color=(0.35,0.35,0.35), gap=5)
                    for b in blocos:
                        foco = b.get("foco", "")
                        bloco = b.get("bloco", "")
                        desc = b.get("descricao", "")
                        _t(f"  {bloco}  |  {foco}", size=9, bold=True, gap=1)
                        _t(f"          {desc}", size=8.5, color=(0.3,0.3,0.3), gap=5)

                # ── PLANO DE AÇÃO HIERÁRQUICO ──────────────────────
                plano = d.get("plano_acao", [])
                if plano:
                    _sec("PLANO DE AÇÃO — MAIS ANTIGA PRIMEIRO")
                    _t("Regra de ouro: responda sempre a mensagem mais antiga primeiro.",
                       size=8, color=(0.35,0.35,0.35), gap=5)
                    pmap = {"CRÍTICO": "[!]", "ATENÇÃO": "[~]", "NORMAL": "[ ]"}
                    for p in plano:
                        sym = pmap.get(p.get("prioridade", ""), "[ ]")
                        _t(f"  {p.get('passo','?')}.  {sym}  {p.get('lead','?')}",
                           size=9, bold=True, gap=1)
                        _t(f"       Estágio: {p.get('estagio','?')}  ·  Parado há: {p.get('tempo','?')}",
                           size=8.5, color=(0.35,0.35,0.35), gap=1)
                        _t(f"       Ação: {p.get('acao','?')}",
                           size=8.5, color=(0.2,0.2,0.2), gap=5)

                # ── FOLLOW-UPS DO DIA ──────────────────────────────
                fups = d.get("followups_detalhe", [])
                if fups:
                    _sec("FOLLOW-UPS DA SEQUÊNCIA 60 DIAS")
                    _t("Execute estes follow-ups antes do meio-dia. Sequência do contrato.",
                       size=8, color=(0.35,0.35,0.35), gap=5)
                    for f in fups:
                        etapa = f.get("etapa") or "—"
                        _t(f"  [ ]  {f.get('nome','?')}  —  {etapa}", size=9, gap=3)

                # ── FUNIL POR ESTÁGIO ──────────────────────────────
                funil = d.get("funil", [])
                if funil:
                    _sec("FUNIL — DISTRIBUIÇÃO POR ESTÁGIO")
                    for fi in funil:
                        est = fi.get("estagio", "—")
                        tot = fi.get("total", 0)
                        bar_n = min(int(tot), 20)
                        bar = "|" * bar_n
                        _t(f"  {est:<28}  {bar}  {tot}", size=8.5, gap=3)

                # ── PASSO A PASSO OPERACIONAL ──────────────────────
                _sec("PASSO A PASSO — ROTINA OPERACIONAL")
                _t("Execute nesta ordem. Não pule etapas.", size=8, color=(0.35,0.35,0.35), gap=5)
                passos_op = [
                    ("1", "Abrir BotConversa", "Verificar aba 'Abertas'. Responder todas as conversas — mais antiga primeiro."),
                    ("2", "Leads críticas e urgências", "Atender as leads listadas em URGÊNCIAS e no PLANO DE AÇÃO acima."),
                    ("3", "Follow-ups da sequência", "Executar os follow-ups do dia listados na seção acima."),
                    ("4", "Atualizar ClickUp", "Atualizar estágio e custom fields de cada lead atendida. Max 2 dias sem atualização."),
                    ("5", "Encerrar atendimentos", "Usar fluxo 'Encerramento' no BotConversa para leads que finalizaram."),
                    ("6", "Etiquetar perdidas", "No WhatsApp: etiquetar leads perdidas como 'Perdida' e arquivar."),
                    ("7", "Pipeline atualizado?", "Conferir se todas as leads atendidas hoje estão com estágio correto no ClickUp."),
                ]
                for num, titulo, desc in passos_op:
                    _t(f"  Passo {num}:  {titulo}", size=9, bold=True, gap=1)
                    _t(f"           {desc}", size=8.5, color=(0.25,0.25,0.25), gap=5)

                # ── DICAS TÁTICAS ──────────────────────────────────
                _sec("DICAS TÁTICAS")
                dicas_battle = [
                    "Se a lead não respondeu em 24h, mude a abordagem — troque o canal (áudio, texto, ligação).",
                    "Pipeline desatualizado = FSS baixo = menos bônus. Atualize sempre antes da reunião de sexta.",
                    "Leads em 'Aguardando pagamento' são prioridade absoluta — money on the table.",
                    "Nunca trate duas leads ao mesmo tempo. Foque em uma, conclua, avance.",
                    "Leads sem estágio definido são invisíveis para o sistema. Preencha no ClickUp agora.",
                ]
                for dica in dicas_battle:
                    _t(f"  -  {dica}", size=8.5, gap=4)

                # ── CHECKLIST DE FECHAMENTO DO DIA ─────────────────
                _sec("CHECKLIST — FECHAR O DIA CERTO")
                for ci in [
                    "Todas as conversas abertas no BotConversa foram respondidas",
                    "Atendimentos concluídos encerrados com fluxo 'Encerramento' no BotConversa",
                    "Todas as leads atendidas com estágio e custom fields atualizados no ClickUp",
                    "Leads perdidas etiquetadas como 'Perdida' e arquivadas no WhatsApp",
                    "Leads sem estágio definido preenchidas no Pipeline",
                ]:
                    _t(f"  [ ]  {ci}", size=8.5, gap=3)

            else:
                # ══════════════════════════════════════════════════
                # FECHAMENTO
                # ══════════════════════════════════════════════════

                # ── BALANÇO DO DIA ─────────────────────────────────
                analise = d.get("analise", {})
                _sec("BALANÇO DO DIA")
                taxa_v = analise.get("taxa_atualizacao", 0)
                aval   = analise.get("avaliacao", "—")
                cor_av = C_BODY if taxa_v >= 80 else C_MID if taxa_v >= 50 else C_MID  # grayscale
                for k, v in [
                    ("Leads atualizadas hoje",         analise.get("feito", 0)),
                    ("Pendências identificadas",        analise.get("pendente", 0)),
                    ("Total de leads ativas",           analise.get("total_ativo", 0)),
                    ("Taxa de atualização do pipeline", f"{taxa_v}%"),
                    ("Avaliação geral do dia",          aval),
                ]:
                    _t(f"  {k}:  {v}", size=9, gap=3)

                # ── CHECKLIST DO DIA ───────────────────────────────
                checklist = d.get("checklist", [])
                if checklist:
                    _sec("CHECKLIST — O QUE FOI FEITO E O QUE FICOU PENDENTE")
                    for c in checklist:
                        sym = "[OK]" if c.get("status") == "ok" else "[--]"
                        _t(f"  {sym}  {c.get('item','?')}", size=9,
                           bold=(c.get("status") != "ok"), gap=1)
                        if c.get("detalhe"):
                            _t(f"         {c['detalhe']}", size=8, color=(0.4,0.4,0.4), gap=3)
                        else:
                            y[0] += 2

                # ── ANÁLISE — ONDE MELHORAR ────────────────────────
                critico_f = d.get("critico", [])
                sem_est_f = d.get("sem_estagio", [])
                pendente_n = analise.get("pendente", 0)
                erros: list[str] = []
                if critico_f:
                    erros.append(
                        f"{len(critico_f)} lead(s) acumularam tempo crítico. "
                        "Priorize as mais antigas no primeiro bloco de amanhã.")
                if sem_est_f:
                    erros.append(
                        f"{len(sem_est_f)} lead(s) sem estágio definido no Pipeline. "
                        "Preencha os campos obrigatórios no ClickUp antes das 8h.")
                if taxa_v < 50:
                    erros.append(
                        f"Taxa de atualização em {taxa_v}% — abaixo do mínimo de 50%. "
                        "Pipeline desatualizado afeta o FSS Score e a visibilidade das leads.")
                if pendente_n > 3:
                    erros.append(
                        f"{pendente_n} leads ficaram sem movimentação hoje. "
                        "Use blocos de 25 min para contatos em sequência — evita dispersão.")
                if not erros:
                    erros.append("Nenhum desvio crítico identificado. Manter a cadência amanhã.")
                _sec("ANÁLISE — ONDE MELHORAR")
                for i, e in enumerate(erros, 1):
                    _t(f"  {i}.  {e}", size=9, gap=5)

                # ── FUNIL ──────────────────────────────────────────
                funil = d.get("funil", [])
                if funil:
                    _sec("FUNIL HOJE — DISTRIBUIÇÃO POR ESTÁGIO")
                    for fi in funil:
                        est = fi.get("estagio", "—")
                        tot = fi.get("total", 0)
                        bar = "|" * min(int(tot), 20)
                        _t(f"  {est:<28}  {bar}  {tot}", size=8.5, gap=3)

                # ── PLANO PARA AMANHÃ ──────────────────────────────
                _sec("PLANO ESTRATÉGICO — AMANHÃ")
                plano_amanha: list[str] = []
                if critico_f:
                    plano_amanha.append(
                        f"Prioridade máxima: {len(critico_f)} lead(s) crítica(s) — atender antes de qualquer outra atividade.")
                if sem_est_f:
                    plano_amanha.append(
                        f"Atualizar estágio e custom fields de {len(sem_est_f)} lead(s) no ClickUp.")
                fups_f = d.get("followups_detalhe", [])
                if fups_f:
                    plano_amanha.append(
                        f"Executar {len(fups_f)} follow-up(s) da sequência 60 dias antes do meio-dia.")
                plano_amanha.append("Verificar e encerrar conversas abertas no BotConversa com fluxo Encerramento.")
                plano_amanha.append("Atualizar Pipeline antes de iniciar novos atendimentos.")
                for i, p in enumerate(plano_amanha, 1):
                    _t(f"  {i}.  {p}", size=9, gap=4)

                # ── DICAS DE ORGANIZAÇÃO ───────────────────────────
                _sec("DICAS PARA O DIA SEGUINTE")
                dicas_fech = [
                    "Leads críticas de hoje viram prioridade absoluta amanhã — não postergue.",
                    "Pipeline atualizado antes da reunião de sexta é obrigatório para o FSS Score.",
                    "Se perdeu a sequência de follow-up hoje, retome amanhã no mesmo ponto — não reinicie.",
                    "Leads em 'Contrato enviado' ou 'Aguardando pagamento' não podem ficar mais de 7h sem contato.",
                    "Cada lead sem estágio preenchido é um ponto a menos no FSS. Preencha todos antes das 8h.",
                ]
                dicas_extra = d.get("dicas", [])
                for dica in (dicas_extra or dicas_fech):
                    _t(f"  -  {dica}", size=8.5, gap=4)

            # ── LEADS CRÍTICAS (ambos os turnos) ──────────────────
            critico_list = d.get("critico", [])
            if critico_list:
                _sec(f"LEADS CRÍTICAS  —  {len(critico_list)} no total")
                _t("Estas leads precisam de ação imediata. Ordenadas da mais urgente para a menos urgente.",
                   size=8, color=(0.35,0.35,0.35), gap=5)
                for l in critico_list:
                    _t(f"  [!]  {l.get('nome','?')}  ·  {l.get('estagio','?')}  ·  {l.get('tempo','?')}",
                       size=9, bold=True, gap=1)
                    if l.get("motivo"):
                        _t(f"       {l['motivo']}", size=8.5, color=(0.3,0.3,0.3), gap=4)
                    else:
                        y[0] += 3

            # ── CONCLUSÃO ──────────────────────────────────────────
            if d.get("conclusao"):
                _sec("RESUMO EXECUTIVO")
                _t(d["conclusao"], size=9, gap=8)

            # ── RODAPÉ EM TODAS AS PÁGINAS ─────────────────────────
            total_pgs = doc.page_count
            _rodape_kw = {"fontfile": _FREG} if _USE_ARIAL else {"fontname": "helv"}
            for i in range(total_pgs):
                pg_r = doc[i]
                pg_r.draw_line(
                    fitz.Point(ML, H - MB + 8), fitz.Point(W - MR, H - MB + 8),
                    color=(0.75,0.75,0.75), width=0.5)
                pg_r.insert_textbox(
                    fitz.Rect(ML, H - MB + 10, W - MR, H - MB + 22),
                    f"Nexus Closer  ·  {nome_v}  ·  {data_str}  ·  Pagina {i+1} de {total_pgs}",
                    fontsize=7, color=(0.55,0.55,0.55), align=1, **_rodape_kw)

            # ── SALVAR E ABRIR ─────────────────────────────────────
            data_fmt = data_str.replace("/", "-")
            hora_fmt = hora_str.replace(":", "h")
            filename = (f"Relatorio - {data_fmt} - {hora_fmt} - "
                        f"{nome_v.upper()} - {cargo_v.upper()}.pdf")
            downloads = Path.home() / "Downloads"
            downloads.mkdir(exist_ok=True)
            output = downloads / filename
            doc.save(str(output))
            doc.close()
            os.startfile(str(output))
            # Registra caminho do PDF no DB para permitir exclusão pelo botão
            report_id = d.get("id")
            if report_id:
                try:
                    self._db.atualizar_pdf_path(int(report_id), str(output))
                except Exception as e:
                    _logger.warning("atualizar_pdf_path: %s", e)
            return {"status": "ok", "path": str(output), "nome": filename}

        except Exception as exc:
            _logger.error("gerar_pdf_pulse: %s", exc, exc_info=True)
            return {"status": "erro", "mensagem": str(exc)}

    # ── MASTER — Visão consolidada ──────────────────────────────

    def obter_relatorio_master(self) -> dict:
        """
        Retorna dados consolidados para o overlay MASTER:
        FSS breakdown por dimensão, financeiro, saúde do pipeline.
        """
        from src.constants import ESTAGIOS_ATIVOS, HORAS_GARGALO, HORAS_ZOMBIE

        agora = datetime.now(timezone.utc)

        def _horas(t: Tarefa) -> float:
            dt = t.data_atualizacao
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (agora - dt).total_seconds() / 3600

        # ── Leads do closer atual ──────────────────────────────
        usuario_id = ""
        clickup = None
        try:
            clickup = ClickUpService()
            usuario = clickup.fetch_current_user()
            usuario_id = str(usuario.get("id", ""))
        except Exception as exc:
            _logger.warning("obter_relatorio_master — fetch_current_user: %s", exc)

        todas = self._db.leads_qualificacao() + self._db.leads_followup()

        # Se DB vazio, tenta sync agora
        if not todas and clickup:
            try:
                tarefas = clickup.buscar_pipeline(desde_ms=0)
                if tarefas:
                    self._db.salvar_tarefas(tarefas)
                    self._db.registrar_sincronizacao(clickup.lista_pipeline_id, tarefas)
                todas = self._db.leads_qualificacao() + self._db.leads_followup()
            except Exception as exc:
                _logger.warning("obter_relatorio_master — sync fallback: %s", exc)

        # Filtra por closer; se usuario_id vazio ou nenhuma match, usa todas
        if usuario_id:
            leads_closer = [t for t in todas if str(t.closer_id) == usuario_id]
            if not leads_closer:
                leads_closer = todas  # fallback: ClickUp pode não ter assignee
        else:
            leads_closer = todas
        total_closer = len(leads_closer)

        # ── FSS — 4 dimensões (escala 0–100% por dimensão) ─────
        _estagios_followup = {
            "Orçamento enviado", "Follow-up", "Contrato enviado", "Aguardando pagamento"
        }
        leads_sem_crm:    list[str] = []
        leads_sem_fu:     list[str] = []
        leads_sem_atend:  list[str] = []
        leads_sem_det:    list[str] = []

        if total_closer > 0:
            for t in leads_closer:
                nome = t.nome or "—"
                if not (t.plano and t.estagio_lead):
                    leads_sem_crm.append(nome)
                if not (t.etapa_followup or t.estagio_lead in _estagios_followup):
                    leads_sem_fu.append(nome)
                if _horas(t) >= 48:
                    leads_sem_atend.append(nome)
                if not (t.plano and t.whatsapp):
                    leads_sem_det.append(nome)

            crm_ok   = total_closer - len(leads_sem_crm)
            fu_ok    = total_closer - len(leads_sem_fu)
            atend_ok = total_closer - len(leads_sem_atend)
            det_ok   = total_closer - len(leads_sem_det)

            pct_crm   = round(crm_ok   / total_closer * 100)
            pct_fu    = round(fu_ok    / total_closer * 100)
            pct_atend = round(atend_ok / total_closer * 100)
            pct_det   = round(det_ok   / total_closer * 100)

            fss_total = round(((pct_crm + pct_fu + pct_atend + pct_det) / 4) / 100 * 16)
            fss_total = max(1, min(16, fss_total))
        else:
            pct_crm = pct_fu = pct_atend = pct_det = 0
            fss_total = 0

        # ── Pipeline por estágio ───────────────────────────────
        por_estagio: dict[str, int] = {}
        gargalos: list[str] = []
        zombies:  list[str] = []
        for t in todas:
            if t.estagio_lead:
                por_estagio[t.estagio_lead] = por_estagio.get(t.estagio_lead, 0) + 1
            if t.estagio_lead in ESTAGIOS_ATIVOS:
                h = _horas(t)
                if h > HORAS_ZOMBIE:
                    zombies.append(t.nome)
                elif h > HORAS_GARGALO:
                    gargalos.append(t.nome)

        # ── Financeiro (separado por estágio) ──────────────────
        # valor_orcamento: válido a partir de "Orçamento enviado"
        # faturamento_bruto: válido a partir de "Contrato enviado"
        _estagios_orcamento = {"Orçamento enviado", "Follow-up"}
        _estagios_contrato  = {"Contrato enviado", "Aguardando pagamento", "Pagamento realizado"}

        pipeline_potencial = sum(
            t.valor_orcamento for t in todas
            if t.estagio_lead in _estagios_orcamento and t.valor_orcamento > 0
        )
        fat_bruto = sum(
            t.faturamento_bruto for t in todas
            if t.estagio_lead in _estagios_contrato and t.faturamento_bruto > 0
        )
        fat_liq   = sum(
            t.faturamento_liquido for t in todas
            if t.estagio_lead in _estagios_contrato and t.faturamento_liquido > 0
        )
        comissao  = sum(
            t.comissao for t in todas
            if t.estagio_lead in _estagios_contrato and t.comissao > 0
        )

        planos: dict[str, dict] = {}
        for t in todas:
            if t.plano and t.estagio_lead in _estagios_contrato:
                p = planos.setdefault(t.plano, {"count": 0, "fat": 0.0})
                p["count"] += 1
                p["fat"]   += t.faturamento_bruto

        self._log(f"[MASTER] FSS={fss_total}/16 | leads_closer={total_closer} | bruto=R${fat_bruto:,.0f}")

        return {
            "status": "ok",
            "fss": {
                "usuario_id":   usuario_id,
                "total":        fss_total,
                "crm":          pct_crm,
                "followup":     pct_fu,
                "atendimento":  pct_atend,
                "detalhes":     pct_det,
                "leads_closer": total_closer,
                "leads_sem_crm":   leads_sem_crm,
                "leads_sem_fu":    leads_sem_fu,
                "leads_sem_atend": leads_sem_atend,
                "leads_sem_det":   leads_sem_det,
            },
            "financeiro": {
                "pipeline_potencial": pipeline_potencial,  # orçamentos em aberto
                "bruto":    fat_bruto,                     # contratos fechados
                "liquido":  fat_liq,
                "comissao": comissao,
                "por_plano": [
                    {"plano": k, "count": v["count"], "fat": v["fat"]}
                    for k, v in sorted(planos.items(), key=lambda x: -x[1]["fat"])
                ],
            },
            "pipeline": {
                "por_estagio": [
                    {"estagio": k, "count": v}
                    for k, v in sorted(por_estagio.items(), key=lambda x: -x[1])
                ],
                "gargalos":     gargalos[:6],
                "zombies":      zombies[:6],
                "total_ativas": len(todas),
            },
        }

    # ── Orçamento ───────────────────────────────────────────────────

    def calcular_proposta(
        self,
        nome_lead: str,
        tipo: str,
        nivel: str,
        plano: str,
        paginas: int,
        prazo: str,
        desconto: float = 0.0,
    ) -> dict:
        """Calcula orçamento completo e retorna texto formatado para copy-paste."""
        from src.modules.orcamento.calculator import (
            TipoDemanda, Nivel, Plano, Prazo, calcular_orcamento,
        )
        from src.modules.orcamento.planos import obter_descritivo

        self._log(f"[SYS] CALCULANDO — TIPO={tipo} PLANO={plano} PRAZO={prazo}")

        # Trava de prazo antes de qualquer chamada à API
        try:
            resultado = calcular_orcamento(
                tipo=TipoDemanda(tipo),
                nivel=Nivel(nivel),
                plano=Plano(plano),
                paginas=int(paginas),
                prazo=Prazo(prazo),
                desconto=float(desconto),
            )
        except ValueError as exc:
            return {"status": "erro_prazo", "mensagem": str(exc)}
        except Exception as exc:
            _logger.error("calcular_orcamento: %s", exc)
            return {"status": "erro", "mensagem": str(exc)}

        # Busca nome real no ClickUp (opcional — falha graciosamente)
        lead_nome = nome_lead or "—"
        try:
            clickup = ClickUpService()
            briefing = clickup.buscar_lead_briefing(nome_lead) if nome_lead else None
            if briefing:
                lead_nome = briefing["nome"]
        except Exception as exc:
            self._log(f"[WARN] ClickUp indisponível — usando nome local: {exc}")

        descritivo = obter_descritivo(tipo, plano)
        texto = _formatar_proposta(
            lead_nome, tipo, nivel, plano, int(paginas), prazo, resultado, descritivo
        )

        self._log(f"[OK] PROPOSTA — R$ {resultado.total_avista:,.2f} | {lead_nome}")
        return {
            "status":            "ok",
            "lead":              lead_nome,
            "total_avista":      resultado.total_avista,
            "total_parcelado":   resultado.total_parcelado,
            "total_com_desconto": resultado.total_com_desconto,
            "aviso_desconto":    resultado.aviso_desconto,
            "texto_proposta":    texto,
        }


# ── BotConversa Worker ─────────────────────────────────────────────

def _iniciar_bot_worker(api: Api) -> None:
    async def _run() -> None:
        db = DatabaseManager()
        worker = BotConversaWorker(log_callback=api._log, db=db)
        worker.start()
        while True:
            await asyncio.sleep(60)

    asyncio.run(_run())


# ── PULSE Scheduler (07h e 19h) ───────────────────────────────────

def _iniciar_pulse_scheduler(api: Api) -> None:
    """
    Agenda relatórios PULSE de segunda a sábado:
    - 07:00h → BATTLE PLAN (agenda do dia)
    - 19:00h → FECHAMENTO (resumo do que foi feito e o que falta)
    Domingo é dia de descanso — sem relatórios.
    """
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger

    # Segunda (0) a Sábado (5) — domingo (6) excluído
    SEG_A_SAB = "mon-sat"

    scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")

    # Auditoria + relatório PULSE às 07h
    scheduler.add_job(
        lambda: api.obter_relatorio_pulse(),
        CronTrigger(hour=7, minute=0, day_of_week=SEG_A_SAB),
        id="pulse_07h",
        name="PULSE — Battle Plan 07h",
    )
    # Auditoria + relatório PULSE às 19h
    scheduler.add_job(
        lambda: api.obter_relatorio_pulse(),
        CronTrigger(hour=19, minute=0, day_of_week=SEG_A_SAB),
        id="pulse_19h",
        name="PULSE — Fechamento 19h",
    )

    # ── Verificação de novas leads a cada 5 min ──────────────────
    # Leads recém-criadas no ClickUp (< 10 min desde data_criacao)
    # indicam que o fluxo de pré-atendimento acabou de finalizar.
    _notificadas: set[str] = set()  # IDs já notificados nesta sessão

    def _verificar_novas_leads() -> None:
        try:
            agora_utc = datetime.now(timezone.utc)
            # Sync rápido antes de checar
            try:
                cu  = ClickUpService()
                ms  = api._db.ultima_sincronizacao_ms(cu.lista_pipeline_id)
                dl  = cu.buscar_pipeline(desde_ms=ms)
                if dl:
                    api._db.salvar_tarefas(dl)
                    api._db.registrar_sincronizacao(cu.lista_pipeline_id, dl)
            except Exception:
                pass

            tarefas = api._db.leads_qualificacao() + api._db.leads_followup()
            for t in tarefas:
                if t.clickup_id in _notificadas:
                    continue
                dc = t.data_criacao
                if dc.tzinfo is None:
                    dc = dc.replace(tzinfo=timezone.utc)
                minutos = (agora_utc - dc).total_seconds() / 60
                # Lead criada nos últimos 10 min — pré-atendimento acabou de finalizar
                if minutos <= 10:
                    _notificadas.add(t.clickup_id)
                    nome = t.nome or "Nova lead"
                    msg  = (f"Pré-atendimento finalizado. Responda agora: {nome}. "
                            f"Regra: mais antiga primeiro.")
                    api._js(f"mostrarAviso('NOVA LEAD — RESPONDER AGORA', {json.dumps(msg)})")
                    _logger.info("Nova lead detectada: %s (%s)", nome, t.clickup_id)
        except Exception as exc:
            _logger.warning("_verificar_novas_leads: %s", exc)

    scheduler.add_job(
        _verificar_novas_leads,
        "interval",
        minutes=5,
        id="check_novas_leads",
        name="Verificar novas leads (pós pré-atendimento)",
    )

    scheduler.start()
    _logger.info("PULSE scheduler ativo — 07:00h e 19:00h (seg-sáb) — Domingo sem relatório")


# ── Entry point ────────────────────────────────────────────────────

def main() -> None:
    # Define AppUserModelID para o Windows agrupar a janela corretamente na barra de tarefas
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NexusCloser.Terminal.V8")
    except Exception:
        pass

    api = Api()  # DatabaseManager() criado aqui — schema garantido

    _base  = Path(__file__).resolve().parent
    _index = (_base / "web" / "index.html").as_uri()
    _icon_path = _base / "assets" / "nexus_closer.ico"
    _icon  = str(_icon_path) if _icon_path.exists() else None

    window = webview.create_window(
        title="NEXUS CLOSER // TERMINAL",
        url=_index,
        js_api=api,
        width=1280,
        height=820,
        min_size=(900, 600),
        background_color="#000000",
        text_select=True,
    )
    api._bind(window)

    # Garante que o processo Python termina quando a janela fechar
    import os as _os
    window.events.closed += lambda: _os._exit(0)

    threading.Thread(
        target=_iniciar_bot_worker, args=(api,), daemon=True
    ).start()

    threading.Thread(
        target=_iniciar_pulse_scheduler, args=(api,), daemon=True
    ).start()

    webview.start(debug=False, icon=_icon)


if __name__ == "__main__":
    main()
