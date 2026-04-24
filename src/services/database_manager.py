"""
Nexus Closer — Camada de Persistência Local (SQLite).

Thread safety: conexões thread-local (threading.local) + WAL mode.
Cada thread (main + sync) abre sua própria conexão e a fecha ao término.
"""

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from src.models import Tarefa

logger  = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "nexus_storage.db"

_local = threading.local()

# Filtro de status finais — usa LIKE para capturar variações com emoji,
# barra, sufixos e acentos (ex: 'fechado 🦈', 'perdida/arquivada').
# Cada tupla = (prefixo_like, substring_like) — a query usa ambos.
#
# Padrão real observado no ClickUp desta conta:
#   'perdida/arquivada' (1212), 'fechado 🦈' (347), 'reembolsado' (1)
#
# LIKE opera em SQLite sem lower() para evitar problemas com acentos/emoji.
_STATUS_FINAIS_LIKE = (
    "perdida%",       # 'perdida/arquivada', 'perdida', 'perdido'
    "%perdida%",      # captura substrings como 'lead perdida'
    "fechado%",       # 'fechado 🦈', 'fechado', 'fechada'
    "fechada%",
    "arquivado%",
    "arquivada%",
    "%arquivada%",
    "cancelado%",
    "cancelada%",
    "encerrado%",
    "encerrada%",
    "reembolsado%",
    "ganho%",
    "won%",
    "lost%",
    "closed%",
    "cancelled%",
    "archived%",
    "contratado%",    # lead que virou contrato — sai do pipeline ativo
    "contratada%",
)

def _filtro_status_final_sql() -> str:
    """
    Retorna fragmento SQL para excluir leads com status final.
    Usa LIKE diretamente no campo status (sem lower()) para não quebrar emojis.
    Uso: WHERE NOT ({_filtro_status_final_sql()})
    """
    partes = [f"status LIKE ?" for _ in _STATUS_FINAIS_LIKE]
    return " OR ".join(partes)


# ------------------------------------------------------------------
# Serialização — datetimes sempre como UTC sem timezone (ISO 8601 simples)
# Necessário: SQLite datetime() não parseia strings com offset "+00:00"
# ------------------------------------------------------------------

def _dt_para_str(dt: datetime) -> str:
    """Converte datetime (tz-aware ou naive) para string UTC sem offset."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(sep="T", timespec="seconds")


def _str_para_dt(s: str) -> datetime:
    """Reconstrói datetime UTC-aware a partir da string armazenada."""
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _tarefa_para_row(t: Tarefa) -> dict:
    return {
        "link":                t.link,
        "nome":                t.nome,
        "status":              t.status,
        "origem":              t.origem,
        "data_criacao":        _dt_para_str(t.data_criacao),
        "data_atualizacao":    _dt_para_str(t.data_atualizacao),
        "faturamento_bruto":   t.faturamento_bruto,
        "faturamento_liquido": t.faturamento_liquido,
        "comissao":            t.comissao,
        "valor_orcamento":     t.valor_orcamento,
        "estagio_lead":        t.estagio_lead,
        "plano":               t.plano,
        "objecao":             t.objecao,
        "whatsapp":            t.whatsapp,
        "etapa_followup":      t.etapa_followup,
    }


def _row_para_tarefa(row) -> Tarefa:
    return Tarefa(
        link=row["link"],
        nome=row["nome"],
        status=row["status"],
        origem=row["origem"],
        data_criacao=_str_para_dt(row["data_criacao"]),
        data_atualizacao=_str_para_dt(row["data_atualizacao"]),
        faturamento_bruto=row["faturamento_bruto"],
        faturamento_liquido=row["faturamento_liquido"],
        comissao=row["comissao"],
        valor_orcamento=row["valor_orcamento"],
        estagio_lead=row["estagio_lead"],
        plano=row["plano"],
        objecao=row["objecao"],
        whatsapp=row["whatsapp"],
        etapa_followup=row["etapa_followup"],
    )


# ------------------------------------------------------------------
# Conexão thread-local
# ------------------------------------------------------------------

def _abrir_conexao() -> sqlite3.Connection:
    """
    Abre (ou reutiliza) a conexão SQLite da thread atual.
    Cria schema se necessário. Chamado uma vez por thread.
    """
    conn = sqlite3.connect(str(DB_PATH), isolation_level=None)
    conn.row_factory = sqlite3.Row

    # PRAGMAs antes do DDL — executescript faria COMMIT implícito que os perderia
    conn.execute("PRAGMA journal_mode=WAL")    # leitura concorrente sem bloqueio
    conn.execute("PRAGMA synchronous=NORMAL")  # balanceado entre performance e segurança

    # DDL com execute() individual para não interferir com isolation_level=None
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tarefas (
            link                TEXT PRIMARY KEY,
            nome                TEXT NOT NULL,
            status              TEXT NOT NULL DEFAULT '',
            origem              TEXT NOT NULL DEFAULT '',
            data_criacao        TEXT NOT NULL,
            data_atualizacao    TEXT NOT NULL,
            faturamento_bruto   REAL NOT NULL DEFAULT 0,
            faturamento_liquido REAL NOT NULL DEFAULT 0,
            comissao            REAL NOT NULL DEFAULT 0,
            valor_orcamento     REAL NOT NULL DEFAULT 0,
            estagio_lead        TEXT NOT NULL DEFAULT '',
            plano               TEXT NOT NULL DEFAULT '',
            objecao             TEXT NOT NULL DEFAULT '',
            whatsapp            TEXT NOT NULL DEFAULT '',
            etapa_followup      TEXT NOT NULL DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_meta (
            lista_id     TEXT PRIMARY KEY,
            last_sync_ms INTEGER NOT NULL DEFAULT 0
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarefas_origem       ON tarefas (origem)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarefas_atualizacao  ON tarefas (data_atualizacao)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tarefas_criacao      ON tarefas (data_criacao)")

    # Tabela de notificações — alertas de follow-up e radar
    conn.execute("""
        CREATE TABLE IF NOT EXISTS notificacoes (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo       TEXT NOT NULL,
            titulo     TEXT NOT NULL,
            mensagem   TEXT NOT NULL,
            tarefa_id  TEXT,
            tarefa_url TEXT,
            script     TEXT,
            criado_em  TEXT NOT NULL,
            resolvido  INTEGER NOT NULL DEFAULT 0,
            adiado_ate TEXT
        )
    """)

    # Tabela de relatórios PULSE — histórico de Battle Plan / Fechamento
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pulse_reports (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            tipo       TEXT NOT NULL,
            horario    TEXT NOT NULL,
            data       TEXT NOT NULL,
            criado_em  TEXT NOT NULL,
            dados_json TEXT NOT NULL
        )
    """)
    # Migração: colunas adicionadas após criação inicial
    for col, ddl in [
        ("origem",   "TEXT NOT NULL DEFAULT 'auto'"),
        ("pdf_path", "TEXT NOT NULL DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE pulse_reports ADD COLUMN {col} {ddl}")
        except sqlite3.OperationalError:
            pass  # coluna já existe — comportamento esperado na migração

    # Tabela de variáveis de negócio — sem hardcode de percentuais no código
    conn.execute("""
        CREATE TABLE IF NOT EXISTS config_business (
            chave     TEXT PRIMARY KEY,
            valor     TEXT NOT NULL,
            descricao TEXT NOT NULL DEFAULT ''
        )
    """)

    # Defaults (só inseridos na primeira execução — ON CONFLICT IGNORE)
    _defaults = [
        ("base_comissao_empresa",  "8.0",  "Comissão base para leads da empresa (%)"),
        ("base_comissao_propria",  "10.0", "Comissão base para leads próprias/prospecção ativa (%)"),
        ("taxa_bonus_elite",       "2.0",  "Bônus adicional para FSS Score 16 — Elite (%)"),
        ("fss_score_usuario",      "1",    "Nota FSS atual do vendedor (1-16, sincronizada do ClickUp)"),
        ("fss_task_id",            "",     "ID da task ClickUp com o campo 'Nota FSS' do vendedor"),
        ("usuario_nome",           "",     "Nome do vendedor (preenchido automaticamente pelo token)"),
        ("usuario_id",             "",     "ID do usuário no ClickUp"),
    ]
    with conn:
        conn.executemany(
            "INSERT OR IGNORE INTO config_business (chave, valor, descricao) VALUES (?, ?, ?)",
            _defaults,
        )

    return conn


def _conn() -> sqlite3.Connection:
    """Retorna a conexão da thread atual, abrindo-a se necessário."""
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = _abrir_conexao()
    return _local.conn


def fechar_conexao_thread() -> None:
    """
    Fecha e descarta a conexão da thread atual.
    Deve ser chamado ao final de cada thread de trabalho para evitar
    acúmulo de file handles (BUG 1 fix).
    """
    conn = getattr(_local, "conn", None)
    if conn:
        try:
            conn.close()
        except Exception:
            pass
        _local.conn = None


# ------------------------------------------------------------------
# DatabaseManager
# ------------------------------------------------------------------

class DatabaseManager:
    """
    Gerenciador SQLite thread-safe via thread-local connections + WAL.
    Instâncias podem ser criadas em qualquer thread; cada thread mantém
    sua própria conexão aberta durante a vida útil da thread.
    """

    def __init__(self) -> None:
        _conn()  # garante que o schema existe na thread atual

    # ------------------------------------------------------------------
    # Escrita
    # ------------------------------------------------------------------

    def salvar_tarefas(self, tarefas: list[Tarefa]) -> None:
        """
        True upsert via ON CONFLICT DO UPDATE — não deleta/reinsere a linha.
        Preserva colunas não informadas e é significativamente mais rápido
        que INSERT OR REPLACE em datasets grandes.
        """
        if not tarefas:
            return

        sql = """
            INSERT INTO tarefas (
                link, nome, status, origem,
                data_criacao, data_atualizacao,
                faturamento_bruto, faturamento_liquido, comissao,
                valor_orcamento, estagio_lead, plano, objecao,
                whatsapp, etapa_followup
            ) VALUES (
                :link, :nome, :status, :origem,
                :data_criacao, :data_atualizacao,
                :faturamento_bruto, :faturamento_liquido, :comissao,
                :valor_orcamento, :estagio_lead, :plano, :objecao,
                :whatsapp, :etapa_followup
            )
            ON CONFLICT(link) DO UPDATE SET
                nome               = excluded.nome,
                status             = excluded.status,
                data_atualizacao   = excluded.data_atualizacao,
                faturamento_bruto  = excluded.faturamento_bruto,
                faturamento_liquido= excluded.faturamento_liquido,
                comissao           = excluded.comissao,
                valor_orcamento    = excluded.valor_orcamento,
                estagio_lead       = excluded.estagio_lead,
                plano              = excluded.plano,
                objecao            = excluded.objecao,
                whatsapp           = excluded.whatsapp,
                etapa_followup     = excluded.etapa_followup
        """
        conn = _conn()
        with conn:
            conn.executemany(sql, [_tarefa_para_row(t) for t in tarefas])
        logger.debug("Upsert de %d tarefas concluído.", len(tarefas))

    def registrar_sincronizacao(self, lista_id: str, tarefas: list[Tarefa]) -> None:
        """
        Salva max(date_updated) - 1ms como ponteiro do próximo delta.
        -1ms evita off-by-one: tasks com exatamente esse timestamp são
        incluídas no próximo sync (date_updated_gt = ponteiro não as excluiria).
        """
        if not tarefas:
            return
        max_ms = max(
            int(t.data_atualizacao.timestamp() * 1000) for t in tarefas
        ) - 1  # -1ms: garante que tasks no exato max_ms aparecem no próximo delta
        conn = _conn()
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO sync_meta VALUES (?, ?)",
                [lista_id, max_ms],
            )

    # ------------------------------------------------------------------
    # Leitura
    # ------------------------------------------------------------------

    def carregar_tarefas(self, origem: str | None = None) -> list[Tarefa]:
        if origem:
            rows = _conn().execute(
                "SELECT * FROM tarefas WHERE origem = ?", [origem]
            ).fetchall()
        else:
            rows = _conn().execute("SELECT * FROM tarefas").fetchall()
        return [_row_para_tarefa(r) for r in rows]

    def tem_dados(self) -> bool:
        row = _conn().execute("SELECT COUNT(*) FROM tarefas").fetchone()
        return (row[0] if row else 0) > 0

    # ------------------------------------------------------------------
    # config_business — variáveis de negócio dinâmicas
    # ------------------------------------------------------------------

    def get_config(self, chave: str, default: str = "") -> str:
        """Lê uma variável de negócio. Retorna `default` se não encontrada."""
        row = _conn().execute(
            "SELECT valor FROM config_business WHERE chave = ?", [chave]
        ).fetchone()
        return row["valor"] if row else default

    def set_config(self, chave: str, valor: str) -> None:
        """Persiste uma variável de negócio (upsert)."""
        with _conn():
            _conn().execute(
                "INSERT INTO config_business (chave, valor, descricao) VALUES (?, ?, '') "
                "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                [chave, valor],
            )

    def get_all_config(self) -> dict[str, str]:
        """Retorna todas as variáveis de negócio como dict {chave: valor}."""
        rows = _conn().execute(
            "SELECT chave, valor FROM config_business"
        ).fetchall()
        return {r["chave"]: r["valor"] for r in rows}

    def get_config_float(self, chave: str, default: float = 0.0) -> float:
        """Atalho: lê config como float."""
        try:
            return float(self.get_config(chave, str(default)))
        except ValueError:
            return default

    def get_config_int(self, chave: str, default: int = 0) -> int:
        """Atalho: lê config como int."""
        try:
            return int(self.get_config(chave, str(default)))
        except ValueError:
            return default

    def total(self, origem: str) -> int:
        row = _conn().execute(
            "SELECT COUNT(*) FROM tarefas WHERE origem = ?", [origem]
        ).fetchone()
        return row[0] if row else 0

    def ultima_sincronizacao_ms(self, lista_id: str) -> int | None:
        """
        Ponteiro para o próximo delta. None = primeira sync (busca completa).
        """
        row = _conn().execute(
            "SELECT last_sync_ms FROM sync_meta WHERE lista_id = ?", [lista_id]
        ).fetchone()
        return row["last_sync_ms"] if row else None

    def ultima_sincronizacao(self) -> datetime | None:
        """Timestamp da última sync bem-sucedida de qualquer lista (para a UI)."""
        row = _conn().execute(
            "SELECT MAX(last_sync_ms) AS ms FROM sync_meta"
        ).fetchone()
        if row and row["ms"]:
            return datetime.fromtimestamp((row["ms"] + 1) / 1000, tz=timezone.utc)
        return None

    # ------------------------------------------------------------------
    # Queries de inteligência — foco em qualificação e follow-up
    # ------------------------------------------------------------------

    def _where_ativa(self) -> tuple[str, list]:
        """
        Fragmento SQL que exclui leads com status final.
        Usa LIKE sem lower() para preservar emojis e acentos.
        Retorna (sql_fragment, params).
        """
        filtro = _filtro_status_final_sql()
        return f"NOT ({filtro})", list(_STATUS_FINAIS_LIKE)

    def leads_qualificacao(self) -> list[Tarefa]:
        """
        Leads em qualificação — filtra pelo board status do ClickUp.
        Inclui: qualificação, stand-by (aguardando primeiro contato).
        NUNCA inclui fechadas, perdidas ou arquivadas.
        """
        rows = _conn().execute(
            """
            SELECT * FROM tarefas
            WHERE origem = 'pipeline'
              AND (
                status LIKE 'qualifica%'
                OR status LIKE 'stand%'
              )
            ORDER BY data_atualizacao ASC
            """,
        ).fetchall()
        return [_row_para_tarefa(r) for r in rows]

    def leads_followup(self) -> list[Tarefa]:
        """
        Leads em follow-up — filtra pelo board status do ClickUp.
        NUNCA inclui fechadas, perdidas ou arquivadas.
        """
        rows = _conn().execute(
            """
            SELECT * FROM tarefas
            WHERE origem = 'pipeline'
              AND status LIKE 'follow%'
            ORDER BY data_atualizacao ASC
            """,
        ).fetchall()
        return [_row_para_tarefa(r) for r in rows]

    def leads_ativas(self) -> list[Tarefa]:
        """
        Todas as leads ativas — exclui perdidas/fechadas/arquivadas.
        Usado como fallback pelo radar quando leads_qualificacao+followup retornam vazio.
        NUNCA retorna fechadas, perdidas ou arquivadas.
        """
        where, params = self._where_ativa()
        rows = _conn().execute(
            f"""
            SELECT * FROM tarefas
            WHERE origem = 'pipeline'
              AND {where}
            ORDER BY data_atualizacao ASC
            """,
            params,
        ).fetchall()
        return [_row_para_tarefa(r) for r in rows]

    def leads_paradas(self, horas: int = 72) -> list[Tarefa]:
        """
        Leads ativas sem atualização há mais de `horas` h.
        Usa filtro LIKE para capturar 'fechado 🦈', 'perdida/arquivada' etc.
        """
        where, params = self._where_ativa()
        rows = _conn().execute(
            f"""
            SELECT * FROM tarefas
            WHERE origem = 'pipeline'
              AND {where}
              AND datetime(data_atualizacao) < datetime('now', ?)
            ORDER BY data_atualizacao ASC
            """,
            params + [f"-{horas} hours"],
        ).fetchall()
        return [_row_para_tarefa(r) for r in rows]

    def leads_sem_valor(self) -> list[Tarefa]:
        """Leads ativas sem proposta ou sem faturamento — processo travado."""
        where, params = self._where_ativa()
        rows = _conn().execute(
            f"""
            SELECT * FROM tarefas
            WHERE origem = 'pipeline'
              AND {where}
              AND (
                  valor_orcamento = 0
                  OR (faturamento_bruto = 0 AND faturamento_liquido = 0)
              )
            ORDER BY data_atualizacao DESC
            """,
            params,
        ).fetchall()
        return [_row_para_tarefa(r) for r in rows]

    def leads_novas(self, dias: int = 7) -> list[Tarefa]:
        """Leads criadas nos últimos `dias` dias — status ativo."""
        where, params = self._where_ativa()
        rows = _conn().execute(
            f"""
            SELECT * FROM tarefas
            WHERE origem = 'pipeline'
              AND {where}
              AND datetime(data_criacao) > datetime('now', ?)
            ORDER BY data_criacao DESC
            """,
            params + [f"-{dias} days"],
        ).fetchall()
        return [_row_para_tarefa(r) for r in rows]

    def leads_quentes(self, horas: int = 48) -> list[Tarefa]:
        """
        Leads com orçamento/proposta enviados sem resposta há mais de `horas` h.
        Status ativo + orçamento/proposta no status ou estagio_lead.
        Fix: LIKE '%or%amento%' para capturar orçamento e orcamento.
        """
        where, params = self._where_ativa()
        rows = _conn().execute(
            f"""
            SELECT * FROM tarefas
            WHERE origem = 'pipeline'
              AND {where}
              AND (
                  status          LIKE '%or%amento%'
                  OR status       LIKE '%proposta%'
                  OR status       LIKE '%Proposta%'
                  OR status       LIKE '%enviado%'
                  OR status       LIKE '%Enviado%'
                  OR estagio_lead LIKE '%or%amento%'
                  OR estagio_lead LIKE '%proposta%'
              )
              AND datetime(data_atualizacao) < datetime('now', ?)
            ORDER BY data_atualizacao ASC
            """,
            params + [f"-{horas} hours"],
        ).fetchall()
        return [_row_para_tarefa(r) for r in rows]

    def leads_dados_faltando(self) -> list:
        """
        Leads ativas com campos críticos vazios.
        Retorna lista de DadosFaltando ordenada por mais campos faltando primeiro.
        Foco: WhatsApp e Proposta são os campos mais críticos para vendas.
        """
        from src.models import DadosFaltando

        where, params = self._where_ativa()
        rows = _conn().execute(
            f"""
            SELECT *,
                   CAST((julianday('now') - julianday(data_criacao)) AS INTEGER) AS dias
            FROM tarefas
            WHERE origem = 'pipeline'
              AND {where}
              AND (
                  whatsapp      = ''
                  OR valor_orcamento = 0
              )
            ORDER BY
              (CASE WHEN whatsapp = '' THEN 2 ELSE 0 END +
               CASE WHEN valor_orcamento = 0 THEN 1 ELSE 0 END) DESC,
              data_atualizacao ASC
            """,
            params,
        ).fetchall()

        resultado = []
        for row in rows:
            tarefa = _row_para_tarefa(row)
            campos: list[str] = []
            if not tarefa.whatsapp:
                campos.append("WhatsApp")
            if tarefa.valor_orcamento == 0:
                campos.append("Sem Proposta")
            dias = int(row["dias"]) if row["dias"] else 0
            resultado.append(DadosFaltando(
                tarefa=tarefa,
                campos_vazios=tuple(campos),
                dias_desde_criacao=dias,
            ))
        return resultado

    # leads_perdidas_recentes REMOVIDO — não exibir leads perdidas/fechadas no sistema.
    # O foco é EXCLUSIVAMENTE em leads ativas (qualificação e follow-up).

    # ------------------------------------------------------------------
    # Notificações
    # ------------------------------------------------------------------

    def resolver_notificacao(self, nid: int) -> None:
        """Marca uma notificação como resolvida."""
        conn = _conn()
        with conn:
            conn.execute("UPDATE notificacoes SET resolvido=1 WHERE id=?", (nid,))

    def adiar_notificacao(self, nid: int, data_iso: str) -> None:
        """Adia uma notificação para a data informada (ISO 8601)."""
        conn = _conn()
        with conn:
            conn.execute(
                "UPDATE notificacoes SET adiado_ate=? WHERE id=?",
                (data_iso, nid),
            )

    def carregar_notificacoes_pendentes(self, hoje: str) -> list[dict]:
        """
        Retorna até 4 notificações pendentes (não resolvidas e não adiadas).

        Args:
            hoje: Data atual em formato ISO 8601 (ex: '2026-04-23').
        """
        rows = _conn().execute(
            """SELECT * FROM notificacoes
               WHERE resolvido=0 AND (adiado_ate IS NULL OR adiado_ate<=?)
               ORDER BY criado_em ASC LIMIT 4""",
            (hoje,),
        ).fetchall()
        return [dict(r) for r in rows]

    def leads_ativas_total(self) -> int:
        """Conta total de leads ativas (não-finalizadas) no pipeline."""
        where, params = self._where_ativa()
        row = _conn().execute(
            f"SELECT COUNT(*) FROM tarefas WHERE origem='pipeline' AND {where}",
            params,
        ).fetchone()
        return row[0] if row else 0

    # ── Relatórios PULSE ────────────────────────────────────────

    def salvar_relatorio_pulse(self, relatorio: dict, criado_em_override: str | None = None, upsert: bool = False, origem: str = "auto") -> int:
        """Persiste um relatório PULSE. Retorna o id gerado (0 se ignorado por duplicata)."""
        import json
        criado_em = criado_em_override or datetime.now().isoformat(timespec="seconds")
        data    = relatorio.get("data", "")
        horario = relatorio.get("horario", "")
        if upsert:
            _conn().execute(
                "DELETE FROM pulse_reports WHERE data=? AND horario=?",
                (data, horario),
            )
        else:
            existe = _conn().execute(
                "SELECT 1 FROM pulse_reports WHERE data=? AND horario=?",
                (data, horario),
            ).fetchone()
            if existe:
                return 0
        cur = _conn().execute(
            "INSERT INTO pulse_reports (tipo, horario, data, criado_em, dados_json, origem) VALUES (?,?,?,?,?,?)",
            (
                relatorio.get("tipo", "PULSE"),
                horario,
                data,
                criado_em,
                json.dumps(relatorio, ensure_ascii=False),
                origem,
            ),
        )
        return cur.lastrowid

    def atualizar_pdf_path(self, report_id: int, pdf_path: str) -> None:
        """Atualiza o caminho do PDF gerado para um relatório."""
        _conn().execute(
            "UPDATE pulse_reports SET pdf_path=? WHERE id=?",
            (pdf_path, report_id),
        )

    def deletar_relatorio_pulse(self, report_id: int) -> str:
        """Deleta registro do DB e retorna o pdf_path para o chamador apagar o arquivo."""
        row = _conn().execute(
            "SELECT pdf_path FROM pulse_reports WHERE id=?", (report_id,)
        ).fetchone()
        pdf_path = row["pdf_path"] if row else ""
        _conn().execute("DELETE FROM pulse_reports WHERE id=?", (report_id,))
        return pdf_path

    def limpar_duplicatas_pulse(self) -> int:
        """Remove duplicatas de pulse_reports mantendo apenas o id mais alto por (data, horario)."""
        cur = _conn().execute("""
            DELETE FROM pulse_reports
            WHERE id NOT IN (
                SELECT MAX(id) FROM pulse_reports GROUP BY data, horario
            )
        """)
        return cur.rowcount

    def listar_relatorios_pulse(self, limit: int = 60) -> list[dict]:
        """Retorna lista resumida dos últimos relatórios (sem dados_json)."""
        rows = _conn().execute(
            "SELECT id, tipo, horario, data, criado_em, origem, pdf_path FROM pulse_reports ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def obter_relatorio_pulse_por_id(self, report_id: int) -> dict | None:
        """Retorna o relatório completo pelo ID."""
        import json
        row = _conn().execute(
            "SELECT dados_json FROM pulse_reports WHERE id = ?",
            (report_id,),
        ).fetchone()
        if not row:
            return None
        return json.loads(row["dados_json"])

