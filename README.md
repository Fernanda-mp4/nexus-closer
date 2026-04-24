# Nexus Closer

Sistema desktop de automação operacional para times de vendas de alta performance. Integra ClickUp e BotConversa para impor disciplina de pipeline, gerar propostas comerciais sem intervenção manual e auditar o desempenho individual do closer em tempo real.

---

## Visão Executiva

O problema que o sistema resolve é previsível e custoso: leads qualificadas sendo perdidas não por falta de produto ou preço, mas por lentidão de resposta, follow-up esquecido e proposta gerada com erro.

O Nexus Closer atua como um gerente operacional autônomo, com dois ciclos diários de auditoria (07h e 19h) que varrem todo o pipeline ativo e surfaçam o que precisa de ação imediata — antes que a janela de fechamento feche.

**O que muda na operação:**

- **Radar tático em tempo real** — todas as leads ativas visíveis em um único painel, com indicação visual de urgência por tempo parado no estágio. Lead parada em estágio crítico sem resposta aparece em vermelho antes que o closer precise lembrar.

- **Auditoria PULSE** — varredura automática duas vezes ao dia. Leads com dados incompletos, estágios estagnados acima do threshold ou follow-up fora do prazo geram alertas de qualidade antes de virarem perda.

- **Motor de propostas** — da calculadora de precificação à proposta formatada em PDF: zero digitação manual, zero erro de valor, consistência visual em 100% das propostas geradas.

- **FSS Score** — métrica individual de 1 a 16 pontos por closer, calculada em tempo real com base em atendimento, uso do pipeline, execução do follow-up e qualidade dos dados. Elimina subjetividade na avaliação de performance.

- **Sequência de follow-up de 60 dias** — plano de contato estruturado com gatilhos nos dias 0, 2, 5, 7, 10, 14, 18, 21, 30, 55, 58 e 60. O sistema rastreia cada lead na sequência e sinaliza o contato do dia automaticamente.

**Segurança operacional**

Dados de leads, propostas e negociações são processados e armazenados localmente, sem passar por servidores de terceiros. As únicas informações que trafegam externamente são as enviadas deliberadamente às integrações da operação (ClickUp e BotConversa). Cada instalação é completamente isolada por configuração — nenhum dado de uma operação é acessível a outra, mesmo rodando sobre a mesma base de código.

---

## Arquitetura e Decisões Técnicas

### Stack

| Camada | Tecnologia | Justificativa |
|--------|-----------|---------------|
| Interface | pywebview (WebView2) + HTML/CSS/JS | Desktop-first sem Electron — binário leve, sem runtime Node.js |
| Backend | Python 3.11+ com asyncio | Concorrência sem overhead de threading manual |
| Persistência | SQLite via camada de abstração única | Portabilidade total, zero dependência de servidor |
| Geração de PDF | PyMuPDF (fitz) | Renderização em camadas sobre template achatado, sem servidor de impressão |
| Agendamento | APScheduler embutido | Sem dependência de infraestrutura externa para os ciclos PULSE |
| Integrações | ClickUp API v2 + BotConversa API | ClickUp como fonte canônica; BotConversa como canal de automação |
| Distribuição | PyInstaller (`--onefile`) | Executável único — sem instalação de dependências pelo usuário final |

### Decisões arquiteturais

**Bridge JS↔Python controlada**
A interface web se comunica com o core Python exclusivamente via `window.pywebview.api`. O frontend não tem acesso direto a nenhuma integração externa nem ao banco de dados. Isso mantém a lógica de negócio isolada da camada de apresentação e torna a superfície auditável.

**ClickUp como única fonte de verdade**
Nenhuma decisão de urgência, auditoria ou automação é baseada em estado local. O sistema sempre opera sobre dados sincronizados do ClickUp. Essa escolha elimina a classe inteira de divergências onde cache local e estado real do pipeline se dessincronizam silenciosamente.

**White-label por design**
Toda identidade de cliente é injetada via `client_config.js` em runtime. O código-fonte não contém nenhuma referência a empresa, closer ou dado operacional de cliente. Isso torna o sistema um produto de prateleira: mesma base de código, deployments independentes por cliente.

**Motor de PDF local**
PyMuPDF renderiza sobre templates achatados diretamente na máquina do usuário. Nenhum dado de lead ou proposta comercial trafega para serviços externos de renderização. O arquivo gerado existe localmente até o envio deliberado pelo closer.

**Módulos desacoplados com responsabilidade única**
`calculator.py` é puro — sem I/O, sem estado. `score.py` não acessa banco. `database_manager.py` é o único ponto de contato com SQLite. Esse isolamento reduz o custo de teste, facilita substituição de componentes e torna o sistema auditável por módulo.

### Segurança

A postura de segurança do sistema é resultado das escolhas arquiteturais acima, não de configuração pontual:

**Local-first** — o processamento ocorre na máquina do usuário. Dados sensíveis de negociação não transitam por infraestrutura intermediária para nenhuma operação core do sistema.

**Isolamento de credenciais** — a camada de configuração é separada do código-fonte por design. Rotação de credenciais e auditoria de acesso não exigem alteração de lógica de negócio.

**Superfície de ataque reduzida** — sem servidor web exposto, sem banco remoto, sem dependência de SaaS para funcionalidade core. O vetor de ataque externo é limitado às chamadas deliberadas às APIs de integração.

### Estrutura do projeto

```
nexus-closer/
├── main_web.py                    entrypoint principal e bridge Python ↔ JS
├── src/
│   ├── constants.py               preços, estágios e thresholds de urgência
│   ├── models.py                  DTOs e dataclasses (únicos)
│   └── services/
│       ├── database_manager.py    único ponto de acesso ao SQLite
│       ├── clickup_service.py     integração ClickUp API
│       └── botconversa_service.py worker BotConversa
│   └── modules/
│       ├── orcamento/calculator.py  motor de cálculo puro
│       └── fss/score.py             lógica do Score FSS
├── web/
│   ├── index.html                 interface principal
│   ├── style.css                  design system Biomechanical Neon-CRT
│   ├── app.js                     lógica da interface
│   └── client_config.js           configuração white-label por cliente
└── assets/
    └── templates/                 templates base para geração de PDF
```

---

## Como Rodar Localmente

**Pré-requisitos:** Python 3.11+

```bash
# Clonar e configurar ambiente
git clone <repositório>
cd nexus-closer
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# Configurar variáveis de ambiente
# Criar .env na raiz com: CLICKUP_TOKEN, CLICKUP_LIST_PIPELINE_ID,
# CLICKUP_LIST_CONTRATOS_ID, BOTCONVERSA_API_KEY, BOTCONVERSA_BASE_URL

# Iniciar
python main_web.py
```

**Distribuição:** `pyinstaller main_web.py --onefile` gera o executável final para entrega ao usuário.

---

## Licença

Produto proprietário. Distribuição restrita. Todos os direitos reservados.
