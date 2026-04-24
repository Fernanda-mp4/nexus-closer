"""
Nexus Closer — Gateway de Comunicação com a API do ClickUp.

Responsabilidade única: encapsular todas as requisições HTTP ao ClickUp,
expondo métodos limpos para os módulos internos do sistema.

Distribuição futura: cada Closer de Elite configura apenas seu .env
com o próprio token e IDs de lista. Nenhuma alteração neste arquivo
é necessária para onboarding.
"""

import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from src.models import Tarefa

# ------------------------------------------------------------------
# Mapeamento de IDs dos Custom Fields — carregados do .env
# ------------------------------------------------------------------
_CAMPOS = {
    "faturamento_bruto":   os.getenv("CLICKUP_FIELD_FATURAMENTO_BRUTO", ""),
    "faturamento_liquido": os.getenv("CLICKUP_FIELD_FATURAMENTO_LIQUIDO", ""),
    "comissao":            os.getenv("CLICKUP_FIELD_COMISSAO", ""),
    "valor_orcamento":     os.getenv("CLICKUP_FIELD_VALOR_ORCAMENTO", ""),
    "estagio_lead":        os.getenv("CLICKUP_FIELD_ESTAGIO_LEAD", ""),
    "plano":               os.getenv("CLICKUP_FIELD_PLANO", ""),
    "objecao":             os.getenv("CLICKUP_FIELD_OBJECAO", ""),
    "whatsapp":            os.getenv("CLICKUP_FIELD_WHATSAPP", ""),
    "etapa_followup":      os.getenv("CLICKUP_FIELD_ETAPA_FOLLOWUP", ""),
}

load_dotenv()

console = Console()
logger  = logging.getLogger(__name__)

_BASE_URL               = "https://api.clickup.com/api/v2"
_CACHE_PATH             = Path(".cache_data.json")
_CACHE_VALIDADE_SEGUNDOS = 1800   # 30 minutos
_WORKERS_PARALELOS      = 10      # threads simultâneas para paginação


# ------------------------------------------------------------------
# Serialização de cache (funções de módulo — sem acesso a self)
# ------------------------------------------------------------------

def _tarefa_para_dict(t: Tarefa) -> dict:
    return {
        "nome":               t.nome,
        "status":             t.status,
        "link":               t.link,
        "origem":             t.origem,
        "data_criacao":       t.data_criacao.isoformat(),
        "data_atualizacao":   t.data_atualizacao.isoformat(),
        "faturamento_bruto":  t.faturamento_bruto,
        "faturamento_liquido": t.faturamento_liquido,
        "comissao":           t.comissao,
        "valor_orcamento":    t.valor_orcamento,
        "estagio_lead":       t.estagio_lead,
        "plano":              t.plano,
        "objecao":            t.objecao,
        "whatsapp":           t.whatsapp,
        "etapa_followup":     t.etapa_followup,
        "closer_id":          t.closer_id,
        "closer_nome":        t.closer_nome,
    }


def _dict_para_tarefa(d: dict) -> Tarefa:
    return Tarefa(
        nome=d["nome"],
        status=d["status"],
        link=d["link"],
        origem=d["origem"],
        data_criacao=datetime.fromisoformat(d["data_criacao"]),
        data_atualizacao=datetime.fromisoformat(d["data_atualizacao"]),
        faturamento_bruto=float(d.get("faturamento_bruto", 0)),
        faturamento_liquido=float(d.get("faturamento_liquido", 0)),
        comissao=float(d.get("comissao", 0)),
        valor_orcamento=float(d.get("valor_orcamento", 0)),
        estagio_lead=d.get("estagio_lead", ""),
        plano=d.get("plano", ""),
        objecao=d.get("objecao", ""),
        whatsapp=d.get("whatsapp", ""),
        etapa_followup=d.get("etapa_followup", ""),
        closer_id=d.get("closer_id", ""),
        closer_nome=d.get("closer_nome", ""),
    )


# ------------------------------------------------------------------
# Classe principal
# ------------------------------------------------------------------

class ClickUpService:
    """
    Gateway principal para a API do ClickUp.

    Inicializa com o token e os IDs de lista lidos do .env,
    garantindo que nenhuma credencial fique exposta no código-fonte.
    """

    def __init__(self) -> None:
        self._token              = self._carregar_variavel("CLICKUP_TOKEN")
        self.lista_pipeline_id   = self._carregar_variavel("CLICKUP_LIST_PIPELINE_ID")
        self.lista_contratos_id  = self._carregar_variavel("CLICKUP_LIST_CONTRATOS_ID")

        self._headers = {
            "Authorization": self._token,
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Suporte interno
    # ------------------------------------------------------------------

    @staticmethod
    def _carregar_variavel(nome: str) -> str:
        valor = os.getenv(nome)
        if not valor:
            raise EnvironmentError(
                f"Variável de ambiente obrigatória não encontrada: '{nome}'. "
                "Verifique se o arquivo .env está presente e corretamente preenchido."
            )
        return valor

    def _get(self, endpoint: str, params: dict | None = None) -> dict:
        """
        Executa uma requisição GET autenticada. Thread-safe (cada chamada
        recebe seu próprio objeto de resposta).
        """
        url = f"{_BASE_URL}{endpoint}"
        try:
            resposta = requests.get(url, headers=self._headers, params=params, timeout=30)
            resposta.raise_for_status()
            return resposta.json()
        except requests.exceptions.ConnectionError as erro:
            raise ConnectionError(
                "Não foi possível conectar à API do ClickUp. "
                "Verifique sua conexão com a internet."
            ) from erro
        except requests.exceptions.HTTPError as erro:
            codigo = erro.response.status_code if erro.response else "desconhecido"
            raise requests.HTTPError(
                f"Erro na API do ClickUp (HTTP {codigo}). "
                "Verifique se o token e os IDs de lista estão corretos."
            ) from erro

    # ------------------------------------------------------------------
    # Extração e normalização
    # ------------------------------------------------------------------

    @staticmethod
    def _extrair_valor_campo(campos_raw: list[dict], campo_id: str) -> str:
        for campo in campos_raw:
            if campo.get("id") != campo_id:
                continue
            valor = campo.get("value")
            if valor is None:
                return ""
            # Campos dict (dropdown v2, label, etc.) — retorna o name
            if isinstance(valor, dict):
                return valor.get("name", "")
            # Campos dropdown retornam o orderindex (int) — resolve pelo type_config
            if isinstance(valor, int):
                opcoes = campo.get("type_config", {}).get("options", [])
                for opc in opcoes:
                    if opc.get("orderindex") == valor:
                        return opc.get("name", str(valor))
                return str(valor)
            # String que seja inteiro puro → pode ser orderindex de dropdown
            if isinstance(valor, str) and valor.isdigit():
                opcoes = campo.get("type_config", {}).get("options", [])
                for opc in opcoes:
                    if str(opc.get("orderindex", "")) == valor:
                        return opc.get("name", valor)
            # Campos numéricos e texto simples
            return str(valor)
        return ""

    @staticmethod
    def _para_float(texto: str) -> float:
        try:
            return float(texto) if texto else 0.0
        except ValueError:
            return 0.0

    @staticmethod
    def _timestamp_ms_para_datetime(ts_ms: str | int | None) -> datetime:
        if not ts_ms:
            return datetime.fromtimestamp(0, tz=timezone.utc)
        try:
            return datetime.fromtimestamp(int(ts_ms) / 1000, tz=timezone.utc)
        except (ValueError, OSError):
            return datetime.fromtimestamp(0, tz=timezone.utc)

    def _normalizar_tarefa(self, raw: dict, origem: str) -> Tarefa:
        campos  = raw.get("custom_fields", [])
        extrair = lambda campo_id: self._extrair_valor_campo(campos, campo_id)

        assignees  = raw.get("assignees", [])
        closer_id  = str(assignees[0].get("id", ""))       if assignees else ""
        closer_nome = assignees[0].get("username", "")     if assignees else ""

        plano_val   = extrair(_CAMPOS["plano"])
        estagio_val = extrair(_CAMPOS["estagio_lead"])

        return Tarefa(
            nome=raw.get("name", ""),
            status=raw.get("status", {}).get("status", ""),
            link=raw.get("url", ""),
            origem=origem,
            data_criacao=self._timestamp_ms_para_datetime(raw.get("date_created")),
            data_atualizacao=self._timestamp_ms_para_datetime(raw.get("date_updated")),
            faturamento_bruto=self._para_float(extrair(_CAMPOS["faturamento_bruto"])),
            faturamento_liquido=self._para_float(extrair(_CAMPOS["faturamento_liquido"])),
            comissao=self._para_float(extrair(_CAMPOS["comissao"])),
            valor_orcamento=self._para_float(extrair(_CAMPOS["valor_orcamento"])),
            estagio_lead=estagio_val,
            plano=plano_val,
            objecao=extrair(_CAMPOS["objecao"]),
            whatsapp=extrair(_CAMPOS["whatsapp"]),
            etapa_followup=extrair(_CAMPOS["etapa_followup"]),
            closer_id=closer_id,
            closer_nome=closer_nome,
        )

    def _buscar_pagina(self, lista_id: str, pagina: int, desde_ms: int | None = None) -> dict:
        """Busca uma única página de tarefas — projetado para uso paralelo."""
        params: dict = {"page": pagina, "include_closed": "true", "subtasks": "false"}
        if desde_ms is not None:
            params["date_updated_gt"] = desde_ms  # delta sync — só o que mudou
        return self._get(f"/list/{lista_id}/task", params=params)

    # ------------------------------------------------------------------
    # Busca com paginação paralela (CLAUDE.md seção 8)
    # ------------------------------------------------------------------

    def buscar_tarefas(
        self,
        lista_id: str,
        origem: str,
        desde_ms: int | None = None,
    ) -> list[Tarefa]:
        """
        Busca tarefas com paginação paralela.

        Args:
            lista_id:  ID da lista no ClickUp.
            origem:    "pipeline" ou "contratos".
            desde_ms:  Unix timestamp em ms — se informado, busca apenas
                       tarefas atualizadas após esse momento (delta sync).
                       None = busca completa.
        """
        dados_p0 = self._buscar_pagina(lista_id, 0, desde_ms)
        batch_p0 = dados_p0.get("tasks", [])
        tarefas: list[Tarefa] = [self._normalizar_tarefa(t, origem) for t in batch_p0]

        if dados_p0.get("last_page", True) or not batch_p0:
            return tarefas

        proxima_pagina = 1
        with ThreadPoolExecutor(max_workers=_WORKERS_PARALELOS) as executor:
            while True:
                paginas = range(proxima_pagina, proxima_pagina + _WORKERS_PARALELOS)
                futures = {
                    executor.submit(self._buscar_pagina, lista_id, p, desde_ms): p
                    for p in paginas
                }

                encontrou_ultima = False
                for future in as_completed(futures):
                    try:
                        dados = future.result()
                        batch = dados.get("tasks", [])
                        tarefas.extend(self._normalizar_tarefa(t, origem) for t in batch)
                        if dados.get("last_page", True) or not batch:
                            encontrou_ultima = True
                    except Exception as exc:
                        logger.warning("Falha ao buscar página da lista %s: %s", lista_id, exc)

                if encontrou_ultima:
                    break
                proxima_pagina += _WORKERS_PARALELOS

        return tarefas

    def buscar_pipeline(self, desde_ms: int | None = None) -> list[Tarefa]:
        """Retorna tarefas do Pipeline (completo ou delta)."""
        return self.buscar_tarefas(self.lista_pipeline_id, "pipeline", desde_ms)

    def buscar_contratos(self, desde_ms: int | None = None) -> list[Tarefa]:
        """Retorna tarefas de Contratos (completo ou delta)."""
        return self.buscar_tarefas(self.lista_contratos_id, "contratos", desde_ms)

    # ------------------------------------------------------------------
    # Cache local (CLAUDE.md seção 8)
    # ------------------------------------------------------------------

    def salvar_cache(
        self,
        pipeline: list[Tarefa],
        contratos: list[Tarefa],
    ) -> None:
        """
        Persiste pipeline e contratos em .cache_data.json com timestamp.

        Falha silenciosa — indisponibilidade de disco não deve travar o sistema.
        """
        try:
            payload = {
                "timestamp": time.time(),
                "pipeline":  [_tarefa_para_dict(t) for t in pipeline],
                "contratos": [_tarefa_para_dict(t) for t in contratos],
            }
            _CACHE_PATH.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as exc:
            logger.warning("Não foi possível salvar o cache: %s", exc)

    def carregar_cache(self) -> tuple[list[Tarefa], list[Tarefa]] | None:
        """
        Carrega pipeline e contratos do cache local se ainda válido.

        Returns:
            Tupla (pipeline, contratos) ou None se cache inexistente/expirado/corrompido.
        """
        if not _CACHE_PATH.exists():
            return None
        try:
            payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
            if time.time() - payload.get("timestamp", 0) > _CACHE_VALIDADE_SEGUNDOS:
                return None
            pipeline  = [_dict_para_tarefa(d) for d in payload.get("pipeline", [])]
            contratos = [_dict_para_tarefa(d) for d in payload.get("contratos", [])]
            return pipeline, contratos
        except Exception as exc:
            logger.warning("Cache corrompido ou ilegível — ignorando: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Busca de lead por nome — usado pela Calculadora de Orçamento
    # ------------------------------------------------------------------

    def buscar_lead_briefing(self, nome: str) -> dict | None:
        """
        Pesquisa uma tarefa no Pipeline pelo nome e retorna dados do Briefing.

        A busca é case-insensitive e parcial (ClickUp `search` param).
        O primeiro resultado retornado pela API é usado.

        Args:
            nome: Nome da lead conforme registrado no ClickUp e no BotConversa.

        Returns:
            Dict com campos encontrados, ou None se nenhum resultado.
            Estrutura: {
                "nome": str,
                "link": str,
                "status": str,
                "whatsapp": str,
                "briefing": {campo: valor},
                "campos_vazios": [campo, ...],
            }
        """
        params = {
            "search":         nome,
            "include_closed": "false",
            "subtasks":       "false",
            "page":           0,
        }
        try:
            dados   = self._get(f"/list/{self.lista_pipeline_id}/task", params=params)
        except Exception as exc:
            logger.warning("buscar_lead_briefing: falha na API — %s", exc)
            return None

        tarefas = dados.get("tasks", [])
        if not tarefas:
            return None

        raw        = tarefas[0]
        campos_raw = raw.get("custom_fields", [])

        # Nomes dos campos de Briefing procurados (case-insensitive)
        _BRIEFING_CHAVES = {"faculdade", "curso", "tipo de pesquisa", "tipo_pesquisa"}

        briefing: dict[str, str] = {}
        for campo in campos_raw:
            nome_c = campo.get("name", "").lower().strip()
            if nome_c not in _BRIEFING_CHAVES:
                continue
            nome_exibicao = campo.get("name", nome_c)
            v = campo.get("value")
            if v is None:
                briefing[nome_exibicao] = ""
                continue
            if isinstance(v, dict):
                briefing[nome_exibicao] = v.get("name", "")
            elif isinstance(v, int):
                opts = campo.get("type_config", {}).get("options", [])
                for o in opts:
                    if o.get("orderindex") == v:
                        briefing[nome_exibicao] = o.get("name", str(v))
                        break
                else:
                    briefing[nome_exibicao] = str(v)
            else:
                briefing[nome_exibicao] = str(v)

        campos_vazios = [k for k, val in briefing.items() if not val.strip()]

        return {
            "nome":         raw.get("name", ""),
            "link":         raw.get("url", ""),
            "status":       raw.get("status", {}).get("status", ""),
            "whatsapp":     self._extrair_valor_campo(campos_raw, _CAMPOS["whatsapp"]),
            "briefing":     briefing,
            "campos_vazios": campos_vazios,
        }

    # ------------------------------------------------------------------
    # Validação de conexão
    # ------------------------------------------------------------------

    def obter_lista(self, lista_id: str) -> dict:
        return self._get(f"/list/{lista_id}")

    # ------------------------------------------------------------------
    # Usuário atual e FSS Score
    # ------------------------------------------------------------------

    def fetch_current_user(self) -> dict:
        """
        Retorna dados do usuário autenticado pelo token.

        Returns:
            {"id": str, "username": str, "email": str, "profilePicture": str}
        """
        dados = self._get("/user")
        user  = dados.get("user", {})
        return {
            "id":             str(user.get("id", "")),
            "username":       user.get("username", ""),
            "email":          user.get("email", ""),
            "profilePicture": user.get("profilePicture", ""),
        }

    def fetch_fss_score(self, fss_task_id: str = "") -> int:
        """
        Busca a Nota FSS do vendedor no ClickUp.

        Estratégia:
          1. Se `fss_task_id` fornecido → busca o campo 'Nota FSS' nessa task.
          2. Caso contrário → retorna 0 (caller usa o valor local do DB).

        Args:
            fss_task_id: ID da task ClickUp que contém o campo 'Nota FSS'.

        Returns:
            Inteiro 1-16, ou 0 se não encontrado.
        """
        if not fss_task_id:
            return 0
        try:
            dados  = self._get(f"/task/{fss_task_id}")
            campos = dados.get("custom_fields", [])
            for campo in campos:
                nome = campo.get("name", "").lower().strip()
                if "nota fss" in nome or "fss score" in nome or "fss" == nome:
                    valor = campo.get("value")
                    if valor is None:
                        return 0
                    # Dropdown → resolve pelo orderindex (dict com 'orderindex')
                    if isinstance(valor, dict) and "orderindex" in valor:
                        opcoes = campo.get("type_config", {}).get("options", [])
                        for opc in opcoes:
                            if opc.get("orderindex") == valor.get("orderindex"):
                                try:
                                    return max(1, min(16, int(opc["name"])))
                                except (ValueError, KeyError):
                                    pass
                    # Campo numérico direto → int/float
                    if isinstance(valor, (int, float)):
                        return max(1, min(16, int(valor)))
                    # String numérica
                    try:
                        return max(1, min(16, int(str(valor))))
                    except ValueError:
                        pass
        except Exception as exc:
            logger.warning("fetch_fss_score falhou: %s", exc)
        return 0

    def sincronizar_usuario_e_fss(self) -> dict:
        """
        Busca usuário + FSS Score e retorna dict pronto para salvar no DB.

        Returns:
            {"usuario_id": str, "usuario_nome": str, "fss_score_usuario": str}
        """
        try:
            user = self.fetch_current_user()
        except Exception as exc:
            logger.warning("Não foi possível buscar usuário: %s", exc)
            return {}

        return {
            "usuario_id":        user["id"],
            "usuario_nome":      user["username"],
        }

    def testar_conexao(self) -> bool:
        try:
            dados      = self.obter_lista(self.lista_pipeline_id)
            nome_lista = dados.get("name", "Nome não disponível")

            mensagem = Text()
            mensagem.append("Conexão com o ClickUp ", style="bold white")
            mensagem.append("estabelecida com sucesso.\n\n", style="bold green")
            mensagem.append("Lista de Pipeline: ", style="dim white")
            mensagem.append(nome_lista, style="bold cyan")

            console.print(
                Panel(
                    mensagem,
                    title="[bold green]Nexus Closer — Status da Conexão[/bold green]",
                    border_style="green",
                    padding=(1, 4),
                )
            )
            return True

        except (EnvironmentError, ConnectionError, requests.HTTPError) as erro:
            console.print(
                Panel(
                    f"[bold red]Falha na conexão:[/bold red]\n{erro}",
                    title="[bold red]Nexus Closer — Erro de Conexão[/bold red]",
                    border_style="red",
                    padding=(1, 4),
                )
            )
            return False
