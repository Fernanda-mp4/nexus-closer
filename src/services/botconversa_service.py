"""
Nexus Closer — BotConversa Worker (Event-Driven Background Service).

Responsabilidade: disparar fluxos de automação no BotConversa via API REST
em resposta a eventos internos do sistema (ex: "Proposta Gerada").
Roda inteiramente em segundo plano — sem interação manual do usuário.

Variáveis de ambiente obrigatórias (.env):
    BOTCONVERSA_API_KEY   — chave de API do BotConversa
    BOTCONVERSA_BASE_URL  — base URL da API (ex: https://api.botconversa.com.br/api/v1)
"""

import logging
import os
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.database_manager import DatabaseManager

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Constantes
# ------------------------------------------------------------------

_BASE_URL = os.getenv("BOTCONVERSA_BASE_URL", "https://api.botconversa.com.br/api/v1")
_API_KEY = os.getenv("BOTCONVERSA_API_KEY", "")
_TIMEOUT = 15.0  # segundos

if not _API_KEY:
    logger.warning("BOTCONVERSA_API_KEY não configurada — worker operará em modo simulado.")

# Intervalo de verificação de follow-ups pendentes (em segundos)
_INTERVALO_VERIFICACAO = 300  # 5 minutos


# ------------------------------------------------------------------
# Worker principal
# ------------------------------------------------------------------

class BotConversaWorker:
    """
    Serviço de automação assíncrona integrado ao BotConversa.

    Dispara fluxos via API REST quando eventos internos do Nexus Closer
    são emitidos. Todo log é encaminhado ao Terminal de Logs da UI.

    Args:
        log_callback: Função chamada com cada mensagem de log formatada.
                      Assinatura: (mensagem: str) -> None
    """

    def __init__(
        self,
        log_callback: Callable[[str], None],
        db: "DatabaseManager | None" = None,
    ) -> None:
        self._log_callback = log_callback
        self._db = db
        self._scheduler = AsyncIOScheduler()
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # Log interno
    # ------------------------------------------------------------------

    def _log(self, nivel: str, mensagem: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        linha = f"[{ts}][{nivel}] {mensagem}"
        logger.info(linha)
        self._log_callback(linha)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Inicia o worker e o scheduler de verificação periódica."""
        if not _API_KEY:
            self._log("WARN", "BOTCONVERSA_API_KEY ausente no .env — worker em modo simulado")
        else:
            self._log("SYS", "BOTCONVERSA WORKER INICIADO")

        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={"api-key": _API_KEY, "Content-Type": "application/json"},
            timeout=_TIMEOUT,
        )

        self._scheduler.add_job(
            self._verificar_followups_pendentes,
            trigger="interval",
            seconds=_INTERVALO_VERIFICACAO,
            id="verificar_followups",
        )
        self._scheduler.start()
        self._log("SYS", f"SCHEDULER ATIVO — CICLO A CADA {_INTERVALO_VERIFICACAO}s")

    def stop(self) -> None:
        """Encerra o scheduler e fecha o cliente HTTP."""
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        if self._client:
            self._log("SYS", "BOTCONVERSA WORKER ENCERRADO")

    # ------------------------------------------------------------------
    # Disparo de eventos
    # ------------------------------------------------------------------

    async def disparar_evento(
        self,
        evento: str,
        protocolo_id: str,
        payload: dict | None = None,
    ) -> bool:
        """
        Dispara um fluxo no BotConversa associado a um evento do sistema.

        REGRA CRÍTICA: o protocolo_id deve ser idêntico ao ID da lead no BotConversa.

        Args:
            evento:        Nome do evento (ex: "PROPOSTA_GERADA", "FOLLOWUP_D7").
            protocolo_id:  ID do protocolo / lead no BotConversa.
            payload:       Dados adicionais enviados ao fluxo (opcional).

        Returns:
            True se o disparo foi bem-sucedido, False caso contrário.
        """
        if not self._client:
            self._log("ERR", f"CLIENTE HTTP NAO INICIALIZADO — evento={evento}")
            return False

        if not _API_KEY:
            self._log("SIM", f"[SIMULADO] EVENTO={evento} | ID={protocolo_id}")
            return True

        endpoint = f"/subscriber/{protocolo_id}/send-flow"
        corpo = {"flow_trigger": evento, **(payload or {})}

        try:
            resposta = await self._client.post(endpoint, json=corpo)
            resposta.raise_for_status()
            self._log("OK", f"FLUXO DISPARADO: {evento} | ID={protocolo_id}")
            return True

        except httpx.HTTPStatusError as exc:
            self._log(
                "ERR",
                f"FALHA HTTP {exc.response.status_code}: {evento} | ID={protocolo_id}",
            )
            return False

        except httpx.RequestError as exc:
            self._log("ERR", f"ERRO DE CONEXAO: {evento} — {exc}")
            return False

    async def disparar_proposta_gerada(self, protocolo_id: str, nome_lead: str) -> bool:
        """Atalho semântico: dispara o fluxo de 7 dias pós-proposta."""
        self._log("SYS", f"FLUXO DE 7 DIAS INICIADO — LEAD={nome_lead}")
        return await self.disparar_evento(
            evento="PROPOSTA_GERADA",
            protocolo_id=protocolo_id,
            payload={"nome_lead": nome_lead},
        )

    # ------------------------------------------------------------------
    # Tarefa periódica
    # ------------------------------------------------------------------

    async def _verificar_followups_pendentes(self) -> None:
        """
        Verifica follow-ups pendentes no banco e dispara os fluxos no BotConversa.

        Para cada lead em stage follow-up com WhatsApp e etapa_followup preenchidos,
        dispara o evento correspondente (ex: FOLLOWUP_D7).
        Chamada automaticamente pelo scheduler a cada 5 minutos.
        """
        self._log("SYS", "VERIFICANDO FOLLOWUPS PENDENTES...")

        if self._db is None:
            self._log("WARN", "DatabaseManager não injetado — verificação ignorada")
            return

        try:
            leads = self._db.leads_followup()
        except Exception as exc:
            self._log("ERR", f"ERRO AO CONSULTAR DB: {exc}")
            return

        disparados = 0
        for lead in leads:
            if not lead.whatsapp or not lead.etapa_followup:
                continue
            evento = f"FOLLOWUP_{lead.etapa_followup.upper().replace(' ', '_')}"
            sucesso = await self.disparar_evento(
                evento=evento,
                protocolo_id=lead.whatsapp,
                payload={"nome_lead": lead.nome},
            )
            if sucesso:
                disparados += 1

        self._log("SYS", f"VERIFICACAO CONCLUIDA — {disparados} fluxo(s) disparado(s)")
