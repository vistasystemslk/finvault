/* FinVault app: bootstrap, routing, navigation and global event handling. */
import {
  api, state, icon, hydrateIcons, errorPanel, esc, toast, copyText, CONFIG,
} from "./core.js";
import { FORM_ACTIONS, openSearch } from "./forms.js";
import {
  pageDashboard, pageCards, pageCardDetail, pageTransactions, pageAccounts,
} from "./pages.js";
import {
  pageInstallments, pageLoans, pageLoanDetail, pageNetworth, pageIncome,
} from "./pages2.js";
import { pageTax, pageInsights, pagePeople, pageSettings, pageApi, pageNotFound } from "./pages3.js";
import { pageScheduled } from "./pages4.js";

/* -------------------------------------------------------------------------- */
/* Navigation                                                                 */
/* -------------------------------------------------------------------------- */
const NAV = [
  {
    label: "Overview",
    items: [["dashboard", "Dashboard", "dashboard"]],
  },
  {
    label: "Money",
    items: [
      ["cards", "Credit cards", "cards", "cards"],
      ["transactions", "Transactions", "transactions", "transactions"],
      ["accounts", "Bank accounts", "bank", "accounts"],
    ],
  },
  {
    label: "Plan",
    items: [
      ["scheduled", "Scheduled", "bell"],
      ["installments", "Installments", "installments"],
      ["loans", "Loans", "loans"],
      ["networth", "Net worth", "networth"],
      ["income", "Income", "income"],
    ],
  },
  {
    label: "Intelligence",
    items: [
      ["tax", "Income tax", "tax"],
      ["insights", "Insights", "insights"],
    ],
  },
  {
    label: "System",
    items: [
      ["people", "People", "people"],
      ["settings", "Settings", "settings"],
      ["api", "API & docs", "api"],
    ],
  },
];

const ROUTES = {
  dashboard: { title: "Dashboard", load: pageDashboard },
  cards: { title: "Credit cards", load: pageCards },
  transactions: { title: "Transactions", load: pageTransactions },
  accounts: { title: "Bank accounts", load: pageAccounts },
  scheduled: { title: "Scheduled & reminders", load: pageScheduled },
  installments: { title: "Installments", load: pageInstallments },
  loans: { title: "Loans", load: pageLoans },
  networth: { title: "Net worth", load: pageNetworth },
  income: { title: "Income", load: pageIncome },
  tax: { title: "Income tax", load: pageTax },
  insights: { title: "Insights", load: pageInsights },
  people: { title: "People", load: pagePeople },
  settings: { title: "Settings", load: pageSettings },
  api: { title: "API & integrations", load: pageApi },
};

const view = document.getElementById("view");
const sidebar = document.getElementById("sidebar");
const scrim = document.querySelector(".scrim");

let booted = false;
let renderToken = 0;
let lastRouteKey = "";
let filterTimer = null;

/* -------------------------------------------------------------------------- */
/* Bootstrap                                                                  */
/* -------------------------------------------------------------------------- */
async function loadBootstrap() {
  const data = await api("/bootstrap");
  state.boot = data;
  state.persons = data.persons || [];
  state.categories = data.categories || [];
  state.fx = data.fx || [];
  state.settings = data.settings || {};
  state.counts = data.counts || {};
  normalisePerson();
}

function normalisePerson() {
  if (state.personId === "all") return;
  const exists = state.persons.some((person) => String(person.id) === String(state.personId));
  if (!exists) {
    state.personId = "all";
    localStorage.setItem("fv_person", state.personId);
  }
}

function renderPersonPicker() {
  const select = document.getElementById("personFilter");
  if (!select) return;
  select.innerHTML = `<option value="all">All people</option>` + state.persons.map((person) =>
    `<option value="${person.id}"${String(state.personId) === String(person.id) ? " selected" : ""}>${esc(person.name)}</option>`
  ).join("");
}

function renderNav() {
  const nav = document.getElementById("nav");
  if (!nav) return;
  const counts = state.counts || {};
  nav.innerHTML = NAV.map((group) => `<div class="nav-group">
    <div class="nav-label">${esc(group.label)}</div>
    ${group.items.map(([key, label, iconName, countKey]) => {
      const active = state.route === key || (key === "cards" && state.route === "card") || (key === "loans" && state.route === "loan");
      const count = countKey ? Number(counts[countKey] || 0) : 0;
      return `<a class="nav-item ${active ? "active" : ""}" href="#/${key === "dashboard" ? "dashboard" : key}" data-nav="${key}" aria-current="${active ? "page" : "false"}">
        <span class="nav-icon">${icon(iconName)}</span>
        <span>${esc(label)}</span>
        ${count > 0 ? `<span class="nav-badge">${count}</span>` : ""}
      </a>`;
    }).join("")}
  </div>`).join("");
}

function updateChrome() {
  const workspace = document.getElementById("workspaceName");
  if (workspace) {
    const person = state.persons.find((row) => String(row.id) === String(state.personId));
    workspace.textContent = person ? person.name : "My finances";
  }
  const version = document.getElementById("sideVersion");
  if (version) version.textContent = `v${CONFIG.version || "1.0.0"}`;
  const dbLabel = document.getElementById("sideDbLabel");
  if (dbLabel) dbLabel.textContent = "Data stays in this folder";
  const themeBtn = document.getElementById("themeToggle");
  if (themeBtn) {
    themeBtn.innerHTML = icon(state.theme === "dark" ? "sun" : "moon");
    themeBtn.setAttribute("aria-label", state.theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
  }
  document.title = `FinVault · ${ROUTES[state.route]?.title || "Personal finance"}`;
}

/* -------------------------------------------------------------------------- */
/* Routing                                                                    */
/* -------------------------------------------------------------------------- */
function parseRoute() {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [name, id] = raw.split("/").filter(Boolean);
  if (!name) return { route: "dashboard", id: null };
  if (name === "cards" && id) return { route: "card", id };
  if (name === "loans" && id) return { route: "loan", id };
  return { route: ROUTES[name] ? name : "notfound", id: id || null };
}

async function loadPage(route, id) {
  if (route === "card") return pageCardDetail(id);
  if (route === "loan") return pageLoanDetail(id);
  const definition = ROUTES[route];
  if (!definition) return pageNotFound();
  return definition.load();
}

async function render({ soft = false } = {}) {
  const token = ++renderToken;
  const { route, id } = parseRoute();
  const routeKey = `${route}:${id || ""}`;
  const isNewRoute = routeKey !== lastRouteKey;
  state.route = route;
  state.params = id ? { id } : {};
  renderNav();

  if (!soft || !view.innerHTML.trim() || isNewRoute) {
    view.innerHTML = `<div class="loading-screen"><div class="loader-ring"></div><p>Opening FinVault…</p></div>`;
  }

  try {
    const html = await loadPage(route, id);
    if (token !== renderToken) return;
    view.innerHTML = html;
    hydrateIcons(view);
    updateChrome();
    renderNav();
    if (isNewRoute) {
      window.scrollTo({ top: 0, behavior: "auto" });
      closeSidebar();
    }
    lastRouteKey = routeKey;
  } catch (error) {
    if (token !== renderToken) return;
    view.innerHTML = errorPanel(error);
    hydrateIcons(view);
    updateChrome();
    console.error("FinVault page error:", error);
  }
}

async function reloadAll({ soft = true } = {}) {
  try {
    await loadBootstrap();
    renderPersonPicker();
    updateChrome();
    await render({ soft });
  } catch (error) {
    view.innerHTML = errorPanel(error);
    hydrateIcons(view);
    toast(error.message || "Could not reach FinVault", "error");
  }
}

/* -------------------------------------------------------------------------- */
/* Sidebar and theme                                                          */
/* -------------------------------------------------------------------------- */
function openSidebar() {
  sidebar?.classList.add("open");
  scrim?.classList.add("show");
}

function closeSidebar() {
  sidebar?.classList.remove("open");
  scrim?.classList.remove("show");
}

function applyTheme(theme, persist = true) {
  state.theme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = state.theme;
  localStorage.setItem("fv_theme", state.theme);
  updateChrome();
  if (persist && state.settings && state.settings.theme !== state.theme) {
    api("/settings", { method: "PUT", body: { settings: { theme: state.theme } } })
      .then(() => { state.settings.theme = state.theme; })
      .catch(() => { /* theme still applies locally */ });
  }
}

function toggleTheme() {
  applyTheme(state.theme === "dark" ? "light" : "dark");
}

function setPerson(id) {
  state.personId = String(id || "all");
  localStorage.setItem("fv_person", state.personId);
  state.txOffset = 0;
  renderPersonPicker();
  reloadAll({ soft: true });
}

/* -------------------------------------------------------------------------- */
/* Actions                                                                    */
/* -------------------------------------------------------------------------- */
function toggleKey() {
  state.showKey = !state.showKey;
  render({ soft: true });
}

function gotoPage(dataset) {
  const page = dataset.page || "dashboard";
  if (dataset.entity && (page === "cards" || page === "loans")) {
    window.location.hash = `#/${page}/${dataset.entity}`;
  } else {
    window.location.hash = `#/${page}`;
  }
}

const APP_ACTIONS = {
  goto: gotoPage,
  insightGo: gotoPage,
  openCard: (dataset) => { window.location.hash = `#/cards/${dataset.id}`; },
  openLoan: (dataset) => { window.location.hash = `#/loans/${dataset.id}`; },
  reload: () => reloadAll({ soft: false }),
  refreshPage: () => reloadAll({ soft: true }),
  cardTab: (dataset) => { state.cardTab = dataset.tab || "transactions"; render({ soft: true }); },
  spendingRange: (dataset) => { state.spendingRange = dataset.range || "6m"; render({ soft: true }); },
  txPage: (dataset) => { state.txOffset = Math.max(0, Number(dataset.offset || 0)); render({ soft: true }); },
  clearTxFilters: () => {
    state.txFilters = { q: "", card_id: "", account_id: "", type: "", month: "", business: "" };
    state.txOffset = 0;
    render({ soft: true });
  },
  toggleTheme,
  toggleSidebar: openSidebar,
  closeSidebar,
  filterPerson: (dataset) => setPerson(dataset.id),
  toggleKey,
  copyKey: () => copyText(state.settings?.api_key || ""),
  copyBaseUrl: (dataset) => copyText(dataset.value || `${window.location.origin}${CONFIG.base}`),
  copyPath: (dataset) => copyText(dataset.value || ""),
  copyText: (dataset) => copyText(dataset.text || ""),
};

const ACTIONS = { ...APP_ACTIONS, ...FORM_ACTIONS };

document.addEventListener("click", (event) => {
  const target = event.target.closest("[data-action]");
  if (!target) return;
  const action = target.dataset.action;
  const handler = ACTIONS[action];
  if (!handler) {
    console.warn(`FinVault: no handler for data-action="${action}"`);
    return;
  }
  if (target.tagName === "A" && (target.getAttribute("href") || "").startsWith("#")) return;
  event.preventDefault();
  Promise.resolve(handler(target.dataset, target)).catch((error) => {
    toast(error.message || "That action failed", "error");
  });
});

document.addEventListener("change", (event) => {
  const element = event.target;
  if (element.id === "personFilter") {
    setPerson(element.value);
    return;
  }
  const change = element.dataset?.change;
  if (change === "dashboardMonth") {
    state.month = element.value || state.month;
    localStorage.setItem("fv_month", state.month);
    render({ soft: true });
    return;
  }
  if (change === "taxYear") {
    state.taxYear = element.value;
    render({ soft: true });
    return;
  }
  if (element.dataset?.filter !== undefined && element.dataset.filter !== "q") {
    applyFilter(element.dataset.filter, element.value, false);
  }
});

document.addEventListener("input", (event) => {
  const element = event.target;
  if (element.dataset?.filter !== "q") return;
  clearTimeout(filterTimer);
  const value = element.value;
  filterTimer = setTimeout(() => applyFilter("q", value, true), 360);
});

function applyFilter(name, value, isSearch) {
  if (state.route !== "transactions") return;
  state.txFilters[name] = value;
  state.txOffset = 0;
  render({ soft: true }).then(() => {
    if (isSearch) {
      const input = view.querySelector(`[data-filter="${name}"]`);
      if (input) {
        input.focus();
        const length = input.value.length;
        try { input.setSelectionRange(length, length); } catch (error) { /* range not supported */ }
      }
    }
  });
}

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault();
    openSearch();
    return;
  }
  if (event.key === "Escape") {
    closeSidebar();
    return;
  }
  if ((event.key === "Enter" || event.key === " ") && event.target?.matches?.('[role="button"][data-action]')) {
    event.preventDefault();
    event.target.click();
  }
});

/* Nav clicks: close the mobile sidebar immediately. */
document.addEventListener("click", (event) => {
  if (event.target.closest("[data-nav]")) closeSidebar();
});

/* -------------------------------------------------------------------------- */
/* Heartbeat                                                                  */
/* -------------------------------------------------------------------------- */
/* The local server can quit itself after a period without activity. While a
   FinVault tab is open we ping /api/health once a minute so idle time is only
   counted after every tab has been closed. */
function startHeartbeat() {
  const beat = () => {
    fetch("/api/health", { cache: "no-store" }).catch(() => { /* server is stopped */ });
  };
  beat();
  const timer = setInterval(beat, 60000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") beat();
  });
  window.addEventListener("pagehide", () => clearInterval(timer));
}

/* -------------------------------------------------------------------------- */
/* Boot                                                                       */
/* -------------------------------------------------------------------------- */
window.addEventListener("hashchange", () => render({ soft: false }));
document.addEventListener("fv:refresh", () => reloadAll({ soft: true }));

async function boot() {
  startHeartbeat();
  hydrateIcons(document);
  applyTheme(state.theme, false);
  try {
    await loadBootstrap();
    booted = true;
    renderPersonPicker();
    updateChrome();
    await render({ soft: false });
  } catch (error) {
    booted = false;
    view.innerHTML = errorPanel(error);
    hydrateIcons(view);
    console.error("FinVault boot error:", error);
  }
}

boot();
