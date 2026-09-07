const app = document.querySelector("#app");
let state = { user: null, bootstrap: null, tab: "dashboard", collapsed: false };
const tabTitles = {
  dashboard: "Visao Geral",
  contacts: "Contatos",
  events: "Acoes e Eventos",
  users: "Equipe",
  referrals: "Indicacoes",
  origins: "Origens",
  goals: "Metas",
  summary: "Resumo do Dia",
  reports: "Relatorios",
  settings: "Configuracoes",
};

const api = async (url, options = {}) => {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    let payload = {};
    try { payload = await res.json(); } catch {}
    const err = new Error(payload.error || "Erro ao processar");
    err.payload = payload;
    err.status = res.status;
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
};

const formData = (form) => {
  const data = {};
  new FormData(form).forEach((value, key) => data[key] = value);
  form.querySelectorAll("input[type=checkbox]").forEach((el) => data[el.name] = el.checked ? 1 : 0);
  return data;
};

const money = (n) => Number(n || 0).toLocaleString("pt-BR");
const percent = (n) => `${Number(n || 0).toLocaleString("pt-BR")}%`;
const todayText = () => new Date().toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

if (location.pathname === "/cadastro") {
  renderPublicSignup();
} else if (location.pathname === "/cadastro/sucesso") {
  renderSignupSuccess();
} else if (location.pathname === "/privacidade") {
  renderPrivacy();
}

document.querySelector("#loginForm")?.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await api("/api/login", { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
    await boot();
  } catch (err) {
    showToast(err.message);
  }
});

async function boot() {
  if (["/cadastro", "/cadastro/sucesso", "/privacidade"].includes(location.pathname)) return;
  const me = await api("/api/me");
  if (!me.user) return;
  state.user = me.user;
  state.bootstrap = await api("/api/bootstrap");
  app.innerHTML = document.querySelector("#crmTemplate").innerHTML;
  bindShell();
  render();
}

function bindShell() {
  document.querySelector("#sidebarUser").textContent = `${state.user.name} - ${state.user.role}`;
  document.querySelector("#logoutBtn").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" });
    location.reload();
  });
  document.querySelector("#copyPublicLink").addEventListener("click", async () => {
    const dashboard = await api("/api/dashboard");
    const link = `${dashboard.publicBaseUrl}/cadastro`;
    try {
      await navigator.clipboard.writeText(link);
      showToast("Link copiado.");
    } catch {
      prompt("Copie o link publico:", link);
    }
  });
  document.querySelector("#collapseSidebar").addEventListener("click", () => {
    state.collapsed = !state.collapsed;
    document.querySelector(".shell").classList.toggle("sidebarCollapsed", state.collapsed);
  });
  document.querySelector("#menuToggle").addEventListener("click", () => document.querySelector(".shell").classList.add("drawerOpen"));
  document.querySelector("#drawerShade").addEventListener("click", () => document.querySelector(".shell").classList.remove("drawerOpen"));
  document.querySelectorAll(".sideNav button").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.tab = btn.dataset.tab;
      document.querySelector(".shell").classList.remove("drawerOpen");
      document.querySelectorAll(".sideNav button").forEach((b) => b.classList.toggle("active", b === btn));
      render();
    });
  });
  document.querySelectorAll("[data-open=contact]").forEach((btn) => btn.addEventListener("click", () => openQuickContactForm()));
  document.querySelector("[data-open=event]").addEventListener("click", () => openEventForm());
}

async function render() {
  document.querySelector("#viewEyebrow").textContent = tabTitles[state.tab] || "CRM";
  document.querySelector(".topbar h1").textContent = state.tab === "dashboard" ? "Painel de comando" : (tabTitles[state.tab] || "CRM");
  document.querySelector("#lastUpdated").textContent = `Atualizado em ${todayText()}`;
  if (state.tab === "dashboard") return renderDashboard();
  if (state.tab === "contacts") return renderContacts();
  if (state.tab === "events") return renderEvents();
  if (state.tab === "referrals") return renderReferrals();
  if (state.tab === "origins") return renderOrigins();
  if (state.tab === "goals") return renderGoals();
  if (state.tab === "summary") return renderSummary();
  if (state.tab === "users") return renderUsers();
  if (state.tab === "reports") return renderReports();
  if (state.tab === "settings") return renderSettings();
}

function showToast(message) {
  const toast = document.querySelector("#toast");
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 1800);
}

function goTab(tab, setup) {
  state.tab = tab;
  document.querySelectorAll(".sideNav button").forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
  render().then(() => setup?.());
}

async function renderPublicSignup() {
  app.innerHTML = document.querySelector("#publicTemplate").innerHTML;
  const options = await api("/api/public-options");
  const params = new URLSearchParams(location.search);
  document.querySelector("#publicRegion").innerHTML = `<option value="">Selecione sua região</option>${optionList(options.regions)}`;
  document.querySelector("#publicSource").innerHTML = `<option value="outros">Selecione</option>${optionList(options.sources)}`;
  ["source", "utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term", "ref", "event"].forEach((key) => {
    const input = document.querySelector(`[name="${key}"]`);
    if (input) input.value = params.get(key) || "";
  });
  if (params.get("ref")) {
    document.querySelector("#referralNotice").hidden = false;
  }
  trackPublic("registration_page_view");
  const phoneInput = document.querySelector("#publicPhone");
  phoneInput.addEventListener("input", () => phoneInput.value = formatBRPhone(phoneInput.value));
  ["publicName", "publicPhone", "publicRegion"].forEach((id) => {
    document.querySelector(`#${id}`).addEventListener("input", () => showPublicMessage(""));
  });
  let started = false;
  document.querySelector("#publicSignupForm").addEventListener("input", () => {
    if (!started) {
      started = true;
      trackPublic("registration_started");
    }
  }, { once: true });
  document.querySelector("#publicSignupForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!validatePublicForm(event.currentTarget)) return;
    const button = event.currentTarget.querySelector("button[type=submit]");
    button.disabled = true;
    button.classList.add("isLoading");
    button.textContent = "Enviando...";
    try {
      const payload = formData(event.currentTarget);
      const result = await api("/api/public-signup", { method: "POST", body: JSON.stringify(payload) });
      sessionStorage.setItem("signupResult", JSON.stringify(result));
      location.href = "/cadastro/sucesso";
    } catch (err) {
      showPublicMessage(err.message || "Não foi possível concluir seu cadastro. Tente novamente.", true);
      button.disabled = false;
      button.classList.remove("isLoading");
      button.textContent = "Quero participar";
    }
  });
}

function renderSignupSuccess() {
  app.innerHTML = document.querySelector("#successTemplate").innerHTML;
  const result = JSON.parse(sessionStorage.getItem("signupResult") || "{}");
  const link = result.referral_link || `${location.origin}/cadastro`;
  document.querySelector("#consentSuccess").textContent = result.communication_consent
    ? "Você poderá receber nossas informações pelo WhatsApp."
    : "Seu cadastro foi recebido. Você pode compartilhar seu link pessoal se quiser convidar outras pessoas.";
  document.querySelector("#personalLink").value = link;
  document.querySelector("#qrCode").src = `https://api.qrserver.com/v1/create-qr-code/?size=190x190&data=${encodeURIComponent(link)}`;
  document.querySelector("#copyReferral").addEventListener("click", async () => {
    await navigator.clipboard.writeText(link);
    document.querySelector("#copyReferral").textContent = "Link copiado";
    trackPublic("share_clicked", { referral_code: result.referral_code || "" });
  });
  document.querySelector("#nativeShare").addEventListener("click", async () => {
    trackPublic("share_clicked", { referral_code: result.referral_code || "" });
    if (navigator.share) {
      await navigator.share({ title: "Participe da rede da Cléa Torres", text: "Cadastre-se para participar da nossa comunidade.", url: link });
    } else {
      await navigator.clipboard.writeText(link);
      showToast("Link copiado.");
    }
  });
  const whatsText = `Participe da rede da Cléa Torres: ${link}`;
  document.querySelector("#whatsappShare").href = `https://wa.me/?text=${encodeURIComponent(whatsText)}`;
  document.querySelector("#whatsappShare").addEventListener("click", () => trackPublic("whatsapp_share_clicked", { referral_code: result.referral_code || "" }));
}

function renderPrivacy() {
  app.innerHTML = document.querySelector("#privacyTemplate").innerHTML;
}

function formatBRPhone(value) {
  const digits = value.replace(/\D/g, "").replace(/^55/, "").slice(0, 11);
  if (digits.length <= 2) return digits;
  if (digits.length <= 6) return `(${digits.slice(0, 2)}) ${digits.slice(2)}`;
  if (digits.length <= 10) return `(${digits.slice(0, 2)}) ${digits.slice(2, 6)}-${digits.slice(6)}`;
  return `(${digits.slice(0, 2)}) ${digits.slice(2, 7)}-${digits.slice(7)}`;
}

function validBRPhone(value) {
  let digits = value.replace(/\D/g, "");
  if (digits.startsWith("55") && [12, 13].includes(digits.length)) digits = digits.slice(2);
  const ddd = Number(digits.slice(0, 2));
  return [10, 11].includes(digits.length) && ddd >= 11 && ddd <= 99 && (digits.length === 10 || digits[2] === "9");
}

function validatePublicForm(form) {
  [form.name, form.phone, form.region_id].forEach((field) => field?.removeAttribute("aria-invalid"));
  if (!form.name.value.trim()) {
    form.name.setAttribute("aria-invalid", "true");
    form.name.focus();
    return showPublicMessage("Informe seu nome.", true);
  }
  if (!validBRPhone(form.phone.value)) {
    form.phone.setAttribute("aria-invalid", "true");
    form.phone.focus();
    return showPublicMessage("Informe um WhatsApp válido com DDD.", true);
  }
  if (!form.region_id.value) {
    form.region_id.setAttribute("aria-invalid", "true");
    form.region_id.focus();
    return showPublicMessage("Selecione sua Região Administrativa.", true);
  }
  return true;
}

function showPublicMessage(message, isError = false) {
  const box = document.querySelector("#publicMessage");
  if (!box) return false;
  box.textContent = message;
  box.classList.toggle("error", Boolean(isError && message));
  box.hidden = !message;
  return false;
}

async function trackPublic(event_name, extra = {}) {
  try {
    const params = new URLSearchParams(location.search);
    await api("/api/public-analytics", {
      method: "POST",
      body: JSON.stringify({
        event_name,
        source: params.get("source") || params.get("utm_source") || "",
        referral_code: params.get("ref") || extra.referral_code || "",
      }),
    });
  } catch {}
}

function metricCard(label, value) {
  const display = typeof value === "number" ? money(value) : value;
  return `<article class="card metric"><span>${label}</span><strong>${display}</strong></article>`;
}

function chart(title, rows, empty = "Ainda nao ha cadastros suficientes para gerar este grafico.") {
  const max = Math.max(1, ...rows.map((r) => Number(r.value || 0)));
  const body = rows.length ? rows.map((r) => `
    <div class="barrow">
      <span>${r.label || "Sem dados para exibir"}</span>
      <div class="bar"><i style="width:${Math.max(3, (Number(r.value || 0) / max) * 100)}%"></i></div>
      <b>${money(r.value)}</b>
    </div>
  `).join("") : `<p class="empty">${empty}</p>`;
  return `<article class="card"><h3>${title}</h3>${body}</article>`;
}

function lineChart(rows) {
  if (!rows.length) return `<article class="card wide"><h3>Evolucao diaria</h3><p class="empty">Os dados aparecerao aqui conforme a operacao comecar.</p></article>`;
  const ordered = [...rows].reverse();
  const max = Math.max(1, ...ordered.map((r) => Number(r.value || 0)));
  const avg = ordered.map((_, i) => {
    const slice = ordered.slice(Math.max(0, i - 6), i + 1);
    return slice.reduce((sum, row) => sum + Number(row.value || 0), 0) / slice.length;
  });
  const points = ordered.map((r, i) => `${(i / Math.max(ordered.length - 1, 1)) * 100},${100 - (Number(r.value || 0) / max) * 86 - 7}`).join(" ");
  const avgPoints = avg.map((v, i) => `${(i / Math.max(avg.length - 1, 1)) * 100},${100 - (v / max) * 86 - 7}`).join(" ");
  return `<article class="card wide"><div class="cardHead"><h3>Evolucao diaria</h3><span>cadastros e media movel</span></div>
    <svg class="lineChart" viewBox="0 0 100 100" preserveAspectRatio="none" aria-label="Grafico de evolucao diaria">
      <polyline class="avgLine" points="${avgPoints}"></polyline>
      <polyline class="mainLine" points="${points}"></polyline>
    </svg>
    <div class="chartLegend"><span>Cadastros/dia</span><span>Media movel 7 dias</span></div>
  </article>`;
}

function progress(label, value, total) {
  const pct = Math.round((Number(value || 0) / Math.max(Number(total || 0), 1)) * 100);
  return `<div class="progressRow"><span>${label}</span><b>${money(value)} <small>${pct}%</small></b><div><i style="width:${pct}%"></i></div></div>`;
}

async function renderDashboard() {
  const [{ cards, charts, mainGoal, attention, acquisition }, { alerts }] = await Promise.all([api("/api/dashboard"), api("/api/alerts")]);
  const empty = !cards.contactsTotal && !cards.events && !mainGoal && !cards.pageViews;
  const attentionItems = [
    ["Contatos sem responsavel", attention.withoutResponsible, "critico", "CRITICO", "Ver contatos", () => goTab("contacts", () => document.querySelector("#responsible").value = "")],
    ["Retornos vencidos", attention.overdueReturns, "critico", "CRITICO", "Ver pendencias", () => goTab("contacts")],
    ["Acoes sem resultado registrado", attention.eventsWithoutReport, "atencao", "ATENCAO", "Abrir acoes", () => goTab("events")],
    ["Duplicidades suspeitas", attention.suspectedDuplicates, "atencao", "ATENCAO", "Ver relatorios", () => goTab("reports")],
    ["Sem RA", attention.withoutRegion, "info", "INFORMATIVO", "Ver contatos", () => goTab("contacts")],
    ["Sem origem clara", attention.withoutSource, "info", "INFORMATIVO", "Ver origens", () => goTab("origins")],
  ].filter((item) => item[1] > 0).slice(0, 5);
  window.__attentionActions = attentionItems.map((item) => item[5]);
  document.querySelector("#view").innerHTML = `
    ${empty ? `<section class="card startHere"><h2>Comece por aqui</h2><ol><li>Configure a campanha</li><li>Copie o link publico</li><li>Crie a primeira acao</li><li>Convide a equipe</li><li>Acompanhe os primeiros cadastros</li></ol></section>` : ""}
    <section class="card attention"><div><h2>Precisa de atencao hoje</h2><p class="muted">Pendencias operacionais mais importantes.</p></div>
      <div class="attentionList">${attentionItems.length ? attentionItems.map(([label, value, level, priority, action], index) => `<article class="${level}"><small>${priority}</small><b>${money(value)}</b><span>${label}</span><button data-attention="${index}">${action}</button></article>`).join("") : `<p class="empty">Sem pendencias criticas agora.</p>`}</div>
    </section>
    <section class="card rhythm ${mainGoal?.status === "ATRASADO" ? "dangerTone" : mainGoal?.status === "ATENCAO" ? "warnTone" : "okTone"}">
      <div><p class="eyebrow">Ritmo da campanha</p><h2>${mainGoal ? mainGoal.status : "Meta principal nao configurada"}</h2><p class="muted">${mainGoal ? `${mainGoal.name}. ${mainGoal.rule}` : "Configure uma meta operacional para acompanhar o ritmo da campanha."}</p>${mainGoal ? "" : `<button class="primary" id="configureGoal">Configurar meta</button>`}</div>
      ${mainGoal ? `<div class="rhythmGrid">
        <span>Meta <b>${money(mainGoal?.target)}</b></span>
        <span>Realizado <b>${money(mainGoal?.realized)}</b></span>
        <span>Faltam <b>${money(mainGoal?.remaining)}</b></span>
        <span>Dias restantes <b>${mainGoal?.periodClosed ? "Periodo encerrado" : money(mainGoal?.daysRemaining)}</b></span>
        <span>Media necessaria <b>${money(mainGoal?.neededPerDay)}/dia</b></span>
        <span>Media 7 dias <b>${money(mainGoal?.average7)}/dia</b><small>${cards.averageDaysConsidered} dia(s) considerado(s)</small></span>
        <span>Diferenca <b>${money(mainGoal?.difference)}/dia</b></span>
      </div>` : ""}
    </section>
    <section class="grid cards commandCards">
      ${metricCard("Base cadastrada", cards.contactsTotal)}
      ${metricCard("Novos hoje", cards.contactsToday)}
      ${metricCard("Ultimos 7 dias", cards.contacts7)}
      ${metricCard("Media/dia", cards.dailyAverage7)}
      ${metricCard("Cadastros por indicacao", cards.referrals)}
      ${metricCard("% por indicacao", percent(cards.referralBasePercent))}
    </section>
    <section class="grid charts commandGrid">
      ${lineChart(charts.daily)}
      <article class="card"><h3>Aquisicao</h3>
        ${progress("Organicos", acquisition.organic, cards.contactsTotal)}
        ${progress("Por indicacao", acquisition.referral, cards.contactsTotal)}
        ${progress("Por eventos", acquisition.event, cards.contactsTotal)}
        ${progress("Outras origens", acquisition.other, cards.contactsTotal)}
        <p class="muted">${percent(acquisition.referralPercent)} da base veio por indicacao.</p>
      </article>
      <article class="card"><h3>Participacao da base</h3>
        ${progress("WhatsApp autorizado", cards.whatsappConsent, cards.contactsTotal)}
        ${progress("Voluntariado", cards.volunteerInterest, cards.contactsTotal)}
        ${progress("Eventos", cards.eventInterest, cards.contactsTotal)}
        ${progress("Mobilizacao", cards.mobilizerInterest, cards.contactsTotal)}
        ${progress("Apoio declarado voluntariamente", cards.support, cards.contactsTotal)}
      </article>
      ${chart("Origem de aquisicao", charts.sources, "Ainda nao existem dados suficientes.")}
      ${chart("Top 5 RAs por cadastros", charts.regions, "As regioes aparecerao conforme os cadastros chegarem.")}
      ${chart("5 RAs com menor cobertura operacional", charts.regionsLow, "Ainda nao ha cobertura regional suficiente para comparar.")}
      ${chart("Funil publico", charts.publicFunnel)}
      ${chart("Multiplicadores", charts.multipliers, "Ainda nao ha indicacoes suficientes para destacar multiplicadores.")}
      <article class="card"><h3>Alertas de gestao</h3>
        <div class="list">${alerts.length ? alerts.map((a) => `<div class="panel alert ${a.level}"><b>${a.category}</b><span>${a.message}</span></div>`).join("") : `<p class="empty">Sem alertas operacionais agora.</p>`}</div>
      </article>
    </section>
  `;
  document.querySelectorAll("[data-attention]").forEach((btn) => btn.addEventListener("click", () => window.__attentionActions?.[Number(btn.dataset.attention)]?.()));
  document.querySelector("#configureGoal")?.addEventListener("click", () => goTab("goals", () => document.querySelector("#newGoal")?.click()));
}

function optionList(items, selected, label = "name") {
  return items.map((item) => `<option value="${item.id ?? item}" ${String(selected || "") === String(item.id ?? item) ? "selected" : ""}>${item[label] ?? item}</option>`).join("");
}

async function renderContacts() {
  const view = document.querySelector("#view");
  view.innerHTML = `
    <section class="toolbar">
      <input id="q" placeholder="Buscar nome, telefone, bairro ou RA">
      <select id="status"><option value="">Status</option>${optionList(state.bootstrap.statuses)}</select>
      <select id="region"><option value="">Regiao</option>${optionList(state.bootstrap.regions)}</select>
      <select id="source"><option value="">Origem</option>${optionList(state.bootstrap.sources)}</select>
      <select id="responsible"><option value="">Responsavel</option>${optionList(state.bootstrap.users)}</select>
      <select id="interest"><option value="">Interesse</option><option value="whatsapp_consent">WhatsApp autorizado</option><option value="volunteer">Voluntarios</option><option value="event_interest">Eventos</option><option value="mobilizer">Mobilizadores</option><option value="declared_support">Apoio declarado</option></select>
      <button id="filterBtn">Filtrar</button>
    </section>
    <section id="contactList"></section>
  `;
  document.querySelector("#filterBtn").addEventListener("click", loadContacts);
  document.querySelector("#q").addEventListener("keydown", (e) => { if (e.key === "Enter") loadContacts(); });
  await loadContacts();
}

async function loadContacts() {
  const params = new URLSearchParams();
  ["q", "status", "region", "source", "responsible"].forEach((id) => {
    const el = document.querySelector(`#${id}`);
    if (el?.value) params.set(id, el.value);
  });
  const interest = document.querySelector("#interest")?.value;
  if (interest) params.set(interest, "1");
  const { contacts } = await api(`/api/contacts?${params}`);
  document.querySelector("#contactList").innerHTML = contacts.length ? `
    <div class="tableWrap card">
      <table class="dataTable">
        <thead><tr><th>Nome</th><th>WhatsApp</th><th>RA</th><th>Origem</th><th>Entrada</th><th>Participacao</th><th>Indicacoes</th><th>Responsavel</th><th>Proxima acao</th><th>Status</th><th></th></tr></thead>
        <tbody>${contacts.map((c) => `<tr>
          <td><b>${c.name}</b><small>${c.neighborhood || ""}</small></td>
          <td>${c.whatsapp || c.phone}</td>
          <td>${c.region_name || "Sem RA"}</td>
          <td>${c.source || "nao informada"}</td>
          <td>${(c.created_at || "").slice(0, 10)}</td>
          <td><span class="miniTags">${c.communication_consent || c.consent ? "<i>WA</i>" : ""}${c.volunteer_interest || c.is_volunteer ? "<i>VOL</i>" : ""}${c.event_interest ? "<i>EV</i>" : ""}${c.mobilizer_interest ? "<i>MOB</i>" : ""}${c.declared_support ? "<i>APOIO</i>" : ""}</span></td>
          <td>${c.referral_count || 0}</td>
          <td>${c.responsible_name || "Sem responsavel"}</td>
          <td>${c.next_action || "-"}</td>
          <td><span class="pill">${c.status}</span></td>
          <td><button data-view-contact="${c.id}">Abrir</button></td>
        </tr>`).join("")}</tbody>
      </table>
    </div>
  ` : `<article class="card empty">Nenhum contato encontrado.</article>`;
  document.querySelectorAll("[data-view-contact]").forEach((btn) => btn.addEventListener("click", () => openContactDetail(btn.dataset.viewContact)));
}

async function openContactDetail(id) {
  const { contact, history, referrals } = await api(`/api/contacts/${id}`);
  const referralLink = contact.referral_code ? `${location.origin}/cadastro?ref=${contact.referral_code}` : "";
  const classifications = [
    contact.is_community_leader ? "Lideranca comunitaria" : "",
    contact.is_building_manager ? "Sindico(a)" : "",
    contact.is_merchant ? "Comerciante" : "",
    contact.is_association_rep ? "Associacao" : "",
    contact.is_multiplier ? "Multiplicador" : "",
  ].filter(Boolean);
  openModal(`Contato`, `
    <div class="grid">
      <article class="card wide">
        <h3>${esc(contact.name)}</h3>
        <div class="quickActions">
          <button data-quick-contact="interaction">Registrar interacao</button>
          <button data-quick-contact="task">Criar proxima acao</button>
          <button class="primary" id="editContact">Editar</button>
          <button data-quick-contact="noContact">Marcar nao contatar</button>
        </div>
      </article>
      <article class="card"><h3>Resumo</h3>
        <div class="detailList">
          <div><span>WhatsApp / telefone</span><b>${esc(contact.whatsapp || contact.phone)}</b></div>
          <div><span>RA</span><b>${esc(contact.region_name || "Sem RA")}</b></div>
          <div><span>Bairro / quadra</span><b>${esc(contact.neighborhood || "-")}</b></div>
          <div><span>Origem</span><b>${esc(contact.source || "Nao informada")}</b></div>
          <div><span>Responsavel</span><b>${esc(contact.responsible_name || "Sem responsavel")}</b></div>
          <div><span>Status</span><b><span class="pill">${esc(contact.status)}</span></b></div>
        </div>
      </article>
      <article class="card"><h3>Participacao</h3>
        <div class="participationGrid">
          ${yesNo("WhatsApp", contact.communication_consent || contact.consent)}
          ${yesNo("Interesse voluntariado", contact.volunteer_interest)}
          ${yesNo("Voluntario ativo", contact.is_volunteer)}
          ${yesNo("Interesse eventos", contact.event_interest)}
          ${yesNo("Interesse mobilizacao", contact.mobilizer_interest)}
          ${yesNo("Apoio declarado voluntariamente", contact.declared_support)}
        </div>
      </article>
      <article class="card"><h3>Classificacoes</h3>
        ${classifications.length ? `<div class="tagList">${classifications.map((item) => `<span>${esc(item)}</span>`).join("")}</div>` : `<p class="muted">Sem classificacoes operacionais.</p>`}
        ${classifications.length || contact.acting_region ? `<div class="detailList"><div><span>Regiao de atuacao</span><b>${esc(contact.acting_region || "-")}</b></div></div>` : ""}
        <button id="addClassification">+ Adicionar classificacao</button>
      </article>
      <article class="card"><h3>Indicacoes</h3>
        <div class="detailList">
          <div><span>Quem indicou</span><b>${esc(contact.referred_by_name || "-")}</b></div>
          <div><span>Pessoas indicadas</span><b>${money(referrals.length)}</b></div>
          <div><span>Link</span><b>${referralLink ? `<input class="inlineInput" readonly value="${esc(referralLink)}">` : "-"}</b></div>
        </div>
        ${referralLink ? `<img class="miniQr" src="https://api.qrserver.com/v1/create-qr-code/?size=120x120&data=${encodeURIComponent(referralLink)}" alt="QR Code do link de indicacao">` : ""}
        ${referrals.length ? referrals.map((r) => `<p>${esc(r.name)} <span class="pill">${esc(r.status)}</span></p>`).join("") : `<p class="muted">Sem indicacoes registradas.</p>`}
      </article>
      <article class="card"><h3>Acompanhamento</h3>
        <div class="detailList">
          <div><span>Proxima acao</span><b>${esc(contact.next_action || "-")}</b></div>
          <div><span>Tipo</span><b>${esc(contact.next_action_type || "-")}</b></div>
          <div><span>Data</span><b>${esc(contact.next_action_date || "-")}</b></div>
          <div><span>Status</span><b>${esc(contact.next_action_status || "Pendente")}</b></div>
          <div><span>Responsavel</span><b>${esc(contact.responsible_name || "Sem responsavel")}</b></div>
        </div>
      </article>
      <article class="card"><h3>Historico</h3><div class="timeline">
        ${history.map((h) => `<div><b>${esc(h.action)}</b><small>${esc(h.created_at)} - ${esc(h.user_name || "sistema")}</small><p>${h.old_status && h.old_status !== h.new_status ? `${esc(h.old_status)} -> ${esc(h.new_status)}` : esc(h.new_status || "")}</p></div>`).join("")}
      </div></article>
      <article class="card wide"><h3>Observacoes</h3>
        <p class="muted">${esc(contact.notes || "Sem observacoes.")}</p>
      </article>
    </div>
  `);
  document.querySelector("#editContact").addEventListener("click", () => openContactForm(contact));
  document.querySelector("#addClassification").addEventListener("click", () => openContactForm(contact));
  document.querySelectorAll("[data-quick-contact]").forEach((btn) => btn.addEventListener("click", () => {
    const mode = btn.dataset.quickContact;
    const patch = { ...contact };
    if (mode === "interaction") {
      patch.last_contact_date = new Date().toISOString().slice(0, 10);
      patch.notes = `${contact.notes || ""}\nContato registrado em ${new Date().toLocaleDateString("pt-BR")}`.trim();
    }
    if (mode === "task") patch.next_action_status = "Pendente";
    if (mode === "noContact") patch.status = "Nao contatar";
    openContactForm(patch);
  }));
}

function yesNo(label, value) {
  return `<div><span>${label}</span><b class="${value ? "yes" : "no"}">${value ? "SIM" : "NAO"}</b></div>`;
}

function quickContactForm() {
  const b = state.bootstrap;
  return `
    <form id="quickContactForm" class="quickContactForm">
      <div class="formgrid">
        <label>Nome *<input name="name" required autocomplete="name"></label>
        <label>WhatsApp / Telefone *<input name="phone" id="quickPhone" inputmode="tel" autocomplete="tel" required placeholder="(61) 99999-9999"></label>
        <label>Regiao Administrativa *<select name="region_id" required><option value="">Selecione</option>${optionList(b.regions)}</select></label>
        <label>Bairro / Quadra<input name="neighborhood" placeholder="Ex.: Asa Norte, SQN 312"></label>
        <label>Origem *<select name="source" id="quickSource" required><option value="">Selecione</option>${optionList(b.sources)}</select></label>
        <label>Responsavel<select name="responsible_user_id"><option value="">Sem responsavel</option>${optionList(b.users, state.user.id)}</select></label>
        <label class="full conditionalField" id="referrerField" hidden>Quem indicou?
          <input id="referrerSearch" list="referrerOptions" placeholder="Buscar por nome ou telefone">
          <input type="hidden" name="referred_by_contact_id" id="referrerId">
          <datalist id="referrerOptions"></datalist>
        </label>
        <label class="full conditionalField" id="eventOriginField" hidden>Evento de origem<select name="origin_event_id"><option value="">Selecione o evento</option>${optionList(b.events)}</select></label>
        <label class="full conditionalField" id="otherOriginField" hidden>Informe a origem<input name="other_source" placeholder="Ex.: reunião local, ligação recebida"></label>
      </div>
      <section class="quickParticipation">
        <h3>Como quer participar?</h3>
        <div class="checks compactChecks">
          <label><input type="checkbox" name="communication_consent"> Receber comunicacao pelo WhatsApp</label>
          <label><input type="checkbox" name="volunteer_interest"> Interesse em voluntariado</label>
          <label><input type="checkbox" name="event_interest"> Interesse em eventos e acoes</label>
          <label><input type="checkbox" name="mobilizer_interest"> Interesse em mobilizacao</label>
          <label><input type="checkbox" name="declared_support"> Apoio declarado voluntariamente</label>
        </div>
      </section>
      <label>Observacao<textarea name="notes" placeholder="Opcional"></textarea></label>
      <div class="stickySubmit"><button class="primary full" type="submit">Salvar contato</button></div>
    </form>
  `;
}

function bindQuickContactForm() {
  const form = document.querySelector("#quickContactForm");
  const phoneInput = document.querySelector("#quickPhone");
  const source = document.querySelector("#quickSource");
  const referrerSearch = document.querySelector("#referrerSearch");
  const referrerId = document.querySelector("#referrerId");
  let referrerMap = new Map();
  phoneInput.addEventListener("input", () => phoneInput.value = formatBRPhone(phoneInput.value));
  const syncSourceFields = () => {
    const value = source.value;
    document.querySelector("#referrerField").hidden = value !== "Indicacao";
    document.querySelector("#eventOriginField").hidden = value !== "Evento/Acao";
    document.querySelector("#otherOriginField").hidden = value !== "Outro";
  };
  source.addEventListener("change", syncSourceFields);
  referrerSearch.addEventListener("input", async () => {
    referrerId.value = "";
    const q = referrerSearch.value.trim();
    if (q.length < 2) return;
    const { contacts } = await api(`/api/contacts?q=${encodeURIComponent(q)}`);
    referrerMap = new Map(contacts.slice(0, 8).map((c) => [`${c.name} - ${c.phone}`, c.id]));
    document.querySelector("#referrerOptions").innerHTML = [...referrerMap.keys()].map((label) => `<option value="${esc(label)}"></option>`).join("");
  });
  referrerSearch.addEventListener("change", () => {
    referrerId.value = referrerMap.get(referrerSearch.value) || "";
  });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = "Salvando...";
    try {
      const payload = formData(form);
      if (payload.source === "Outro" && payload.other_source) payload.source = payload.other_source;
      if (payload.source !== "Indicacao") payload.referred_by_contact_id = "";
      if (payload.source !== "Evento/Acao") payload.origin_event_id = "";
      const result = await api("/api/contacts", { method: "POST", body: JSON.stringify(payload) });
      showToast("Contato cadastrado com sucesso.");
      showSavedContactActions(result.id);
    } catch (err) {
      button.disabled = false;
      button.textContent = "Salvar contato";
      if (err.status === 409) showToast(`Telefone ja cadastrado em: ${err.payload.duplicate.name}.`);
      else showToast("Erro ao salvar. Tente novamente.");
    }
  });
}

function openQuickContactForm() {
  openModal("Novo contato rapido", quickContactForm());
  bindQuickContactForm();
}

function showSavedContactActions(contactId) {
  const modal = document.querySelector("#modal");
  modal.innerHTML = `<div class="modalHead"><h2>Contato cadastrado</h2><button id="closeModal">Fechar</button></div>
    <div class="modalBody savedContact"><p>O contato entrou na base. Agora voce pode fechar ou abrir a ficha completa para classificar e acompanhar.</p>
      <div class="quickActions"><button id="finishQuick">Fechar</button><button class="primary" id="openSavedContact">Abrir ficha</button></div>
    </div>`;
  document.querySelector("#closeModal").addEventListener("click", closeModal);
  document.querySelector("#finishQuick").addEventListener("click", async () => {
    closeModal();
    state.bootstrap = await api("/api/bootstrap");
    render();
  });
  document.querySelector("#openSavedContact").addEventListener("click", async () => {
    state.bootstrap = await api("/api/bootstrap");
    closeModal();
    render();
    openContactDetail(contactId);
  });
}

function contactForm(contact = {}) {
  const b = state.bootstrap;
  return `
    <form id="contactForm" class="formgrid">
      <input type="hidden" name="id" value="${contact.id || ""}">
      <label>Nome<input name="name" value="${contact.name || ""}" required></label>
      <label>Telefone<input name="phone" value="${contact.phone || ""}" inputmode="tel" required></label>
      <label>WhatsApp<input name="whatsapp" value="${contact.whatsapp || ""}" inputmode="tel"></label>
      <label>Regiao<select name="region_id"><option value="">Selecione</option>${optionList(b.regions, contact.region_id)}</select></label>
      <label>Bairro/quadra<input name="neighborhood" value="${contact.neighborhood || ""}"></label>
      <label>Origem<select name="source">${optionList(b.sources, contact.source)}</select></label>
      <label>Primeiro contato<input name="first_contact_date" type="date" value="${(contact.first_contact_date || new Date().toISOString()).slice(0,10)}"></label>
      <label>Responsavel<select name="responsible_user_id"><option value="">Selecione</option>${optionList(b.users, contact.responsible_user_id || state.user.id)}</select></label>
      <label>Quem indicou<select name="referred_by_contact_id"><option value="">Nao informado</option></select></label>
      <label>Evento de origem<select name="origin_event_id"><option value="">Nenhum</option>${optionList(b.events, contact.origin_event_id)}</select></label>
      <label>Status<select name="status">${optionList(b.statuses, contact.status || "Novo")}</select></label>
      <label>Ultimo contato<input name="last_contact_date" type="date" value="${contact.last_contact_date || ""}"></label>
      <label>Tipo da proxima acao<select name="next_action_type"><option value="">Selecione</option>${optionList(["Ligacao", "WhatsApp", "Reuniao", "Retorno", "Acompanhamento"], contact.next_action_type)}</select></label>
      <label>Status da pendencia<select name="next_action_status">${optionList(["Pendente", "Concluida", "Cancelada", "Vencida"], contact.next_action_status || "Pendente")}</select></label>
      <label>Proxima acao<input name="next_action" value="${contact.next_action || ""}" placeholder="Ex.: confirmar presenca na reuniao"></label>
      <label>Data da proxima acao<input name="next_action_date" type="date" value="${contact.next_action_date || ""}"></label>
      <label>Regiao de atuacao<input name="acting_region" value="${contact.acting_region || ""}"></label>
      <div class="full checks">
        <label><input type="checkbox" name="communication_consent" ${contact.communication_consent || contact.consent ? "checked" : ""}> WhatsApp autorizado</label>
        <label><input type="checkbox" name="is_volunteer" ${contact.is_volunteer ? "checked" : ""}> voluntario ativo</label>
        <label><input type="checkbox" name="volunteer_interest" ${contact.volunteer_interest ? "checked" : ""}> interesse voluntariado</label>
        <label><input type="checkbox" name="event_interest" ${contact.event_interest ? "checked" : ""}> interesse em eventos</label>
        <label><input type="checkbox" name="mobilizer_interest" ${contact.mobilizer_interest ? "checked" : ""}> mobilizador</label>
        <label><input type="checkbox" name="declared_support" ${contact.declared_support ? "checked" : ""}> apoio declarado</label>
        <label><input type="checkbox" name="is_community_leader" ${contact.is_community_leader ? "checked" : ""}> lideranca comunitaria</label>
        <label><input type="checkbox" name="is_building_manager" ${contact.is_building_manager ? "checked" : ""}> sindico</label>
        <label><input type="checkbox" name="is_merchant" ${contact.is_merchant ? "checked" : ""}> comerciante</label>
        <label><input type="checkbox" name="is_association_rep" ${contact.is_association_rep ? "checked" : ""}> associacao</label>
        <label><input type="checkbox" name="is_multiplier" ${contact.is_multiplier ? "checked" : ""}> multiplicador</label>
      </div>
      <label class="full">Observacoes<textarea name="notes">${contact.notes || ""}</textarea></label>
      <button class="primary full" type="submit">Salvar contato</button>
    </form>
    <p class="hint">O sistema verifica telefone repetido antes de salvar e registra historico de status automaticamente.</p>
  `;
}

function openContactForm(contact = {}) {
  openModal(contact.id ? "Ficha completa do contato" : "Novo contato rapido", contactForm(contact));
  document.querySelector("#contactForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/contacts", { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
      closeModal();
      state.bootstrap = await api("/api/bootstrap");
      showToast("Contato salvo");
      render();
    } catch (err) {
      if (err.status === 409) showToast(`Telefone ja cadastrado em: ${err.payload.duplicate.name}.`);
      else showToast("Erro ao salvar. Tente novamente.");
    }
  });
}

async function renderEvents() {
  const { events } = await api("/api/events");
  document.querySelector("#view").innerHTML = `<section class="list">
    ${events.length ? events.map((e) => `<article class="card row">
      <div><b>${esc(e.name)}</b><small>${esc(e.type)}</small></div>
      <div>${esc(e.event_date)} ${esc(e.event_time || "")}<small>${esc(e.location || "")}</small></div>
      <div>${esc(e.region_name || "Sem regiao")}<small>${esc(e.responsible_name || "")}</small></div>
      <div>${money(e.contact_count)} cadastros<small>${money(e.volunteer_count)} voluntarios | ${money(e.mobilizer_count)} mobilizadores</small></div>
      <span class="pill">${eventStatus(e)}</span>
    </article>`).join("") : `<article class="card empty"><h3>Nenhuma acao cadastrada</h3><p>Crie sua primeira acao para comecar a acompanhar resultados.</p><button class="primary" data-empty-event>+ Nova acao</button></article>`}
  </section>`;
  document.querySelector("[data-empty-event]")?.addEventListener("click", openEventForm);
}

function eventStatus(event) {
  const today = new Date().toISOString().slice(0, 10);
  if (event.event_date > today) return "Planejada";
  if (Number(event.contact_count || 0) === 0) return "Relatorio pendente";
  return "Realizada";
}

function openEventForm() {
  const b = state.bootstrap;
  openModal("Nova acao", `
    <form id="eventForm" class="formgrid">
      <label class="full">Nome da acao<input name="name" required></label>
      <label>Tipo<select name="type">${optionList(b.eventTypes)}</select></label>
      <label>Data<input name="event_date" type="date" required value="${new Date().toISOString().slice(0,10)}"></label>
      <label>Horario<input name="event_time" type="time"></label>
      <label>Regiao<select name="region_id"><option value="">Selecione</option>${optionList(b.regions)}</select></label>
      <label>Responsavel<select name="responsible_user_id">${optionList(b.users, state.user.id)}</select></label>
      <label class="full">Local<input name="location"></label>
      <label class="full">Equipe participante<input name="team"></label>
      <label class="full">Observacoes<textarea name="notes"></textarea></label>
      <button class="primary full" type="submit">Salvar acao</button>
    </form>
  `);
  document.querySelector("#eventForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await api("/api/events", { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
    closeModal();
    state.bootstrap = await api("/api/bootstrap");
    showToast("Acao criada");
    render();
  });
}

async function renderGoals() {
  const { goals } = await api("/api/goals");
  document.querySelector("#view").innerHTML = `
    <section class="quick"><button class="primary" id="newGoal">Nova meta</button></section>
    <section class="list">
      ${goals.length ? goals.map((g) => `<article class="card row">
        <div><b>${g.name}</b><small>${g.start_date} ate ${g.end_date}</small></div>
        <div>META <b>${money(g.target)}</b><small>${g.metric}</small></div>
        <div>REALIZADO <b>${money(g.realized)}</b><small>${g.percent}%</small></div>
        <div>PROJECAO <b>${money(g.projection)}</b><small>${g.needed_per_day}/dia necessarios</small></div>
        <span class="pill">${g.percent >= 100 ? "concluida" : "em andamento"}</span>
      </article>`).join("") : `<article class="card muted">Cadastre metas operacionais para acompanhar ritmo e projecao.</article>`}
    </section>
  `;
  document.querySelector("#newGoal").addEventListener("click", openGoalForm);
}

function openGoalForm() {
  openModal("Nova meta operacional", `
    <form id="goalForm" class="formgrid">
      <label class="full">Nome<input name="name" placeholder="Meta contatos no periodo" required></label>
      <label>Indicador<select name="metric"><option value="contacts">novos contatos</option><option value="volunteers">novos voluntarios</option><option value="leaders">liderancas cadastradas</option><option value="events">eventos realizados</option></select></label>
      <label>Meta<input name="target" type="number" min="1" required></label>
      <label>Inicio<input name="start_date" type="date" value="${new Date().toISOString().slice(0,10)}" required></label>
      <label>Prazo<input name="end_date" type="date" required></label>
      <button class="primary full" type="submit">Salvar meta</button>
    </form>
  `);
  document.querySelector("#goalForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    await api("/api/goals", { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
    closeModal();
    render();
  });
}

async function renderSummary() {
  const s = await api("/api/daily-summary");
  const t = s.today;
  document.querySelector("#view").innerHTML = `
    <section class="grid cards">
      ${metricCard("NOVOS CONTATOS", t.newContacts)}
      ${metricCard("TRABALHADOS", t.worked)}
      ${metricCard("VOLUNTARIOS", t.volunteers)}
      ${metricCard("LIDERANCAS", t.leaders)}
      ${metricCard("INDICACOES", t.referrals)}
      ${metricCard("EVENTOS", t.events)}
    </section>
    <section class="grid charts">
      <article class="card"><h3>Comparacao</h3>
        <p>Hoje x ontem: <b>${money(t.newContacts)}</b> x <b>${money(s.yesterdayContacts)}</b></p>
        <p>Ultimos 7 dias x 7 anteriores: <b>${money(s.last7Contacts)}</b> x <b>${money(s.previous7Contacts)}</b></p>
      </article>
      ${chart("Contatos hoje por regiao", s.regions)}
      ${chart("Desempenho da equipe hoje", s.team)}
    </section>
  `;
}

async function renderReferrals() {
  const data = await api("/api/referrals");
  document.querySelector("#view").innerHTML = `
    <section class="grid cards commandCards">
      ${metricCard("Total por indicacao", data.cards.total)}
      ${metricCard("% da base", percent(data.cards.percent))}
      ${metricCard("Novos hoje", data.cards.today)}
      ${metricCard("Ultimos 7 dias", data.cards.last7)}
      ${metricCard("Media por indicador", data.cards.average)}
    </section>
    <section class="grid charts">
      <article class="card"><h3>Multiplicadores ativos nos ultimos 7 dias</h3>${data.active7.length ? table(["Nome", "RA", "Indicacoes", "Ultima"], data.active7.map((r) => [r.name, r.region_name || "Sem RA", r.direct_referrals, r.last_referral || "-"])) : `<p class="empty">Ainda nao ha multiplicadores ativos nos ultimos 7 dias.</p>`}</article>
      <article class="card"><h3>Rede de indicacoes</h3>${data.multipliers.length ? table(["Nome", "RA", "Diretas", "Cadastros", "Ultima indicacao", "Entrada"], data.multipliers.map((r) => [r.name, r.region_name || "Sem RA", r.direct_referrals, r.generated_contacts, r.last_referral || "-", (r.created_at || "").slice(0, 10)])) : `<p class="empty">As indicacoes aparecerao aqui conforme a rede crescer.</p>`}</article>
    </section>
  `;
}

async function renderOrigins() {
  const data = await api("/api/origins");
  document.querySelector("#view").innerHTML = `
    <section class="card">
      <h3>Origem de aquisicao</h3>
      ${data.origins.length ? table(["Origem", "Cadastros", "% da base", "WhatsApp", "Voluntarios", "Mobilizadores", "7 dias"], data.origins.map((r) => [r.source, r.contacts, percent(r.percent), r.whatsapp, r.volunteers, r.mobilizers, r.last7])) : `<p class="empty">Ainda nao existem dados suficientes.</p>`}
    </section>
  `;
}

async function renderRegionsReport() {
  const data = await api("/api/regions-report");
  return table(["RA", "Cadastros", "Novos 7 dias", "Voluntarios", "Mobilizadores", "Eventos", "Indicacoes", "Ultima acao"], data.regions.map((r) => [r.name, r.contacts, r.last7 || 0, r.volunteers || 0, r.mobilizers || 0, r.events || 0, r.referrals || 0, r.last_event || "-"]));
}

async function renderReports() {
  const [reports, regionsTable] = await Promise.all([api("/api/reports"), renderRegionsReport()]);
  document.querySelector("#view").innerHTML = `
    <section class="grid cards commandCards">
      ${metricCard("Telefones duplicados", reports.quality.duplicates)}
      ${metricCard("Cadastros incompletos", reports.quality.incomplete)}
      ${metricCard("Sem RA", reports.quality.withoutRegion)}
      ${metricCard("Sem origem", reports.quality.withoutSource)}
      ${metricCard("Sem responsavel", reports.quality.withoutResponsible)}
    </section>
    <section class="grid charts">
      <article class="card wide"><h3>Regioes administrativas</h3>${regionsTable}</article>
      <article class="card"><h3>Exportacoes</h3><a class="buttonlike primary" href="/api/export/contacts.csv">Exportar contatos CSV</a>${reports.exports.length ? table(["Usuario", "Acao", "Quando"], reports.exports.map((r) => [r.user_name || "Sistema", r.action, r.created_at])) : `<p class="empty">Nenhuma exportacao registrada ainda.</p>`}</article>
      <article class="card"><h3>Auditoria e seguranca</h3>${reports.security.length ? table(["Evento", "Detalhes", "Quando"], reports.security.map((r) => [r.event_name, r.details || "-", r.created_at])) : `<p class="empty">Nenhum evento de seguranca registrado.</p>`}</article>
    </section>
  `;
}

function renderSettings() {
  document.querySelector("#view").innerHTML = `
    <section class="grid charts">
      <article class="card">
        <h3>Configuracoes da campanha</h3>
        <div class="settingsList">
          <div><span>Nome da campanha</span><b>CRM Campanha 2026</b></div>
          <div><span>Candidata</span><b>Clea Torres</b></div>
          <div><span>Numero</span><b>45155</b></div>
          <div><span>Partido</span><b>PSDB Distrito Federal</b></div>
          <div><span>URL publica</span><b>Configuravel por PUBLIC_APP_URL</b></div>
          <div><span>Ambiente</span><b>Configuravel por APP_ENV</b></div>
        </div>
      </article>
      <article class="card">
        <h3>Privacidade e acesso</h3>
        <p class="muted">O CRM registra consentimentos, login, tentativas suspeitas, exportacoes e historico de alteracoes. Antes de publicar online, defina a URL publica e os dados oficiais do controlador na Politica de Privacidade.</p>
      </article>
    </section>
  `;
}

function table(headers, rows) {
  return `<div class="tableWrap"><table class="dataTable compact"><thead><tr>${headers.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((cell) => `<td>${cell ?? "-"}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

async function renderUsers() {
  const b = state.bootstrap;
  document.querySelector("#view").innerHTML = `
    <section class="grid charts">
      <article class="card">
        <h3>Criar acesso da equipe</h3>
        <form id="userForm" class="formgrid" style="margin-top:12px">
          <label>Nome<input name="name" required></label>
          <label>Email<input name="email" type="email" required></label>
          <label>Perfil<select name="role">
            <option value="Equipe de campo">Equipe de campo</option>
            <option value="Coordenacao">Coordenacao</option>
            <option value="Leitura">Leitura</option>
            <option value="Administrador">Administrador</option>
          </select></label>
          <label>Senha inicial<input name="password" type="password" autocomplete="new-password" required></label>
          <button class="primary full" type="submit">Criar usuario</button>
        </form>
        <p class="hint">Perfis: campo cadastra e atualiza seus contatos; coordenacao acompanha a operacao; leitura apenas visualiza; administrador cria usuarios.</p>
      </article>
      <article class="card">
        <h3>Equipe ativa</h3>
        <div class="list" style="margin-top:12px">
          ${b.users.map((u) => `<div class="panel teamItem"><b>${u.name}</b><span>${u.email}</span><span class="pill">${u.role}</span></div>`).join("")}
        </div>
      </article>
    </section>
  `;
  document.querySelector("#userForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/users", { method: "POST", body: JSON.stringify(formData(event.currentTarget)) });
      state.bootstrap = await api("/api/bootstrap");
      renderUsers();
    } catch (err) {
      showToast(err.status === 403 ? "Somente administrador pode criar usuarios." : "Erro ao salvar. Tente novamente.");
    }
  });
}

function openModal(title, html) {
  const modal = document.querySelector("#modal");
  modal.innerHTML = `<div class="modalHead"><h2>${title}</h2><button id="closeModal">Fechar</button></div><div class="modalBody">${html}</div>`;
  modal.showModal();
  document.querySelector("#closeModal").addEventListener("click", closeModal);
}

function closeModal() {
  document.querySelector("#modal").close();
}

boot().catch(() => {});
