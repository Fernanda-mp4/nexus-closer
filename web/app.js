/* ═══════════════════════════════════════════════════════════════
   NEXUS CLOSER — app.js  V8
   Bridge pywebview ↔ UI
   JS → Python : window.pywebview.api.method(args) → Promise
   Python → JS : receberLog(), mostrarNotificacao()  (globais)
═══════════════════════════════════════════════════════════════ */

// ── Overlays táticos (ORÇAMENTOS / LOGS / SISTEMA / MASTER) ──
document.querySelectorAll('.overlay-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const key = btn.dataset.overlay;
    const panel = document.getElementById('overlay-' + key);
    if (!panel) return;

    const isOpen = panel.classList.contains('open');
    // Fechar todos
    document.querySelectorAll('.overlay-panel').forEach(p => p.classList.remove('open'));
    document.querySelectorAll('.overlay-btn').forEach(b => b.classList.remove('active'));

    if (!isOpen) {
      panel.classList.add('open');
      btn.classList.add('active');
      if (key === 'master') carregarElite();
    }
  });
});

// Fechar overlay pelo botão interno ✕
document.querySelectorAll('.overlay-close').forEach(btn => {
  btn.addEventListener('click', () => {
    const key = btn.dataset.overlay;
    const panel = document.getElementById('overlay-' + key);
    if (panel) panel.classList.remove('open');
    document.querySelectorAll('.overlay-btn').forEach(b => b.classList.remove('active'));
  });
});

// Fechar overlay com Escape
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    document.querySelectorAll('.overlay-panel').forEach(p => p.classList.remove('open'));
    document.querySelectorAll('.overlay-btn').forEach(b => b.classList.remove('active'));
  }
});

// ── Terminal de logs ──────────────────────────────────────────
const _logStrip = document.getElementById('last-log-strip');

function termLog(msg) {
  const log = document.getElementById('terminal-log-full');
  const line = document.createElement('span');
  line.className = 'log-line';
  line.textContent = msg;
  log.appendChild(line);
  while (log.children.length > 500) log.removeChild(log.firstChild);
  log.scrollTop = log.scrollHeight;

  // Espelha última linha no masthead
  if (_logStrip) _logStrip.textContent = msg;
}

// ── Python → JS : recebe log do backend ──────────────────────
function receberLog(mensagem) { termLog(mensagem); }

// ── Python → JS : relatório PULSE ────────────────────────────
function receberRelatorioPulse(r) {
  if (!r || r.status !== 'ok') return;

  // Atualiza HUD
  document.getElementById('hud-pct-ok').textContent    = r.pct_ok + '%';
  document.getElementById('hud-gargalos').textContent  = r.gargalos?.length ?? 0;
  document.getElementById('hud-zombies').textContent   = r.zombies?.length  ?? 0;
  document.getElementById('hud-pulse-ultimo').textContent = 'último: ' + r.horario;

  // Cores de alerta no HUD
  const elPct = document.getElementById('hud-pct-ok');
  elPct.style.color = r.pct_ok >= 90 ? 'var(--neon)' : r.pct_ok >= 70 ? 'var(--amber)' : 'var(--danger)';

  const totalFalhas = (r.pendencias?.length ?? 0) + (r.gargalos?.length ?? 0) + (r.zombies?.length ?? 0);
  if (totalFalhas === 0) return;

  // Notificação visual no pipeline
  const msg = [
    totalFalhas + ' lead(s) com estágio desatualizado',
    r.gargalos?.length  ? '⚠ Gargalos: ' + r.gargalos.map(l => l.nome.split(' ')[0]).join(', ') : '',
    r.zombies?.length   ? '☠ Zombies: '  + r.zombies.map(l  => l.nome.split(' ')[0]).join(', ')  : '',
    r.pendencias?.length ? r.pendencias.length + ' pendência(s) de atualização' : '',
  ].filter(Boolean).join('\n');

  mostrarNotificacao('info', `[${r.tipo}] AUDITORIA — ${r.horario}`, msg, null);
}

// ── ELITE — Thresholds do FSS Score ──────────────────────────
const _FSS_TIERS = [
  { min: 16, perfil: 'ELITE',         bonus: 1.00, plus: 0.02, cor: '#00FF41' },
  { min: 12, perfil: 'PROFISSIONAL',  bonus: 1.00, plus: 0.00, cor: '#00FF41' },
  { min: 10, perfil: 'MEDIANO',       bonus: 0.50, plus: 0.00, cor: '#FFAA00' },
  { min:  1, perfil: 'DESORGANIZADO', bonus: 0.00, plus: 0.00, cor: '#FF3333' },
];
const _FSS_FAIXAS = [
  { min: 20000, bonus_base: 5000 },
  { min: 15000, bonus_base: 3000 },
  { min: 10000, bonus_base: 1500 },
  { min:  5000, bonus_base:  600 },
  { min:     0, bonus_base:    0 },
];
// Labels por pilar — cada nota (1-4) tem descrição específica de critério
const _PILAR_LABELS = {
  crm: {
    1: 'Pipeline abandonado — tasks sem update há +24h, campos vazios',
    2: 'Pipeline parcial — atrasos ou campos incompletos',
    3: 'Pipeline atualizado — status e campos ok diariamente',
    4: 'Pipeline impecável — 100% completo, pronto para reunião',
  },
  fu: {
    1: 'Sem follow-up — leads esquecidas, sequência quebrada',
    2: 'Follow-up irregular — dias perdidos na sequência',
    3: 'Follow-up executado — sequência 60d respeitada',
    4: 'Follow-up elite — zero leads perdidas por falta de contato',
  },
  atend: {
    1: 'Sem atendimento — leads sem resposta há +24h',
    2: 'Atendimento tardio — backlog acumulado',
    3: 'Atendimento diário — todos respondidos, ordem hierárquica',
    4: 'Atendimento elite — rápido, sem backlog, encerramento no BotConversa',
  },
  det: {
    1: 'Desorganizado — sem histórico, leads sem classificação',
    2: 'Parcialmente organizado — inconsistências no pipeline',
    3: 'Organizado — histórico atualizado, leads classificadas',
    4: 'Organização elite — pipeline limpo e auditável',
  },
};

function _fssNivel(score) {
  return _FSS_TIERS.find(t => score >= t.min) || _FSS_TIERS[_FSS_TIERS.length - 1];
}
function _fatBonus(fat) {
  return (_FSS_FAIXAS.find(f => fat >= f.min) || _FSS_FAIXAS[_FSS_FAIXAS.length - 1]).bonus_base;
}

// ── ELITE — Score Input: interatividade em tempo real ────────
function _initEliteScore() {
  const input = document.getElementById('elite-score-input');
  const fatInput = document.getElementById('elite-fat-input');
  if (input)    input.addEventListener('input', _atualizarEliteDisplay);
  if (fatInput) fatInput.addEventListener('input', _atualizarEliteDisplay);
  _atualizarEliteDisplay();
  _initPilares();
}

function _atualizarEliteDisplay() {
  const score = Math.max(1, Math.min(16, parseInt(document.getElementById('elite-score-input')?.value) || 1));
  const fat   = parseFloat(document.getElementById('elite-fat-input')?.value) || 0;
  const nivel = _fssNivel(score);

  // Score bar
  const bar = document.getElementById('elite-score-bar');
  if (bar) { bar.style.width = (score / 16 * 100) + '%'; bar.style.background = nivel.cor; }

  // Perfil tag
  const tag = document.getElementById('elite-perfil');
  if (tag) { tag.textContent = nivel.perfil; tag.style.color = nivel.cor; tag.style.borderColor = nivel.cor; }

  // Cálculo financeiro
  const comissaoBase = fat * 0.08;
  const bonusBase    = _fatBonus(fat);
  const bonusEfetivo = bonusBase * nivel.bonus;
  const plusElite    = fat * nivel.plus;
  const total        = comissaoBase + bonusEfetivo + plusElite;

  const fmt = v => 'R$ ' + v.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  set('elite-comissao-base', fmt(comissaoBase));
  set('elite-bonus-val',     nivel.bonus > 0 ? fmt(bonusEfetivo) : 'R$ 0,00 — score insuficiente');
  set('elite-plus-val',      fmt(plusElite));
  set('elite-total',         fmt(total));

  const plusRow = document.getElementById('elite-plus-row');
  if (plusRow) plusRow.style.display = nivel.plus > 0 ? 'flex' : 'none';

  const totalEl = document.getElementById('elite-total');
  if (totalEl) totalEl.style.color = score >= 16 ? '#00FF41' : score >= 12 ? '#00CC33' : '#FFAA00';

  // Sync with HUD se estiver aberto
  receberFssScore(Math.round(score / 4), nivel.perfil, 0, 0);
}

// ── ELITE — Pilares interativos (clique para marcar nota 1-4) ─
function _initPilares() {
  document.querySelectorAll('.elite-pilar-stars').forEach(container => {
    container.innerHTML = '';
    const pilar = container.dataset.pilar;
    for (let i = 1; i <= 4; i++) {
      const btn = document.createElement('button');
      btn.className = 'elite-star-btn';
      btn.dataset.val = String(i);
      btn.textContent = i;
      const pilarLabels = _PILAR_LABELS[pilar] || {};
      btn.title = pilarLabels[i] || '';
      btn.addEventListener('click', () => {
        container.querySelectorAll('.elite-star-btn').forEach(b =>
          b.classList.toggle('active', parseInt(b.dataset.val) <= i));
        const descEl = document.getElementById('pdesc-' + pilar);
        if (descEl) descEl.textContent = pilarLabels[i] || '';
        _calcPilarSum();
      });
      container.appendChild(btn);
    }
  });
}

function _calcPilarSum() {
  let sum = 0;
  document.querySelectorAll('.elite-pilar-stars').forEach(c => {
    const active = [...c.querySelectorAll('.elite-star-btn.active')];
    sum += active.length > 0 ? Math.max(...active.map(b => parseInt(b.dataset.val))) : 0;
  });
  const el = document.getElementById('elite-pilar-total');
  if (el) el.textContent = String(sum);
  const scoreInput = document.getElementById('elite-score-input');
  if (scoreInput && sum > 0) { scoreInput.value = String(sum); _atualizarEliteDisplay(); }
}

// ── ELITE — Carrega dados do ClickUp e popula indicadores ─────
async function carregarElite() {
  const loading = document.getElementById('elite-loading');
  const content = document.getElementById('elite-content');
  if (loading) loading.style.display = 'flex';
  if (content) content.style.opacity = '0.4';

  _initEliteScore();

  // Botão atualizar
  document.getElementById('btn-refresh-elite')?.addEventListener('click', carregarElite, { once: true });

  try {
    const r = await window.pywebview.api.obter_relatorio_master();
    if (r?.status === 'ok') {
      _renderEliteIndicadores(r.fss);
      _renderElitePipeline(r.pipeline);
      _renderEliteAcoes(r.fss, r.pipeline);
      // Valores financeiros do ClickUp
      const fmt = v => v > 0 ? 'R$ ' + v.toLocaleString('pt-BR', { minimumFractionDigits: 2 }) : '—';
      const ckOrc = document.getElementById('elite-ck-orcamentos');
      const ckCon = document.getElementById('elite-ck-contratos');
      if (ckOrc) ckOrc.textContent = fmt(r.financeiro?.pipeline_potencial || 0);
      if (ckCon) ckCon.textContent = fmt(r.financeiro?.bruto || 0);
      renderEliteRadar(r.fss?.usuario_id || '');
    }
  } catch (e) {
    showError('Erro ao carregar dados', String(e));
  } finally {
    if (loading) loading.style.display = 'none';
    if (content) content.style.opacity = '1';
  }
}

function _renderEliteIndicadores(fss) {
  const setBar = (id, pct) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.width = pct + '%';
    el.style.background = pct >= 80 ? 'var(--neon)' : pct >= 50 ? 'var(--amber)' : 'var(--danger)';
  };
  const setPct = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val + '%'; };

  setBar('ind-bar-crm',   fss.crm);          setPct('ind-pct-crm',   fss.crm);
  setBar('ind-bar-fu',    fss.followup);      setPct('ind-pct-fu',    fss.followup);
  setBar('ind-bar-atend', fss.atendimento);   setPct('ind-pct-atend', fss.atendimento);
  setBar('ind-bar-det',   fss.detalhes);      setPct('ind-pct-det',   fss.detalhes);

  const infoEl = document.getElementById('elite-leads-closer');
  if (infoEl) infoEl.textContent = fss.leads_closer + ' leads do closer';
}

function _renderElitePipeline(pipeline) {
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = String(val); };
  set('elite-total-ativas', pipeline.total_ativas);
  set('elite-gargalos',     pipeline.gargalos?.length || 0);
  set('elite-zombies',      pipeline.zombies?.length  || 0);

  const cont = document.getElementById('elite-por-estagio');
  if (!cont) return;
  cont.innerHTML = '';
  const maxC = Math.max(...(pipeline.por_estagio || []).map(e => e.count), 1);
  (pipeline.por_estagio || []).slice(0, 5).forEach(e => {
    const row = document.createElement('div');
    row.className = 'elite-estagio-row';

    const lbl = document.createElement('span');
    lbl.className = 'elite-estagio-name';
    lbl.textContent = e.estagio.length > 14 ? e.estagio.substring(0, 12) + '…' : e.estagio;

    const wrap = document.createElement('div');
    wrap.className = 'elite-ind-bar-wrap';
    const bar = document.createElement('div');
    bar.className = 'elite-ind-bar';
    bar.style.width = Math.round(e.count / maxC * 100) + '%';
    bar.style.background = 'var(--neon)';
    wrap.appendChild(bar);

    const cnt = document.createElement('span');
    cnt.className = 'elite-estagio-count';
    cnt.textContent = String(e.count);

    row.append(lbl, wrap, cnt);
    cont.appendChild(row);
  });
}

function _renderEliteAcoes(fss, pipeline) {
  const cont = document.getElementById('elite-acoes');
  if (!cont) return;
  cont.innerHTML = '';

  const acoes = [];
  if (fss.crm < 80)
    acoes.push({ txt: 'Atualize pipeline: plano + estágio em leads pendentes', cor: 'var(--danger)', leads: fss.leads_sem_crm || [] });
  if (fss.followup < 80)
    acoes.push({ txt: 'Defina etapa de follow-up nas leads sem status', cor: 'var(--amber)', leads: fss.leads_sem_fu || [] });
  if (fss.atendimento < 80)
    acoes.push({ txt: 'Responda leads com mais de 48h sem contato', cor: 'var(--amber)', leads: fss.leads_sem_atend || [] });
  if (fss.detalhes < 80)
    acoes.push({ txt: 'Organização: preencha WhatsApp + arquive perdidas no BotConversa', cor: 'var(--neon)', leads: fss.leads_sem_det || [] });
  if ((pipeline.gargalos?.length || 0) > 0)
    acoes.push({ txt: `${pipeline.gargalos.length} gargalo(s) bloqueando o pipeline — mova ou feche`, cor: 'var(--danger)', leads: pipeline.gargalos });
  if ((pipeline.zombies?.length || 0) > 0)
    acoes.push({ txt: `${pipeline.zombies.length} zombie(s) detectado(s) — qualifique ou arquive`, cor: '#aa00ff', leads: pipeline.zombies });
  if (acoes.length === 0)
    acoes.push({ txt: 'Pipeline saudável — mantenha o ritmo para o nível Elite!', cor: 'var(--neon)', leads: [] });

  acoes.forEach(a => {
    const item = document.createElement('div');
    item.className = 'elite-acao-item elite-acao-accordion';
    item.style.borderLeftColor = a.cor;

    // Header clicável
    const header = document.createElement('div');
    header.className = 'elite-acao-header';
    const bullet = document.createElement('span');
    bullet.textContent = '[*] ';
    bullet.style.color = a.cor;
    const txt = document.createElement('span');
    txt.textContent = a.txt;
    const arrow = document.createElement('span');
    arrow.className = 'elite-acao-arrow';
    arrow.textContent = a.leads.length ? ' ▶' : '';
    arrow.style.color = a.cor;
    header.append(bullet, txt, arrow);

    // Dropdown com nomes das leads
    const dropdown = document.createElement('div');
    dropdown.className = 'elite-acao-dropdown';
    dropdown.style.display = 'none';

    if (a.leads.length) {
      a.leads.forEach(nome => {
        const row = document.createElement('div');
        row.className = 'elite-acao-lead-row';
        row.textContent = '  › ' + nome;
        row.style.color = 'rgba(0,255,65,0.7)';
        dropdown.appendChild(row);
      });

      header.style.cursor = 'pointer';
      header.addEventListener('click', () => {
        const open = dropdown.style.display !== 'none';
        dropdown.style.display = open ? 'none' : 'block';
        arrow.textContent = open ? ' ▶' : ' ▼';
      });
    }

    item.append(header, dropdown);
    cont.appendChild(item);
  });
}

// ── Python → JS : FSS Score do closer ────────────────────────
function receberFssScore(score, nivel, total, completas) {
  const elVal   = document.getElementById('hud-fss-val');
  const elBar   = document.getElementById('hud-fss-bar');
  const elNivel = document.getElementById('hud-fss-nivel');
  if (!elVal) return;

  // O FSS exibido no HUD é uma nota de 1-4 (score CRM), não 1-16
  // Converte: 1→4pts, 2→8pts, 3→12pts, 4→16pts para exibição
  const exibido = score * 4;
  elVal.textContent = exibido + '/16';
  elBar.style.width = (exibido / 16 * 100) + '%';
  elBar.style.background =
    score >= 4 ? 'var(--neon)' :
    score >= 3 ? 'var(--amber)' :
    score >= 2 ? '#ff8800' : 'var(--danger)';
  elNivel.textContent = nivel ? nivel.toUpperCase() : 'AGUARDANDO';

  // Cor do valor principal
  elVal.style.color =
    score >= 4 ? 'var(--neon)' :
    score >= 3 ? 'var(--amber)' : 'var(--danger)';
}

// ── Erro técnico — registra no painel de LOGS com detalhe completo ──
function showError(titulo, mensagem) {
  const ts = new Date().toLocaleTimeString('pt-BR', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  termLog(`[ERR ${ts}] ${titulo} :: ${mensagem}`);
}

// ── Python → JS : Aviso urgente (AVISOS táticos) ─────────────
function mostrarAviso(titulo, mensagem) {
  const toasts = document.getElementById('aviso-toasts');
  const dismissBtn = document.getElementById('aviso-dismiss-all');
  if (!toasts) return;

  // Substitui aviso com mesmo título se já existe
  const existing = toasts.querySelector(`[data-aviso-titulo="${CSS.escape(titulo)}"]`);
  if (existing) existing.remove();

  const toast = document.createElement('div');
  toast.className = 'aviso-toast';
  toast.dataset.avisoTitulo = titulo;

  const hdr = document.createElement('div');
  hdr.className = 'aviso-toast-hdr';

  const lbl = document.createElement('span');
  lbl.className = 'aviso-toast-lbl';
  lbl.textContent = '[!] ' + String(titulo).toUpperCase();

  const x = document.createElement('button');
  x.className = 'aviso-toast-close';
  x.textContent = '✕';
  x.addEventListener('click', () => { toast.remove(); _atualizarDismissBtn(); });

  hdr.append(lbl, x);

  const msg = document.createElement('div');
  msg.className = 'aviso-toast-msg';
  msg.textContent = String(mensagem);

  toast.append(hdr, msg);
  toasts.appendChild(toast);
  _atualizarDismissBtn();

  setTimeout(() => { if (toast.isConnected) { toast.remove(); _atualizarDismissBtn(); } }, 30000);
}

function _atualizarDismissBtn() {
  const btn = document.getElementById('aviso-dismiss-all');
  const toasts = document.getElementById('aviso-toasts');
  if (!btn || !toasts) return;
  const count = toasts.querySelectorAll('.aviso-toast').length;
  btn.style.display = count > 0 ? 'block' : 'none';
  btn.textContent = `✕ FECHAR TODOS (${count})`;
}

document.getElementById('aviso-dismiss-all')?.addEventListener('click', () => {
  const toasts = document.getElementById('aviso-toasts');
  if (toasts) toasts.innerHTML = '';
  _atualizarDismissBtn();
});

// ── PULSE — Forçar auditoria manual ──────────────────────────
document.getElementById('btn-forcar-auditoria')?.addEventListener('click', async () => {
  const btn = document.getElementById('btn-forcar-auditoria');
  const orig = btn.textContent;
  btn.textContent = '⟳ AUDITANDO...';
  btn.disabled = true;
  try {
    await window.pywebview.api.auditar_pipeline(true);
  } catch (e) {
    showError('Erro na Auditoria', String(e));
  } finally {
    btn.textContent = orig;
    btn.disabled = false;
  }
});

// ── Python → JS : notificação flutuante ──────────────────────
function mostrarNotificacao(tipo, titulo, mensagem, nid) {
  const container = document.getElementById('notif-container');

  const card = document.createElement('div');
  card.className = 'notif-card ' + (tipo || '');
  card.dataset.nid = nid != null ? String(nid) : '';

  // — Header —
  const header = document.createElement('div');
  header.className = 'notif-header';

  const accent = document.createElement('div');
  accent.className = 'notif-accent';

  const titleEl = document.createElement('span');
  titleEl.className = 'notif-title';
  titleEl.textContent = String(titulo).toUpperCase();

  const closeBtn = document.createElement('button');
  closeBtn.className = 'notif-close';
  closeBtn.textContent = '✕';
  closeBtn.addEventListener('click', () => card.remove());

  header.append(accent, titleEl, closeBtn);

  // — Body —
  const body = document.createElement('div');
  body.className = 'notif-body';
  body.textContent = String(mensagem);

  // — Divisor —
  const divider = document.createElement('div');
  divider.className = 'notif-divider';

  // — Ações —
  const actions = document.createElement('div');
  actions.className = 'notif-actions';

  const btnResolver = document.createElement('button');
  btnResolver.className = 'btn-neon';
  btnResolver.style.cssText = 'font-size:9px;padding:5px 10px;';
  btnResolver.textContent = '✓ RESOLVER';
  btnResolver.addEventListener('click', () => resolverNotif(card));

  const btnAdiar = document.createElement('button');
  btnAdiar.className = 'btn-dim';
  btnAdiar.style.cssText = 'font-size:9px;padding:5px 10px;';
  btnAdiar.textContent = '↻ AMANHÃ';
  btnAdiar.addEventListener('click', () => adiarNotif(card));

  actions.append(btnResolver, btnAdiar);
  card.append(header, body, divider, actions);
  container.appendChild(card);

  setTimeout(() => { if (card.parentNode) card.remove(); }, 12000);
}

function resolverNotif(card) {
  const nid = parseInt(card.dataset.nid, 10);
  if (!isNaN(nid)) window.pywebview.api.resolver_notificacao(nid);
  card.remove();
}

function adiarNotif(card) {
  const nid = parseInt(card.dataset.nid, 10);
  if (!isNaN(nid)) window.pywebview.api.adiar_notificacao(nid);
  card.remove();
}

// ── PIPELINE — Sincronizar ────────────────────────────────────
document.getElementById('btn-sync').addEventListener('click', sincronizar);

async function sincronizar() {
  termLog('[SYS] SINCRONIZANDO COM CLICKUP...');
  _setAssemblerActive(true);
  try {
    const dados = await window.pywebview.api.sincronizar_radar();
    renderLeads(dados || []);
    termLog(`[OK] SINCRONIZAÇÃO CONCLUÍDA — ${(dados || []).length} LEADS`);
  } catch (e) {
    termLog(`[ERR] FALHA NA SINCRONIZAÇÃO: ${e}`);
  } finally {
    _setAssemblerActive(false);
  }
}

// ── Helpers de dados ─────────────────────────────────────────
function _horasDesde(isoStr) {
  if (!isoStr) return null;
  return Math.floor((Date.now() - new Date(isoStr).getTime()) / 3600000);
}

// Sempre mostra dias quando >= 24h
function _formatTempo(horas) {
  if (horas == null) return '—';
  return horas >= 24 ? Math.floor(horas / 24) + 'd' : horas + 'h';
}

function parseDiaFollowup(etapa) {
  if (!etapa) return null;
  const m = String(etapa).match(/(\d+)/);
  return m ? parseInt(m[1], 10) : null;
}

// Cache global de leads para uso em overlays (ex: radar ELITE)
let _cachedLeads = [];

function renderLeads(leads) {
  _cachedLeads = leads;
  const tbody = document.getElementById('leads-body');
  tbody.innerHTML = '';

  if (!leads.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 6;
    td.className = 'empty-state';
    td.textContent = '// NENHUMA LEAD ATIVA';
    tr.appendChild(td);
    tbody.appendChild(tr);
    _atualizarMetricas([]);
    return;
  }

  leads.forEach(l => {
    const horas = _horasDesde(l.data_atualizacao);
    const dia   = parseDiaFollowup(l.etapa_followup);
    const tr    = document.createElement('tr');

    // LEAD
    const tdNome = document.createElement('td');
    tdNome.textContent = l.nome || '—';

    // STATUS
    const tdStatus = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = 'badge badge-' + badgeClass(l.status);
    badge.textContent = (l.status || '—').toUpperCase();
    tdStatus.appendChild(badge);

    // HORAS PARADO (calculado de data_atualizacao)
    const tdHoras = document.createElement('td');
    tdHoras.textContent = _formatTempo(horas);
    if (horas > 48) tdHoras.style.color = 'var(--amber)';

    // PLANO
    const tdPlano = document.createElement('td');
    tdPlano.textContent = l.plano || '—';

    // MOTIVO / ESTÁGIO
    const tdMotivo = document.createElement('td');
    tdMotivo.textContent = dia != null
      ? `D.${dia} — ${l.estagio_lead || 'FOLLOW-UP'}`
      : (l.estagio_lead || '—');
    tdMotivo.style.cssText = 'font-size:10px;color:var(--text-dim)';

    // AÇÃO — abre plano de follow-up da lead
    const tdAcao = document.createElement('td');
    const btnVer = document.createElement('button');
    btnVer.className = dia != null ? 'btn-neon' : 'btn-dim';
    btnVer.style.cssText = 'font-size:9px;padding:4px 8px;';
    btnVer.textContent = dia != null ? '>>> PLANO' : 'VER';
    btnVer.addEventListener('click', () => {
      mostrarAlertaFollowup({
        nome:  l.nome,
        dia:   dia ?? 0,
        plano: l.plano  || '—',
        fss:   l.fss    || 0,
        tipo:  dia != null ? 'fss' : 'info',
        nid:   null,
      });
    });
    tdAcao.appendChild(btnVer);

    tr.append(tdNome, tdStatus, tdHoras, tdPlano, tdMotivo, tdAcao);
    tbody.appendChild(tr);
  });

  _atualizarMetricas(leads);
  renderRadar(leads);
}

function _primeiroNomeCard(lead) {
  return (lead.nome || '—').replace(/^(Dra?\.|Dr\.)\s*/i, '').split(' ')[0];
}

function _renderMiniList(elId, items, onClickFn) {
  const el = document.getElementById(elId);
  if (!el) return;
  el.innerHTML = '';

  const preview = items.slice(0, 2);
  const rest    = items.slice(2);

  const renderRow = (item, expanded) => {
    const row = document.createElement('div');
    row.className = 'mini-item';
    if (onClickFn) {
      row.classList.add('mini-item--clicavel');
      row.addEventListener('click', () => onClickFn(item));
    }
    const nome = document.createElement('span');
    nome.className = 'mini-nome';
    // Expanded: usa nome completo (item.fullName); collapsed: primeiro nome
    nome.textContent = (expanded && item.fullName) ? item.fullName : item.label;
    const info = document.createElement('span');
    info.className = 'mini-info';
    info.textContent = item.sub;
    row.append(nome, info);
    return row;
  };

  preview.forEach(item => el.appendChild(renderRow(item, false)));

  if (rest.length > 0) {
    const more = document.createElement('div');
    more.className = 'mini-more';
    more.textContent = `+${rest.length} mais ▶`;
    more.addEventListener('click', () => {
      more.remove();
      rest.forEach(item => el.appendChild(renderRow(item, true)));
      // Mostra nomes completos nos existentes também
      el.querySelectorAll('.mini-item').forEach((row, i) => {
        if (i < preview.length) {
          const n = row.querySelector('.mini-nome');
          if (n && items[i].fullName) n.textContent = items[i].fullName;
        }
      });
      const close = document.createElement('div');
      close.className = 'mini-more mini-close';
      close.textContent = '▲ FECHAR';
      close.addEventListener('click', () => _renderMiniList(elId, items, onClickFn));
      el.appendChild(close);
    });
    el.appendChild(more);
  }
}

// Estágios que já estão aptos para follow-up, independente do closer
const _ESTAGIOS_FOLLOWUP = new Set([
  'Orçamento enviado', 'Follow-up', 'Contrato enviado', 'Aguardando pagamento'
]);

function _atualizarMetricas(leads) {
  // Qualificação — proposta ainda NÃO enviada e não em estágio de follow-up
  const qualif = leads.filter(l =>
    !_ESTAGIOS_FOLLOWUP.has(l.estagio_lead) &&
    (l.estagio_lead === 'Qualificação' || l.status === 'nova' ||
    (parseDiaFollowup(l.etapa_followup) == null && l.estagio_lead !== 'Fechado'))
  );
  // Follow-up — proposta JÁ enviada OU estágio confirma que está apto
  const followup = leads.filter(l =>
    parseDiaFollowup(l.etapa_followup) != null || _ESTAGIOS_FOLLOWUP.has(l.estagio_lead)
  );
  // Paradas — sem movimento há +48h
  const paradas = leads.filter(l => (_horasDesde(l.data_atualizacao) ?? 0) > 48);
  // Ação imediata — follow-up atrasado ou do dia (D ≤ hoje + 1)
  const acao = followup.filter(l => {
    const horas = _horasDesde(l.data_atualizacao) ?? 0;
    return horas > 0; // qualquer follow-up com tempo passado é ação pendente
  });

  document.getElementById('val-paradas').textContent     = paradas.length;
  document.getElementById('val-qualificacao').textContent = qualif.length;
  document.getElementById('val-followup').textContent    = followup.length;
  document.getElementById('val-acao').textContent        = acao.length;

  // Mini-listas
  _renderMiniList('mini-paradas', paradas
    .sort((a, b) => (_horasDesde(b.data_atualizacao) ?? 0) - (_horasDesde(a.data_atualizacao) ?? 0))
    .map(l => ({ label: _primeiroNomeCard(l), sub: _formatTempo(_horasDesde(l.data_atualizacao)) }))
  );
  _renderMiniList('mini-qualificacao', qualif
    .sort((a, b) => (_horasDesde(b.data_atualizacao) ?? 0) - (_horasDesde(a.data_atualizacao) ?? 0))
    .map(l => ({ label: _primeiroNomeCard(l), sub: _formatTempo(_horasDesde(l.data_atualizacao)), data: l })),
    (item) => mostrarSituacaoQualif(item.data)
  );
  _renderMiniList('mini-followup', followup
    .sort((a, b) => (_horasDesde(b.data_atualizacao) ?? 0) - (_horasDesde(a.data_atualizacao) ?? 0))
    .map(l => {
      const dia = parseDiaFollowup(l.etapa_followup);
      return { label: _primeiroNomeCard(l), fullName: l.nome, sub: dia != null ? 'D.' + dia : (l.estagio_lead || 'FOLLOW-UP') };
    })
  );
  _renderMiniList('mini-acao', acao
    .sort((a, b) => (_horasDesde(b.data_atualizacao) ?? 0) - (_horasDesde(a.data_atualizacao) ?? 0))
    .map(l => {
      const dia = parseDiaFollowup(l.etapa_followup);
      return { label: _primeiroNomeCard(l), fullName: l.nome, sub: dia != null ? 'D.' + dia : (l.estagio_lead || 'FOLLOW-UP') };
    })
  );

  // HUD
  const hudLeads = document.getElementById('hud-leads-count');
  if (hudLeads) hudLeads.textContent = leads.length || '0';

  const emFechamento = followup.sort((a, b) =>
    (_horasDesde(b.data_atualizacao) ?? 0) - (_horasDesde(a.data_atualizacao) ?? 0)
  );
  const hudNext = document.getElementById('hud-next-followup');
  if (hudNext) {
    if (emFechamento.length) {
      const nxt = emFechamento[0];
      const dia = parseDiaFollowup(nxt.etapa_followup);
      hudNext.textContent = _primeiroNomeCard(nxt) + (dia != null ? ' D.' + dia : ' [' + (nxt.estagio_lead || 'FOLLOW-UP') + ']');
    } else {
      hudNext.textContent = 'NENHUM';
    }
  }
}

// ── Thresholds por estágio — espelha src/constants.py URGENCIA_ESTAGIO ──
// Estrutura: { estagio: [horas_ambar, horas_vermelho] }
const _URGENCIA_ESTAGIO = {
  'Coletando dados':      [24,  48],
  'Enviar orçamento':     [ 4,   8],
  'Orçamento enviado':    [48,  72],
  'Follow-up':            [48,  72],
  'Contrato enviado':     [12,  24],
  'Aguardando pagamento': [ 3,   7],
};
const _HORAS_GARGALO = 120;  // 5 dias
const _HORAS_ZOMBIE  = 720;  // 30 dias

// ── Radar SVG — núcleo compartilhado por main radar e ELITE radar ──
function _renderRadarDots(leads, dotsGroupId, CX, CY, R_MAX) {
  const dotsG = document.getElementById(dotsGroupId);
  if (!dotsG) return;
  while (dotsG.firstChild) dotsG.removeChild(dotsG.firstChild);

  leads.forEach((l, i) => {
    const horas     = _horasDesde(l.data_atualizacao) ?? 0;
    const estagio   = l.estagio_lead || '';
    const threshold = _URGENCIA_ESTAGIO[estagio] || [24, 48];
    const [hAmbar, hVerm] = threshold;

    // ── Nível de urgência pelo estágio ──────────────────────────
    let nivel;
    if      (horas > _HORAS_ZOMBIE)  nivel = 'zombie';
    else if (horas > _HORAS_GARGALO) nivel = 'gargalo';
    else if (horas > hVerm)          nivel = 'critico';
    else if (horas > hAmbar)         nivel = 'ambar';
    else                             nivel = 'ok';

    // ── Distância do centro: crítico = centro, ok = borda ───────
    const ratioMap = { zombie: 0.10, gargalo: 0.20, critico: 0.38, ambar: 0.62, ok: 0.85 };
    const r = R_MAX * (ratioMap[nivel] ?? 0.85);

    // ── Cor do dot ───────────────────────────────────────────────
    const fillMap = {
      zombie:  '#FF3333',
      gargalo: '#FF3333',
      critico: '#FF3333',
      ambar:   '#FFAA00',
      ok:      '#00FF41',
    };
    const fill = fillMap[nivel];
    const isCritical = nivel === 'critico' || nivel === 'gargalo' || nivel === 'zombie';

    // ── Posição angular determinística ───────────────────────────
    const angle = (i / Math.max(leads.length, 1)) * 2 * Math.PI + (i * 0.618 * Math.PI);
    const cx = CX + r * Math.sin(angle);
    const cy = CY - r * Math.cos(angle);

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', cx.toFixed(1));
    circle.setAttribute('cy', cy.toFixed(1));
    circle.setAttribute('r', '4');
    circle.setAttribute('fill', fill);
    circle.setAttribute('opacity', '0.9');
    circle.style.cursor = 'pointer';
    circle.style.filter = `drop-shadow(0 0 3px ${fill})`;
    if (isCritical) circle.classList.add('radar-dot-critical');

    // ── Clique abre card de follow-up ────────────────────────────
    const dia = parseDiaFollowup(l.etapa_followup) ?? 0;
    circle.addEventListener('click', () => {
      mostrarAlertaFollowup({
        nome:  l.nome,
        dia,
        plano: l.plano || '—',
        fss:   l.fss   || 0,
        tipo:  dia > 0 ? 'fss' : 'info',
        nid:   null,
      });
    });

    // ── Tooltip neon com dados reais do estágio ───────────────────
    const urgLabel =
      nivel === 'zombie'  ? '☠ ZOMBIE'      :
      nivel === 'gargalo' ? '⚠ GARGALO'     :
      nivel === 'critico' ? '⚠ CRÍTICO'     :
      nivel === 'ambar'   ? '↯ ATENÇÃO'     : '✓ EM DIA';
    const tempoStr = _formatTempo(horas);
    const estagioLabel = estagio || (dia > 0 ? `D.${dia} follow-up` : 'qualificação');

    circle.addEventListener('mouseenter', ev =>
      _showRadarTooltip(ev, l.nome, tempoStr, estagioLabel, urgLabel, fill));
    circle.addEventListener('mousemove',  ev => _moveRadarTooltip(ev));
    circle.addEventListener('mouseleave', _hideRadarTooltip);

    dotsG.appendChild(circle);
  });
}

// Radar principal — todas as leads
function renderRadar(leads) {
  _renderRadarDots(leads, 'radar-dots', 100, 100, 78);
}

// Radar FSS no ELITE — só leads do closer atual
function renderEliteRadar(usuarioId) {
  const leads = usuarioId
    ? _cachedLeads.filter(l => String(l.closer_id) === String(usuarioId))
    : _cachedLeads;
  _renderRadarDots(leads, 'elite-radar-dots', 80, 80, 62);
}

// ── Radar tooltip customizado ─────────────────────────────────
const _rtt = document.getElementById('radar-tooltip');

function _showRadarTooltip(ev, nome, tempoStr, estagio, urgLabel, cor) {
  if (!_rtt) return;
  _rtt.style.borderColor = cor;
  _rtt.innerHTML = '';

  const nomeEl = document.createElement('div');
  nomeEl.className = 'rtt-nome';
  nomeEl.textContent = nome || '—';

  const linhas = [
    `[*] ${tempoStr} no estágio`,
    `[*] ${estagio}`,
    `[*] ${urgLabel}`,
  ];
  linhas.forEach(txt => {
    const l = document.createElement('div');
    l.className = 'rtt-linha';
    l.textContent = txt;
    _rtt.appendChild(l);
  });
  _rtt.insertBefore(nomeEl, _rtt.firstChild);
  _rtt.classList.add('visible');
  _moveRadarTooltip(ev);
}

function _moveRadarTooltip(ev) {
  if (!_rtt) return;
  const x = ev.clientX + 14;
  const y = ev.clientY - 10;
  _rtt.style.left = x + 'px';
  _rtt.style.top  = y + 'px';
}

function _hideRadarTooltip() {
  if (_rtt) _rtt.classList.remove('visible');
}

// ── Assembler overlay — ativa durante processamento Python ────
function _setAssemblerActive(active) {
  const el = document.getElementById('assembler-overlay');
  if (el) el.classList.toggle('active', active);
}

// ── HUD Clock — atualiza a cada segundo ──────────────────────
function _atualizarClock() {
  const el = document.getElementById('hud-clock');
  if (!el) return;
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  el.textContent = `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
}
setInterval(_atualizarClock, 1000);
_atualizarClock();

function badgeClass(s) {
  return ({ ativo: 'green', nova: 'green', quente: 'red', parado: 'amber', inativo: 'muted' })[s] || 'muted';
}

// ── ORÇAMENTOS — Colar nome da lead ──────────────────────────
document.getElementById('btn-paste-lead').addEventListener('click', async () => {
  const input = document.getElementById('input-lead');
  try {
    const text = await window.pywebview.api.obter_clipboard();
    if (text) {
      input.value = text.trim();
      input.focus();
    }
  } catch (e) {
    termLog(`[WARN] clipboard: ${e}`);
  }
});

// ── ORÇAMENTOS — Calcular proposta ────────────────────────────
document.getElementById('btn-calcular').addEventListener('click', calcularProposta);

async function calcularProposta() {
  const nome    = document.getElementById('input-lead').value.trim();
  const titulo  = document.getElementById('select-titulo').value;
  const tipo    = document.getElementById('select-tipo').value;
  const nivel   = document.getElementById('select-nivel').value;
  const plano   = document.getElementById('select-plano').value;
  const paginas = parseInt(document.getElementById('input-paginas').value) || 10;
  const prazo   = document.getElementById('select-prazo').value;
  const desc    = parseFloat(document.getElementById('input-desconto').value) || 0;

  termLog(`[SYS] CALCULANDO — TIPO=${tipo} NÍVEL=${nivel} PLANO=${plano} PRAZO=${prazo}`);

  try {
    const r = await window.pywebview.api.calcular_proposta(
      nome, tipo, nivel, plano, paginas, prazo, desc
    );

    if (r.status === 'erro_prazo') {
      termLog(`[WARN] ${r.mensagem}`);
      document.getElementById('resultado-placeholder').textContent = `// ${r.mensagem}`;
      document.getElementById('resultado-placeholder').style.display = 'block';
      document.getElementById('resultado-wrap').style.display = 'none';
      return;
    }
    if (r.status !== 'ok') {
      termLog(`[ERR] ${r.mensagem || r.status}`);
      return;
    }

    // Exibe resultado
    document.getElementById('resultado-placeholder').style.display = 'none';
    document.getElementById('resultado-wrap').style.display = 'block';
    document.getElementById('resultado-proposta').textContent = r.texto_proposta;

    // Guarda dados para o botão PDF
    _ultimaProposta = { nome: r.lead, titulo, tipo, nivel, plano, paginas, prazo, desconto: desc };

    // Scripts pós-envio prontos para copiar
    _mostrarScriptsPosEnvio(titulo, nome);

    if (r.aviso_desconto) termLog(`[WARN] ${r.aviso_desconto}`);
    termLog(`[OK] PROPOSTA — À VISTA: R$ ${r.total_avista?.toFixed(2)} | LEAD: ${r.lead}`);

  } catch (e) {
    termLog(`[ERR] calcular_proposta: ${e}`);
  }
}

// ── ORÇAMENTOS — Scripts pós-envio ───────────────────────────
function _mostrarScriptsPosEnvio(tituloVal, nomeVal) {
  const generoF  = /^dra\./i.test(tituloVal);
  const doutorx  = generoF ? 'a doutora' : 'o doutor';
  const primeiro = nomeVal.split(' ')[0] || nomeVal;
  const empresa  = window.NEXUS_CLIENT?.name || '[EMPRESA]';

  document.getElementById('script-texto-principal').textContent =
    `${tituloVal} ${primeiro}, acabei de finalizar o seu orçamento exclusivo e já te encaminhei em PDF. Nesse arquivo ${doutorx} vai ver todo o passo a passo da nossa assessoria, os recebíveis, as garantias e também os nossos três planos de elaboração: o Essencial, o Full e o Master. Se tiver qualquer dúvida em relação aos planos, ao suporte ou às condições de pagamento, pode me chamar aqui ou, se preferir, posso te atender por ligação também.`;

  document.getElementById('script-audio').textContent =
    `"${tituloVal} ${primeiro}, aqui é [SEU NOME] da ${empresa}. Acabei de enviar sua proposta para [CURSO] pela [FACULDADE]. Qualquer dúvida, estou à disposição!"`;

  document.getElementById('script-pagamento').textContent =
    'Para pagamentos via pix, você paga somente 50% do valor como entrada, e os outros 50% apenas na entrega do trabalho.';

  document.getElementById('scripts-pos-envio').style.display = 'block';
}

// ── ORÇAMENTOS — Copiar proposta ──────────────────────────────
document.getElementById('btn-copiar').addEventListener('click', () => {
  const texto = document.getElementById('resultado-proposta').textContent;
  if (!texto) return;

  // Fallback compatível com pywebview (clipboard API pode não estar disponível)
  const ta = document.createElement('textarea');
  ta.value = texto;
  ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;width:1px;height:1px;';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  document.execCommand('copy');
  ta.remove();

  const btn = document.getElementById('btn-copiar');
  const original = btn.textContent;
  btn.textContent = '✓ COPIADO';
  btn.style.color = 'var(--neon)';
  setTimeout(() => { btn.textContent = original; }, 2000);
});

// ── ORÇAMENTOS — Copiar scripts pós-envio ────────────────────
document.addEventListener('click', e => {
  const btn = e.target.closest('.btn-copy-script');
  if (!btn) return;
  const texto = document.getElementById(btn.dataset.target)?.textContent || '';
  if (!texto) return;
  const ta = document.createElement('textarea');
  ta.value = texto;
  ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;width:1px;height:1px;';
  document.body.appendChild(ta); ta.focus(); ta.select(); document.execCommand('copy'); ta.remove();
  const orig = btn.textContent;
  btn.textContent = '✓ COPIADO';
  setTimeout(() => { btn.textContent = orig; }, 2000);
});

// ── ORÇAMENTOS — Baixar PDF ───────────────────────────────────
let _ultimaProposta = null; // guarda dados da última proposta calculada

// ═══════════════════════════════════════════════════════════════
// FOLLOW-UP SCRIPTS — Cronograma de 60 dias (guia de referência)
// ═══════════════════════════════════════════════════════════════
const FOLLOWUP_SCRIPTS = {
  0:  { fase: 'Fase 1 — Conexão Inicial', canal: 'WhatsApp · Texto + Áudio', tipo: 'ENVIO DE PROPOSTA',
        script: '[TITULO] [NOME], acabei de finalizar o seu orçamento exclusivo e já te encaminhei em PDF. Nesse arquivo [DOUTORX] vai ver todo o passo a passo da nossa assessoria, os recebíveis, as garantias e também os nossos três planos de elaboração: o Essencial, o Full e o Master. Se tiver qualquer dúvida em relação aos planos, ao suporte ou às condições de pagamento, pode me chamar aqui ou, se preferir, posso te atender por ligação também.\n\n🎙 ÁUDIO:\n"[TITULO] [NOME], aqui é [SEU NOME] da [EMPRESA]. Acabei de enviar sua proposta para [CURSO] pela [FACULDADE]. Qualquer dúvida, estou à disposição!"\n\n💳 PAGAMENTO VIA PIX:\nPara pagamentos via pix, você paga somente 50% do valor como entrada, e os outros 50% apenas na entrega do trabalho.' },
  2:  { fase: 'Fase 1 — Conexão e Urgência', canal: 'WhatsApp · Texto', tipo: 'MENSAGEM DE VALOR',
        script: '"[TITULO] [NOME], a [EMPRESA] já aprovou mais de 3.000 clientes com 98,47% de sucesso. Nosso método foi desenvolvido para garantir sua aprovação com segurança e tranquilidade. Posso te ajudar com alguma dúvida sobre o processo?"' },
  5:  { fase: 'Fase 1 — Conexão e Urgência', canal: 'WhatsApp · Texto', tipo: 'MENSAGEM DE SEGURANÇA',
        script: '"[TITULO] [NOME], quero reforçar que todo o nosso trabalho vem acompanhado de relatório anti-plágio, contrato digital e nota fiscal. Você está em boas mãos. Alguma dúvida que posso esclarecer?"' },
  7:  { fase: 'Fase 1 — Conexão e Urgência', canal: 'WhatsApp · Texto', tipo: 'GATILHO DE URGÊNCIA',
        script: '"[TITULO] [NOME], seu orçamento tem validade de 7 dias e vence hoje. Gostaria de garantir sua vaga no cronograma de 4 semanas (20 dias úteis) para não atrasar sua banca?"' },
  10: { fase: 'Fase 2 — Aproximação Humana', canal: 'Ligação + WhatsApp', tipo: 'LIGAÇÃO 1 + INDICAÇÃO',
        script: 'Ligar para a lead. Apresentar o Programa de Indicação Full:\n\n"[TITULO] [NOME], se [ELA] indicar um colega que fechar, [ELA] ganha 10% de desconto imediato no plano [DELA]. Conhece alguém que também precise?"' },
  14: { fase: 'Fase 2 — Aproximação Humana', canal: 'Ligação', tipo: 'LIGAÇÃO 2 — JORNADA FULL',
        script: 'Focar na tranquilidade da Jornada Full — suporte de correções por até 3 meses.\n\n"[TITULO] [NOME], muitos clientes nos escolhem pela segurança do acompanhamento contínuo. Como está se sentindo em relação ao prazo da banca?"' },
  18: { fase: 'Fase 2 — Aproximação Humana', canal: 'WhatsApp · Áudio ou Texto', tipo: 'DESCONTO ACUMULATIVO',
        script: '"[TITULO] [NOME], sabia que mesmo as indicações que não fecham garantem 1% de desconto acumulativo para [ELA]? São até 10 indicações possíveis! Uma forma de economizar enquanto ajuda colegas."' },
  21: { fase: 'Fase 2 — Aproximação Humana', canal: 'Ligação', tipo: 'LIGAÇÃO 3 — SONDAGEM DE PLANO',
        script: 'Ligar para sondar qual plano melhor se adapta à realidade dela hoje.\n\n"[TITULO] [NOME], pensando bem nos três planos — Essencial, Full e Master — qual faz mais sentido para a sua situação agora?"' },
  30: { fase: 'Fase 3 — Re-engajamento', canal: 'WhatsApp · Texto', tipo: 'OFERTA ESPECIAL 30 DIAS',
        script: '"[TITULO] [NOME], liberamos uma condição especial para quem recebeu orçamento nos últimos 30 dias. Conseguimos baixar o valor original do plano escolhido. Posso te enviar o novo valor?"' },
  55: { fase: 'Fase 4 — Cartada Final', canal: 'Ligação + Mensagem Visual', tipo: 'OFERTA MÁXIMA',
        script: '"[TITULO] [NOME], esta é a nossa melhor condição de 2026. Estou te oferecendo o valor promocional de 30 dias MAIS um upgrade para o Plano Master — tradução, resumo dos artigos e suporte estendido até 180 dias. Válido por apenas 3 dias."' },
  58: { fase: 'Fase 5 — Encerramento', canal: 'WhatsApp · Texto', tipo: 'ÚLTIMO AVISO',
        script: '"[TITULO] [NOME], o upgrade para o Master com desconto encerra em algumas horas. Vamos aproveitar?"' },
  60: { fase: 'Fase 5 — Encerramento', canal: 'WhatsApp · Texto', tipo: 'MENSAGEM DE DESPEDIDA',
        script: '"Entendo que este não é o momento ideal para sua assessoria acadêmica. Para manter nossa organização, estou encerrando seu protocolo de atendimento. Caso precise da [EMPRESA] futuramente, será um prazer atendê-la. Sucesso!"' }
};

function obterScriptFollowup(dia) {
  const dias = Object.keys(FOLLOWUP_SCRIPTS).map(Number).sort((a, b) => a - b);
  let melhor = dias[0];
  for (const d of dias) { if (d <= dia) melhor = d; }
  return FOLLOWUP_SCRIPTS[melhor];
}

// ── Alerta rico de Lead com plano de follow-up ────────────────
function mostrarAlertaFollowup({ nome, dia, plano, fss, tipo, nid }) {
  const container = document.getElementById('notif-container');
  const info = obterScriptFollowup(dia);

  const card = document.createElement('div');
  card.className = 'notif-card ' + (tipo || 'fss');
  card.dataset.nid  = nid  != null ? String(nid)  : '';
  card.dataset.dia  = String(dia);
  card.dataset.nome = nome;

  // Header
  const header = document.createElement('div');
  header.className = 'notif-header';
  const accent = document.createElement('div');
  accent.className = 'notif-accent';
  const titleEl = document.createElement('span');
  titleEl.className = 'notif-title';
  titleEl.textContent = `FOLLOW-UP D.${dia}`;
  const closeBtn = document.createElement('button');
  closeBtn.className = 'notif-close';
  closeBtn.textContent = '✕';
  closeBtn.addEventListener('click', () => card.remove());
  header.append(accent, titleEl, closeBtn);

  // Nome da lead
  const nomeEl = document.createElement('div');
  nomeEl.className = 'notif-lead-nome';
  nomeEl.textContent = nome;

  // Meta
  const body = document.createElement('div');
  body.className = 'notif-body';
  body.textContent = `[*] FSS :: ${fss}/16\n[*] Pacote :: ${plano}\n[*] Ação :: ${info.tipo}\n[*] Canal :: ${info.canal}`;

  const divider = document.createElement('div');
  divider.className = 'notif-divider';

  // Actions
  const actions = document.createElement('div');
  actions.className = 'notif-actions';

  const btnPlano = document.createElement('button');
  btnPlano.className = 'btn-neon';
  btnPlano.style.cssText = 'font-size:7px;padding:6px 10px;';
  btnPlano.textContent = '>>> PLANO';
  btnPlano.addEventListener('click', () => abrirPlanoAcao(dia, nome, nid));

  const btnResolver = document.createElement('button');
  btnResolver.className = 'btn-neon';
  btnResolver.style.cssText = 'font-size:7px;padding:6px 10px;';
  btnResolver.textContent = '✓ RESOLVER';
  btnResolver.addEventListener('click', () => resolverNotif(card));

  const btnAdiar = document.createElement('button');
  btnAdiar.className = 'btn-dim';
  btnAdiar.style.cssText = 'font-size:7px;padding:6px 10px;';
  btnAdiar.textContent = '↻ AMANHÃ';
  btnAdiar.addEventListener('click', () => adiarNotif(card));

  actions.append(btnPlano, btnResolver, btnAdiar);
  card.append(header, nomeEl, body, divider, actions);
  container.appendChild(card);

  setTimeout(() => { if (card.parentNode) card.remove(); }, 15000);
}

// ── Modal de Situação de Qualificação ────────────────────────
function mostrarSituacaoQualif(lead) {
  const existente = document.getElementById('qualif-sit-overlay');
  if (existente) existente.remove();

  const nome     = lead.nome || '—';
  const titulo   = nome.match(/^(Dra?\.|Dr\.)\s*/i)?.[0]?.trim() || '';
  const generoF  = /^dra\./i.test(titulo);
  const primeiro = nome.replace(/^(Dra?\.|Dr\.)\s*/i, '').split(' ')[0];
  const label    = titulo ? `${titulo} ${primeiro}` : primeiro;

  const overlay = document.createElement('div');
  overlay.id = 'qualif-sit-overlay';
  overlay.className = 'plano-overlay';

  const modal = document.createElement('div');
  modal.className = 'plano-modal';

  const header = document.createElement('div');
  header.className = 'plano-header';
  const titleEl = document.createElement('div');
  titleEl.className = 'plano-title';
  titleEl.textContent = `QUALIFICAÇÃO — ${label}`;
  const closeBtn = document.createElement('button');
  closeBtn.className = 'plano-close';
  closeBtn.textContent = '✕';
  closeBtn.addEventListener('click', () => overlay.remove());
  header.append(titleEl, closeBtn);

  const body = document.createElement('div');
  body.className = 'plano-body';

  const instrucao = document.createElement('p');
  instrucao.style.cssText = 'font-size:9px;color:rgba(0,255,65,0.6);margin-bottom:14px;letter-spacing:0.08em;';
  instrucao.textContent = '>>> QUAL É A SITUAÇÃO DESTA LEAD?';
  body.appendChild(instrucao);

  function _btnSit(lbl, desc, cor) {
    const btn = document.createElement('button');
    btn.className = 'btn-neon';
    btn.style.cssText = `width:100%;margin-bottom:8px;border-color:${cor};color:${cor};text-align:left;padding:10px 14px;`;
    const d1 = document.createElement('div'); d1.style.fontSize = '9px'; d1.textContent = lbl;
    const d2 = document.createElement('div'); d2.style.cssText = 'font-size:7px;margin-top:3px;opacity:0.5;'; d2.textContent = desc;
    btn.append(d1, d2);
    return btn;
  }

  // 1 — Esperando proposta → abre ORÇAMENTOS pré-preenchido
  const btnProposta = _btnSit('⚡ ESPERANDO PROPOSTA', 'Orçamento ainda não foi enviado', '#00FF41');
  btnProposta.addEventListener('click', () => {
    overlay.remove();
    document.getElementById('input-lead').value = nome.replace(/^(Dra?\.|Dr\.)\s*/i, '');
    if (titulo) document.getElementById('select-titulo').value = titulo;
    document.querySelectorAll('.overlay-panel').forEach(p => p.classList.remove('open'));
    document.getElementById('overlay-orcamentos').classList.add('open');
  });

  // 2 — Closer não respondeu → alerta vermelho
  const btnCloser = _btnSit('⚠ CLOSER NÃO RESPONDEU', 'Você esqueceu de responder esta lead', '#FF3333');
  btnCloser.addEventListener('click', () => {
    body.innerHTML = '';
    const alerta = document.createElement('div');
    alerta.style.cssText = 'border:1px solid #FF3333;padding:14px;color:#FF3333;font-size:9px;line-height:1.9;white-space:pre-line;';
    alerta.textContent = `⚠ RESPONDA AGORA\n\n${label} está aguardando sua resposta.\nAbra o WhatsApp e retome o atendimento imediatamente.`;
    const btnOk = document.createElement('button');
    btnOk.className = 'btn-neon';
    btnOk.style.cssText = 'margin-top:12px;width:100%;border-color:#FF3333;color:#FF3333;';
    btnOk.textContent = '✓ ENTENDIDO — VOU RESPONDER AGORA';
    btnOk.addEventListener('click', () => overlay.remove());
    body.append(alerta, btnOk);
  });

  // 3 — Cliente não respondeu → script de reativação
  const btnCliente = _btnSit('◈ CLIENTE NÃO RESPONDEU', 'Lead parou de responder — script de reativação', '#FFAA00');
  btnCliente.addEventListener('click', () => {
    const script = `"${titulo} ${primeiro}, tudo bem? Percebi que ficamos sem contato e quero entender se posso te ajudar em algo. Caso tenha surgido alguma dúvida sobre o processo, os planos ou as condições de pagamento, estou aqui. Quando quiser conversar, pode me chamar!"`.trim();
    body.innerHTML = '';
    const pre = document.createElement('pre');
    pre.className = 'plano-script';
    pre.textContent = script;
    const btnCopiar = document.createElement('button');
    btnCopiar.className = 'btn-neon';
    btnCopiar.style.cssText = 'margin-top:8px;width:100%;';
    btnCopiar.textContent = '📋 COPIAR SCRIPT';
    btnCopiar.addEventListener('click', () => {
      navigator.clipboard.writeText(script).catch(() => {
        const ta = document.createElement('textarea');
        ta.value = script; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); ta.remove();
      });
      const orig = btnCopiar.textContent;
      btnCopiar.textContent = '✓ COPIADO';
      setTimeout(() => { btnCopiar.textContent = orig; }, 2000);
    });
    const btnFechar = document.createElement('button');
    btnFechar.className = 'btn-neon';
    btnFechar.style.cssText = 'margin-top:6px;width:100%;';
    btnFechar.textContent = '✕ FECHAR';
    btnFechar.addEventListener('click', () => overlay.remove());
    body.append(pre, btnCopiar, btnFechar);
  });

  body.append(btnProposta, btnCloser, btnCliente);
  modal.append(header, body);
  overlay.appendChild(modal);
  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

// ── Modal de Plano de Ação ────────────────────────────────────
function abrirPlanoAcao(dia, nome, nid) {
  const existente = document.getElementById('plano-modal-overlay');
  if (existente) existente.remove();

  const info = obterScriptFollowup(dia);

  // Detecta título e gênero a partir do nome
  const titulo      = nome.match(/^(Dra?\.|Dr\.)\s*/i)?.[0]?.trim() || '';
  const generoF     = /^dra\./i.test(titulo); // true = feminino, false = masculino
  const primeiroNome = nome.replace(/^(Dra?\.|Dr\.)\s*/i, '').split(' ')[0];

  const scriptFinal = info.script
    .replace(/\[EMPRESA\]/g,  window.NEXUS_CLIENT?.name || '[EMPRESA]')
    .replace(/\[TITULO\]/g,   titulo)
    .replace(/\[NOME\]/g,     primeiroNome)
    .replace(/\[DOUTORX\]/g,  generoF ? 'a doutora' : 'o doutor')
    .replace(/\[ELA\]/g,      generoF ? 'ela'  : 'ele')
    .replace(/\[DELE\]/g,     generoF ? 'dela' : 'dele')
    .replace(/\[DELA\]/g,     generoF ? 'dela' : 'dele')
    .replace(/\[A\b\]/g,      generoF ? 'a'    : 'o')
    .replace(/\[DA\b\]/g,     generoF ? 'da'   : 'do');

  const overlay = document.createElement('div');
  overlay.id = 'plano-modal-overlay';
  overlay.className = 'plano-overlay';

  const modal = document.createElement('div');
  modal.className = 'plano-modal';

  // Header do modal
  const header = document.createElement('div');
  header.className = 'plano-header';
  const titleEl = document.createElement('div');
  titleEl.className = 'plano-title';
  titleEl.textContent = `D.${dia} — ${info.tipo}`;
  const closeBtn = document.createElement('button');
  closeBtn.className = 'notif-close';
  closeBtn.style.cssText = 'font-size:16px;padding:2px 6px;';
  closeBtn.textContent = '✕';
  closeBtn.addEventListener('click', () => overlay.remove());
  header.append(titleEl, closeBtn);

  // Conteúdo
  const content = document.createElement('div');
  content.className = 'plano-content';

  const leadNome = document.createElement('div');
  leadNome.className = 'plano-lead-nome';
  leadNome.textContent = nome;

  const fase = document.createElement('div');
  fase.className = 'plano-fase';
  fase.textContent = info.fase;

  const meta = document.createElement('div');
  meta.className = 'plano-meta-grid';
  const mAcao  = document.createElement('span'); mAcao.textContent  = `[*] AÇÃO :: ${info.tipo}`;
  const mCanal = document.createElement('span'); mCanal.textContent = `[*] CANAL :: ${info.canal}`;
  meta.append(mAcao, mCanal);

  const scriptLabel = document.createElement('div');
  scriptLabel.className = 'plano-script-label';
  scriptLabel.textContent = '>>> SCRIPT SUGERIDO:';

  const scriptBox = document.createElement('div');
  scriptBox.className = 'plano-script';
  scriptBox.textContent = scriptFinal;

  const aviso = document.createElement('div');
  aviso.className = 'plano-aviso';
  aviso.textContent = '[*] Este script é um guia — adapte ao contexto real da lead.';

  // Ações do modal
  const actionsDiv = document.createElement('div');
  actionsDiv.className = 'plano-actions';

  const btnCopiar = document.createElement('button');
  btnCopiar.className = 'btn-neon';
  btnCopiar.style.cssText = 'font-size:7px;';
  btnCopiar.textContent = '📋 COPIAR SCRIPT';
  btnCopiar.addEventListener('click', () => {
    const ta = document.createElement('textarea');
    ta.value = scriptBox.textContent;
    ta.style.cssText = 'position:fixed;opacity:0;top:0;left:0;width:1px;height:1px;';
    document.body.appendChild(ta);
    ta.focus(); ta.select();
    document.execCommand('copy');
    ta.remove();
    btnCopiar.textContent = '✓ COPIADO';
    setTimeout(() => { btnCopiar.textContent = '📋 COPIAR SCRIPT'; }, 2000);
  });

  const btnFechar = document.createElement('button');
  btnFechar.className = 'btn-dim';
  btnFechar.style.cssText = 'font-size:7px;';
  btnFechar.textContent = '✕ FECHAR';
  btnFechar.addEventListener('click', () => overlay.remove());

  actionsDiv.append(btnCopiar, btnFechar);
  content.append(leadNome, fase, meta, scriptLabel, scriptBox, aviso, actionsDiv);
  modal.append(header, content);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
  termLog(`[PLANO] D.${dia} :: ${nome} :: ${info.tipo}`);
}

document.getElementById('btn-pdf').addEventListener('click', async () => {
  if (!_ultimaProposta) return;
  const btn = document.getElementById('btn-pdf');
  btn.textContent = '⏳ GERANDO...';
  btn.disabled = true;
  try {
    const r = await window.pywebview.api.gerar_pdf_proposta(
      _ultimaProposta.nome,
      _ultimaProposta.titulo,
      _ultimaProposta.tipo,
      _ultimaProposta.nivel,
      _ultimaProposta.plano,
      _ultimaProposta.paginas,
      _ultimaProposta.prazo,
      _ultimaProposta.desconto
    );
    if (r.status === 'template_pendente') {
      termLog('[WARN] PDF: template Canva ainda não configurado em assets/template_proposta.pdf');
    } else if (r.status === 'ok') {
      termLog(`[OK] PDF GERADO: ${r.caminho}`);
    } else {
      termLog(`[ERR] PDF: ${r.mensagem}`);
    }
  } catch (e) {
    termLog(`[ERR] gerar_pdf_proposta: ${e}`);
  } finally {
    btn.textContent = '⬇ BAIXAR PDF';
    btn.disabled = false;
  }
});

// ── Boot — aguarda bridge pywebview estar pronta ──────────────
window.addEventListener('pywebviewready', () => {
  termLog('[SYS] INTERFACE CARREGADA — BRIDGE PYWEBVIEW ATIVO');
  window.pywebview.api.carregar_notificacoes_pendentes();
  sincronizar(); // auto-sync pipeline ao abrir
});

// ── Demo visual — dispara apenas em modo browser (sem bridge) ─
// Remove ou comenta este bloco em produção com pywebview
if (typeof window.pywebview === 'undefined') {
  termLog('[SYS] NEXUS CLOSER — MODO BROWSER (DEMO VISUAL)');
  termLog('[SYS] Bridge pywebview não detectada — notificações de exemplo ativas.');

  setTimeout(() => {
    mostrarAlertaFollowup({
      nome: 'Dra. Carla Mendonça',
      dia: 5,
      plano: 'Master',
      fss: 14,
      tipo: 'fss',
      nid: null
    });
  }, 900);

  setTimeout(() => {
    mostrarAlertaFollowup({
      nome: 'Dra. Isabela Rocha',
      dia: 7,
      plano: 'Full',
      fss: 11,
      tipo: 'urgente',
      nid: null
    });
  }, 2400);
}

// ══════════════════════════════════════════════════════════════════════
// PULSE PAGE — Histórico de relatórios Battle Plan / Fechamento
// ══════════════════════════════════════════════════════════════════════

// Dados do relatório atualmente exibido (necessário para exportar PDF via Python)
let _pulseCurrentData = null;

function abrirPulsePage() {
  const page = document.getElementById('pulse-page');
  if (!page) return;
  page.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  _mostrarViewLista();
  _carregarListaRelatorios();
}

function fecharPulsePage() {
  const page = document.getElementById('pulse-page');
  if (!page) return;
  page.style.display = 'none';
  document.body.style.overflow = '';
}

// ── Navegação entre views ─────────────────────────────────────

function _mostrarViewLista() {
  const vl = document.getElementById('pulse-view-list');
  const vd = document.getElementById('pulse-view-detail');
  if (vl) vl.style.display = 'flex';
  if (vd) vd.style.display = 'none';
  _pset('pulse-tipo-label', 'PULSE REPORTS');
  const dt = document.getElementById('pulse-datetime');
  if (dt) dt.textContent = '';
  const btnPdf = document.getElementById('btn-pulse-pdf');
  if (btnPdf) btnPdf.style.display = 'none';
  const footerInfo = document.getElementById('pulse-footer-info');
  if (footerInfo) footerInfo.textContent = 'HISTÓRICO DE RELATÓRIOS';
}

function _mostrarViewDetalhe(data) {
  const vl = document.getElementById('pulse-view-list');
  const vd = document.getElementById('pulse-view-detail');
  if (vl) vl.style.display = 'none';
  if (vd) { vd.style.display = 'flex'; vd.style.flexDirection = 'column'; }
  _pset('pulse-tipo-label', data.tipo || 'PULSE');
  const dt = document.getElementById('pulse-datetime');
  if (dt) dt.textContent = (data.data || '') + ' — ' + (data.horario || '');
  const btnPdf = document.getElementById('btn-pulse-pdf');
  if (btnPdf) btnPdf.style.display = '';
  const footerInfo = document.getElementById('pulse-footer-info');
  if (footerInfo) footerInfo.textContent = 'DADOS SINCRONIZADOS COM CLICKUP';

  // Preenche cabeçalho profissional do PDF
  const vendor = window.NEXUS_CLIENT?.vendor || {};
  const _tipo  = data.tipo || 'PULSE';
  const _data  = data.data || '—';
  const _hora  = data.horario || '—';

  _pset('pdf-vendor-nome',    vendor.nome || 'VENDEDOR');
  _pset('pdf-turno',          _tipo);
  _pset('pdf-data',           _data);
  _pset('pdf-hora',           _hora);
  _pset('pdf-turno-badge',    _tipo.includes('BATTLE') ? 'BATTLE PLAN — MANHÃ' : 'FECHAMENTO — NOITE');
  _pset('pdf-subtitulo',      _tipo + ' — ' + _data + ' às ' + _hora);
  _pset('pdf-data-hora-full', _data + ' às ' + _hora);

  _renderPulsePage(data);
}

// ── Lista de relatórios ───────────────────────────────────────

async function _carregarListaRelatorios() {
  const loading = document.getElementById('pulse-list-loading');
  const list    = document.getElementById('pulse-reports-list');
  if (loading) loading.style.display = 'flex';
  if (list)    list.style.display    = 'none';

  try {
    const items = await window.pywebview.api.listar_relatorios_pulse();
    _renderListaRelatorios(items || []);
  } catch (e) {
    showError('Erro ao listar relatórios', String(e));
    _renderListaRelatorios([]);
  } finally {
    if (loading) loading.style.display = 'none';
    if (list)    list.style.display    = 'flex';
  }
}

function _diaLabel(dataStr) {
  // dataStr: "24/04/2026" → "Qui · 24/04"
  const p = dataStr.split('/');
  if (p.length !== 3) return dataStr;
  const d = new Date(+p[2], +p[1] - 1, +p[0]);
  const dias = ['Dom', 'Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb'];
  return dias[d.getDay()] + ' · ' + p[0] + '/' + p[1];
}

function _semanaLabel(dataStr) {
  // dataStr: "24/04/2026"
  const p = dataStr.split('/');
  if (p.length !== 3) return dataStr;
  const d = new Date(+p[2], +p[1] - 1, +p[0]);
  const day = d.getDay() || 7; // 1=Seg ... 7=Dom
  const seg = new Date(d); seg.setDate(d.getDate() - day + 1);
  const dom = new Date(seg); dom.setDate(seg.getDate() + 6);
  const f = n => String(n).padStart(2, '0');
  return `Semana ${f(seg.getDate())}/${f(seg.getMonth()+1)} — ${f(dom.getDate())}/${f(dom.getMonth()+1)}/${dom.getFullYear()}`;
}

function _mkReportCard(item) {
  const card = document.createElement('div');
  card.className = 'pulse-report-card';
  card.setAttribute('role', 'button');
  card.setAttribute('tabindex', '0');

  const isBattle = (item.tipo || '').includes('BATTLE');
  const turnoEl = document.createElement('span');
  turnoEl.className = 'pulse-report-card-turno ' + (isBattle ? 'turno-battle' : 'turno-fecha');
  turnoEl.textContent = isBattle ? '⚡ BATTLE PLAN' : '🌙 FECHAMENTO';

  const dataEl = document.createElement('span');
  dataEl.className = 'pulse-report-card-data';
  dataEl.textContent = item.data || '—';

  const horaEl = document.createElement('span');
  horaEl.className = 'pulse-report-card-hora';
  horaEl.textContent = item.horario || '—';

  const arrow = document.createElement('span');
  arrow.className = 'pulse-report-card-arrow';
  arrow.textContent = '›';

  card.append(turnoEl, dataEl, horaEl, arrow);

  // Botão excluir — apenas relatórios gerados manualmente pelo closer
  if (item.origem === 'manual') {
    const btnDel = document.createElement('button');
    btnDel.className = 'pulse-report-card-del';
    btnDel.title = 'Excluir relatório e PDF';
    btnDel.textContent = '✕';
    btnDel.addEventListener('click', async e => {
      e.stopPropagation();
      if (!confirm('Excluir este relatório e o PDF gerado?')) return;
      btnDel.textContent = '...';
      btnDel.disabled = true;
      try {
        const r = await window.pywebview.api.deletar_relatorio_pulse(item.id);
        if (r && r.status === 'ok') {
          termLog('[PULSE] Relatório ' + item.id + ' excluído.');
          _carregarListaRelatorios();
        } else {
          showError('Erro ao excluir', r?.mensagem || 'erro desconhecido');
          btnDel.textContent = '✕';
          btnDel.disabled = false;
        }
      } catch (err) {
        showError('Erro ao excluir relatório', String(err));
        btnDel.textContent = '✕';
        btnDel.disabled = false;
      }
    });
    card.appendChild(btnDel);
  }

  const _abrir = async () => {
    const loading = document.getElementById('pulse-detail-loading');
    if (loading) loading.style.display = 'flex';
    _mostrarViewDetalhe({ tipo: item.tipo, data: item.data, horario: item.horario, status: 'ok', stats: {} });
    try {
      const data = await window.pywebview.api.obter_relatorio_pulse_por_id(item.id);
      if (data && data.status !== 'erro') _renderPulsePage(data);
      else showError('Erro ao carregar relatório', data?.mensagem || 'erro desconhecido');
    } catch (e) {
      showError('Erro ao carregar relatório', String(e));
    } finally {
      if (loading) loading.style.display = 'none';
    }
  };
  card.addEventListener('click', _abrir);
  card.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') _abrir(); });
  return card;
}

function _renderListaRelatorios(items) {
  const list = document.getElementById('pulse-reports-list');
  if (!list) return;
  list.innerHTML = '';

  if (items.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'pulse-list-empty';
    empty.textContent = '[—] Nenhum relatório gerado ainda. Clique em ⚡ GERAR AGORA para criar o primeiro.';
    list.appendChild(empty);
    return;
  }

  // Agrupar por semana, depois por dia
  const semanas = {};
  const ordemSem = [];
  items.forEach(item => {
    const sem = _semanaLabel(item.data || '');
    const dia = _diaLabel(item.data || '');
    if (!semanas[sem]) { semanas[sem] = { dias: {}, ordemDia: [] }; ordemSem.push(sem); }
    if (!semanas[sem].dias[dia]) { semanas[sem].dias[dia] = []; semanas[sem].ordemDia.push(dia); }
    semanas[sem].dias[dia].push(item);
  });

  ordemSem.forEach(sem => {
    const hdr = document.createElement('div');
    hdr.className = 'pulse-week-header';
    hdr.textContent = '>>> ' + sem;
    list.appendChild(hdr);

    const g = semanas[sem];
    g.ordemDia.forEach(dia => {
      const dhdr = document.createElement('div');
      dhdr.className = 'pulse-day-header';
      dhdr.textContent = dia;
      list.appendChild(dhdr);
      g.dias[dia].forEach(item => list.appendChild(_mkReportCard(item)));
    });
  });
}

// ── Gerar novo relatório ──────────────────────────────────────

async function _gerarNovoRelatorio() {
  const btn = document.getElementById('btn-pulse-novo');
  if (btn) btn.textContent = '⟳ GERANDO...';
  try {
    const data = await window.pywebview.api.obter_relatorio_pulse();
    if (data && data.status === 'ok') _mostrarViewDetalhe(data);
    else showError('Erro ao gerar relatório', data?.mensagem || 'erro desconhecido');
  } catch (e) {
    showError('Erro ao gerar relatório', String(e));
  } finally {
    if (btn) btn.textContent = '⚡ GERAR AGORA';
  }
}

function _renderPulsePage(d) {
  _pulseCurrentData = d; // Salva para exportação PDF via Python
  // Cabeçalho
  const tipoEl = document.getElementById('pulse-tipo-label');
  const dtEl   = document.getElementById('pulse-datetime');
  const footerH = document.getElementById('pulse-footer-hora');
  if (tipoEl) tipoEl.textContent = d.tipo;
  if (dtEl)   dtEl.textContent   = d.data + ' — ' + d.horario;
  if (footerH) footerH.textContent = d.horario;

  // Stats bar
  const s = d.stats || {};
  _pset('pstat-total',       s.total       ?? 0);
  _pset('pstat-critico',     s.critico     ?? 0);
  _pset('pstat-atencao',     s.atencao     ?? 0);
  _pset('pstat-normal',      s.normal      ?? 0);
  _pset('pstat-sem-estagio', s.sem_estagio ?? 0);
  _pset('pstat-pct',         (s.pct_ok ?? 100) + '%');

  // Cores dinâmicas no pct
  const pctEl = document.getElementById('pstat-pct');
  if (pctEl) {
    const p = s.pct_ok ?? 100;
    pctEl.style.color = p >= 90 ? 'var(--neon)' : p >= 70 ? 'var(--amber)' : 'var(--danger)';
  }

  // Introdução
  _pset('pulse-intro-text', d.intro || '—');

  // Plano de ação (Battle Plan 07h) ou ocultar
  _renderPlanoAcao(d.plano_acao || [], d.tipo);

  // Renderizar seções de leads
  _renderLeadSection('pulse-list-critico',     'pulse-count-critico',     d.critico,     'critico');
  _renderLeadSection('pulse-list-atencao',     'pulse-count-atencao',     d.atencao,     'atencao');
  _renderLeadSection('pulse-list-normal',      'pulse-count-normal',      d.normal,      'normal');
  _renderLeadSection('pulse-list-sem-estagio', 'pulse-count-sem-estagio', d.sem_estagio, 'sem-estagio');

  // Follow-ups
  _renderFollowupSection(d.followups_hoje || []);

  // Concluído hoje (Fechamento)
  _renderFeitoSection(d.atualizadas_hoje || [], d.tipo);

  // Pendências
  _renderPendencias(d);

  // Checklist, Análise, Dicas (Fechamento)
  _renderChecklist(d.checklist || [], d.tipo);
  _renderAnalise(d.analise || {}, d.tipo);
  _renderDicas(d.dicas || [], d.tipo);

  // Conclusão
  _pset('pulse-conclusao-text', d.conclusao || '—');

  // Ocultar seções vazias (exceto CRÍTICO e INTRODUÇÃO — sempre visíveis)
  ['atencao','normal','sem-estagio','followups','feito'].forEach(id => {
    const sec = document.getElementById('pulse-sec-' + id);
    if (!sec) return;
    const lst = sec.querySelector('.pulse-leads-list');
    if (lst && lst.children.length === 0) sec.style.display = 'none';
    else sec.style.display = '';
  });
}

function _pset(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = String(val);
}

function _renderLeadSection(listId, countId, leads, tipo) {
  const list  = document.getElementById(listId);
  const count = document.getElementById(countId);
  if (!list) return;
  if (count) count.textContent = (leads || []).length;
  list.innerHTML = '';

  if (!leads || leads.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'pulse-lead-empty';
    empty.textContent = tipo === 'critico' ? '[✓] Nenhuma lead crítica — pipeline saudável.' : '[—] Nenhuma lead nesta categoria.';
    list.appendChild(empty);
    return;
  }

  leads.forEach(l => {
    const row = document.createElement('div');
    row.className = 'pulse-lead-row pulse-lead-' + tipo;

    const nome = document.createElement('span');
    nome.className = 'pulse-lead-nome';
    nome.textContent = l.nome || '—';

    const estagio = document.createElement('span');
    estagio.className = 'pulse-lead-estagio';
    estagio.textContent = l.estagio || l.board_status || '—';

    const tempo = document.createElement('span');
    tempo.className = 'pulse-lead-tempo';
    tempo.textContent = l.tempo || '—';

    const motivo = document.createElement('span');
    motivo.className = 'pulse-lead-motivo';
    motivo.textContent = l.motivo || '';

    const link = document.createElement('a');
    link.className = 'pulse-lead-link';
    link.textContent = '[VER →]';
    if (l.link) {
      link.href = '#';
      link.addEventListener('click', e => { e.preventDefault(); window.pywebview.api.abrir_link_externo && window.pywebview.api.abrir_link_externo(l.link); });
    }

    row.append(nome, estagio, tempo, motivo, link);
    list.appendChild(row);
  });
}

function _renderFollowupSection(followups) {
  const list  = document.getElementById('pulse-list-fu');
  const count = document.getElementById('pulse-count-fu');
  if (!list) return;
  if (count) count.textContent = followups.length;
  list.innerHTML = '';

  if (followups.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'pulse-lead-empty';
    empty.textContent = '[—] Nenhum follow-up com etapa definida hoje.';
    list.appendChild(empty);
    return;
  }

  followups.forEach(f => {
    const row = document.createElement('div');
    row.className = 'pulse-lead-row pulse-lead-followup';

    const etapa = document.createElement('span');
    etapa.className = 'pulse-fu-etapa';
    etapa.textContent = f.etapa || '—';

    const sep = document.createElement('span');
    sep.className = 'pulse-fu-arrow';
    sep.textContent = '→';

    const nome = document.createElement('span');
    nome.className = 'pulse-lead-nome';
    nome.textContent = f.nome || '—';

    const link = document.createElement('a');
    link.className = 'pulse-lead-link';
    link.textContent = '[VER →]';
    if (f.link) {
      link.href = '#';
      link.addEventListener('click', e => { e.preventDefault(); window.pywebview.api.abrir_link_externo && window.pywebview.api.abrir_link_externo(f.link); });
    }

    row.append(etapa, sep, nome, link);
    list.appendChild(row);
  });
}

function _renderFeitoSection(atualizadas, tipo) {
  const sec   = document.getElementById('pulse-sec-feito');
  const list  = document.getElementById('pulse-list-feito');
  const count = document.getElementById('pulse-count-feito');
  if (!list) return;
  if (count) count.textContent = atualizadas.length;

  // Seção de concluídos só aparece no Fechamento
  if (tipo !== 'FECHAMENTO') {
    if (sec) sec.style.display = 'none';
    return;
  }
  if (sec) sec.style.display = '';

  list.innerHTML = '';
  if (atualizadas.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'pulse-lead-empty';
    empty.textContent = '[—] Nenhuma lead atualizada hoje.';
    list.appendChild(empty);
    return;
  }

  atualizadas.forEach(a => {
    const row = document.createElement('div');
    row.className = 'pulse-lead-row pulse-lead-feito';

    const check = document.createElement('span');
    check.className = 'pulse-check';
    check.textContent = '[✓]';

    const nome = document.createElement('span');
    nome.className = 'pulse-lead-nome';
    nome.textContent = a.nome || '—';

    const estagio = document.createElement('span');
    estagio.className = 'pulse-lead-estagio';
    estagio.textContent = a.estagio || '—';

    row.append(check, nome, estagio);
    list.appendChild(row);
  });
}

function _renderPendencias(d) {
  const list = document.getElementById('pulse-list-pendente');
  if (!list) return;
  list.innerHTML = '';

  const items = [];
  if ((d.critico || []).length > 0)
    items.push(`[!] ${d.critico.length} lead(s) crítica(s) sem atualização — ação imediata`);
  if ((d.atencao || []).length > 0)
    items.push(`[~] ${d.atencao.length} lead(s) em atenção — monitorar hoje`);
  if ((d.sem_estagio || []).length > 0)
    items.push(`[?] ${d.sem_estagio.length} lead(s) sem estágio definido — atualizar no ClickUp`);
  if ((d.followups_hoje || []).length > 0)
    items.push(`[>] ${d.followups_hoje.length} follow-up(s) na sequência 60d — executar hoje`);

  if (items.length === 0) {
    const ok = document.createElement('div');
    ok.className = 'pulse-lead-empty neon-text';
    ok.textContent = '[✓] Pipeline em dia — nenhuma pendência crítica.';
    list.appendChild(ok);
    return;
  }

  items.forEach(txt => {
    const item = document.createElement('div');
    item.className = 'pulse-pendente-item';
    item.textContent = txt;
    list.appendChild(item);
  });
}

// ── Renderiza Plano de Ação (Battle Plan) ───────────────────────
function _renderPlanoAcao(plano, tipo) {
  const sec  = document.getElementById('pulse-sec-plano');
  const list = document.getElementById('pulse-list-plano');
  if (!sec || !list) return;
  const isBattle = (tipo || '').includes('BATTLE');
  sec.style.display = isBattle && plano.length > 0 ? '' : 'none';
  list.innerHTML = '';
  if (!isBattle || plano.length === 0) return;

  plano.forEach(p => {
    const row = document.createElement('div');
    row.className = 'pulse-plano-row';

    const passo = document.createElement('span');
    passo.className = 'pulse-plano-passo';
    passo.textContent = String(p.passo).padStart(2, '0');

    const prioEl = document.createElement('span');
    prioEl.className = 'pulse-plano-prio pulse-plano-prio-' + (p.prioridade || 'NORMAL').toLowerCase().replace('í','i').replace('ç','c').replace('ã','a');
    prioEl.textContent = p.prioridade || '—';

    const nome = document.createElement('span');
    nome.className = 'pulse-plano-lead';
    nome.textContent = p.lead || '—';

    const estagio = document.createElement('span');
    estagio.className = 'pulse-plano-estagio';
    estagio.textContent = p.estagio || '—';

    const tempo = document.createElement('span');
    tempo.className = 'pulse-plano-tempo';
    tempo.textContent = p.tempo || '—';

    const acao = document.createElement('div');
    acao.className = 'pulse-plano-acao';
    acao.textContent = '→ ' + (p.acao || '—');

    const top = document.createElement('div');
    top.className = 'pulse-plano-top';
    top.append(passo, prioEl, nome, estagio, tempo);
    row.append(top, acao);
    list.appendChild(row);
  });
}

// ── Renderiza Checklist (Fechamento) ────────────────────────────
function _renderChecklist(checklist, tipo) {
  const sec  = document.getElementById('pulse-sec-checklist');
  const list = document.getElementById('pulse-list-checklist');
  if (!sec || !list) return;
  const isFecha = (tipo || '') === 'FECHAMENTO';
  sec.style.display = isFecha && checklist.length > 0 ? '' : 'none';
  list.innerHTML = '';
  if (!isFecha || checklist.length === 0) return;

  checklist.forEach(c => {
    const row = document.createElement('div');
    row.className = 'pulse-check-row pulse-check-' + (c.status === 'ok' ? 'ok' : 'pendente');

    const mark = document.createElement('span');
    mark.className = 'pulse-check-mark';
    mark.textContent = c.status === 'ok' ? '[✓]' : '[✗]';

    const item = document.createElement('span');
    item.className = 'pulse-check-item';
    item.textContent = c.item || '—';

    const det = document.createElement('span');
    det.className = 'pulse-check-detalhe';
    det.textContent = c.detalhe || '';

    row.append(mark, item, det);
    list.appendChild(row);
  });
}

// ── Renderiza Análise de Desempenho (Fechamento) ─────────────────
function _renderAnalise(analise, tipo) {
  const sec  = document.getElementById('pulse-sec-analise');
  const body = document.getElementById('pulse-analise-body');
  if (!sec || !body) return;
  const isFecha = (tipo || '') === 'FECHAMENTO';
  sec.style.display = isFecha ? '' : 'none';
  body.innerHTML = '';
  if (!isFecha) return;

  const stats = [
    { lbl: 'Leads atualizadas', val: analise.feito ?? 0 },
    { lbl: 'Pendências',        val: analise.pendente ?? 0 },
    { lbl: 'Total ativas',      val: analise.total_ativo ?? 0 },
    { lbl: 'Taxa de aproveitamento', val: (analise.taxa_atualizacao ?? 0) + '%' },
    { lbl: 'Avaliação do dia',  val: analise.avaliacao || '—' },
  ];
  stats.forEach(s => {
    const row = document.createElement('div');
    row.className = 'pulse-analise-row';
    const lbl = document.createElement('span'); lbl.className = 'pulse-analise-lbl'; lbl.textContent = s.lbl;
    const val = document.createElement('span'); val.className = 'pulse-analise-val'; val.textContent = s.val;
    row.append(lbl, val);
    body.appendChild(row);
  });
}

// ── Renderiza Dicas de Organização (Fechamento) ──────────────────
function _renderDicas(dicas, tipo) {
  const sec  = document.getElementById('pulse-sec-dicas');
  const list = document.getElementById('pulse-list-dicas');
  if (!sec || !list) return;
  const isFecha = (tipo || '') === 'FECHAMENTO';
  sec.style.display = isFecha && dicas.length > 0 ? '' : 'none';
  list.innerHTML = '';
  if (!isFecha || dicas.length === 0) return;

  dicas.forEach(d => {
    const item = document.createElement('div');
    item.className = 'pulse-dica-item';
    item.textContent = '[*] ' + d;
    list.appendChild(item);
  });
}

// ── Export PDF — gerado via PyMuPDF no Python ────────────────
// REGRA INVIOLÁVEL: window.print() em pywebview/WebView2 não captura o
// conteúdo da webview — resulta em PDF em branco. Usar SEMPRE a bridge
// Python (gerar_pdf_pulse) que usa PyMuPDF para gerar o PDF diretamente.
function _showPdfLoading(dados) {
  const tipo  = dados?.tipo  || 'PULSE';
  const data  = dados?.data  || '—';
  const hora  = dados?.horario || '—';
  const s     = dados?.stats  || {};
  const overlay = document.createElement('div');
  overlay.id = 'pdf-loading-overlay';
  overlay.innerHTML = `
    <div class="pdf-load-card">
      <div class="pdf-load-top">NEXUS CLOSER // PDF ENGINE</div>
      <div class="pdf-load-title" id="pdf-load-tipo"></div>
      <div class="pdf-load-meta" id="pdf-load-meta1"></div>
      <div class="pdf-load-meta" id="pdf-load-meta2"></div>
      <div class="pdf-load-bar"><span class="pdf-load-fill" id="pdf-load-fill"></span></div>
      <div class="pdf-load-status" id="pdf-load-status">[*] Compilando relatório...</div>
      <div class="pdf-load-hint">&gt;&gt;&gt; Aguarde. Abrirá automaticamente.</div>
    </div>`;
  overlay.querySelector('#pdf-load-tipo').textContent = tipo;
  overlay.querySelector('#pdf-load-meta1').textContent = data + ' · ' + hora;
  overlay.querySelector('#pdf-load-meta2').textContent = 'Pipeline: ' + (s.total||0) + ' leads  ·  Crítico: ' + (s.critico||0);
  document.body.appendChild(overlay);
  // Simula progresso visual enquanto aguarda
  let pct = 0;
  const fill = document.getElementById('pdf-load-fill');
  const status = document.getElementById('pdf-load-status');
  const msgs = [
    '[*] Compilando relatório...',
    '[*] Montando plano de ação...',
    '[*] Renderizando páginas...',
    '[*] Aplicando fontes...',
    '[*] Finalizando PDF...',
  ];
  let mi = 0;
  const timer = setInterval(() => {
    pct = Math.min(pct + Math.random() * 18, 90);
    if (fill) fill.style.width = pct + '%';
    if (status && mi < msgs.length) { status.textContent = msgs[mi++]; }
  }, 400);
  overlay._stopProgress = () => {
    clearInterval(timer);
    if (fill) fill.style.width = '100%';
    if (status) status.textContent = '[OK] PDF gerado com sucesso.';
    setTimeout(() => overlay.remove(), 900);
  };
  overlay._stopError = (msg) => {
    clearInterval(timer);
    if (fill) fill.style.background = 'var(--danger, #FF3333)';
    if (status) status.textContent = '[ERR] ' + msg;
    setTimeout(() => overlay.remove(), 2500);
  };
  return overlay;
}

async function exportarPulsePdf() {
  const btn = document.getElementById('btn-pulse-pdf');
  if (btn) { btn.textContent = '⟳ GERANDO...'; btn.disabled = true; }
  let overlay = null;
  try {
    // Se não há relatório carregado, busca um novo antes de gerar o PDF
    let dados = _pulseCurrentData;
    if (!dados) {
      termLog('[INFO] Buscando dados do relatório...');
      dados = await window.pywebview.api.obter_relatorio_pulse();
      if (!dados || dados.status !== 'ok') {
        showError('Erro ao buscar dados do relatório', dados?.mensagem || 'erro desconhecido');
        return;
      }
      _pulseCurrentData = dados;
      _renderPulsePage(dados);
    }
    overlay = _showPdfLoading(dados);
    const vendor = window.NEXUS_CLIENT?.vendor || {};
    const r = await window.pywebview.api.gerar_pdf_pulse(
      JSON.stringify(dados),
      vendor.nome  || 'VENDEDOR',
      vendor.cargo || ''
    );
    if (r && r.status === 'ok') {
      overlay?._stopProgress();
      termLog('[OK] PDF gerado: ' + (r.nome || r.path));
    } else {
      const msg = r?.mensagem || 'erro desconhecido';
      overlay?._stopError(msg);
      termLog('[ERR] PDF: ' + msg);
    }
  } catch (e) {
    overlay?._stopError(String(e));
    termLog('[ERR] gerar_pdf_pulse: ' + e);
  } finally {
    if (btn) { btn.textContent = '⬇ EXPORTAR PDF'; btn.disabled = false; }
  }
}

// ── Event listeners da Pulse Page ────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('btn-abrir-pulse')?.addEventListener('click', abrirPulsePage);
  document.getElementById('btn-pulse-fechar')?.addEventListener('click', fecharPulsePage);
  document.getElementById('btn-pulse-novo')?.addEventListener('click', _gerarNovoRelatorio);
  document.getElementById('btn-pulse-pdf')?.addEventListener('click', exportarPulsePdf);
  document.getElementById('btn-pulse-historico')?.addEventListener('click', async () => {
    const btn = document.getElementById('btn-pulse-historico');
    if (btn) { btn.textContent = '⟳ GERANDO...'; btn.disabled = true; }
    try {
      // 1. Cria/atualiza slots desta semana
      const r = await window.pywebview.api.gerar_relatorios_historicos();
      termLog(`[PULSE] ${r?.criados || 0} slot(s) da semana criados.`);
      // 2. Regenera TODOS os relatórios existentes com o formato atual
      const r2 = await window.pywebview.api.atualizar_todos_relatorios();
      termLog(`[PULSE] ${r2?.atualizados || 0} relatório(s) existentes atualizados.`);
      _carregarListaRelatorios();
    } catch (e) { showError('Erro ao atualizar relatórios', String(e)); }
    finally { if (btn) { btn.textContent = '⏳ SEMANA'; btn.disabled = false; } }
  });
  document.getElementById('btn-pulse-back-list')?.addEventListener('click', () => {
    _mostrarViewLista();
    _carregarListaRelatorios();
  });

  // Fechar com Escape
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      const page = document.getElementById('pulse-page');
      if (page && page.style.display !== 'none') fecharPulsePage();
    }
  });
});
