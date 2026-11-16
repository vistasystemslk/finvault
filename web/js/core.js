/* FinVault core: config, state, API client, formatting, icons, charts and UI helpers. */
export const CONFIG = window.FINVAULT_CONFIG || { apiKey: "", base: "/api/v1", version: "dev" };

const today = new Date();
const currentMonth = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;

export const state = {
  boot: null,
  persons: [],
  categories: [],
  fx: [],
  settings: {},
  counts: {},
  personId: localStorage.getItem("fv_person") || "all",
  month: localStorage.getItem("fv_month") || currentMonth,
  theme: document.documentElement.dataset.theme || "dark",
  route: "dashboard",
  params: {},
  txOffset: 0,
  txLimit: 40,
  txFilters: { q: "", card_id: "", account_id: "", type: "", month: "", business: "" },
  cardTab: "transactions",
  spendingRange: "6m",
  taxYear: null,
  pageData: {},
};

export const SYMBOLS = {
  LKR: "Rs", USD: "$", EUR: "€", GBP: "£", INR: "₹", AUD: "A$", CAD: "C$",
  AED: "AED", SGD: "S$", JPY: "¥", CNY: "CN¥",
};

export class ApiError extends Error {
  constructor(message, status = 0, field = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.field = field;
  }
}

/* -------------------------------------------------------------------------- */
/* API                                                                        */
/* -------------------------------------------------------------------------- */
export async function api(path, options = {}) {
  const { method = "GET", body, headers = {} } = options;
  const response = await fetch(`${CONFIG.base}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": CONFIG.apiKey,
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch (error) {
    throw new ApiError(`Unexpected response (${response.status})`, response.status);
  }
  if (!response.ok || payload.ok === false) {
    const message = payload?.error?.message || `Request failed (${response.status})`;
    throw new ApiError(message, response.status, payload?.error?.field || null);
  }
  return payload.data;
}

export async function download(path, filename) {
  const response = await fetch(`${CONFIG.base}${path}`, {
    headers: { "X-API-Key": CONFIG.apiKey },
  });
  if (!response.ok) {
    let message = `Download failed (${response.status})`;
    try {
      const payload = await response.json();
      message = payload?.error?.message || message;
    } catch (error) { /* ignore */ }
    throw new ApiError(message, response.status);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename || "FinVault-export";
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/* -------------------------------------------------------------------------- */
/* Escaping and formatting                                                    */
/* -------------------------------------------------------------------------- */
export function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function money(value, currency = "LKR", decimals = 0) {
  const number = Number(value || 0);
  const symbol = SYMBOLS[currency] || currency || "Rs";
  const negative = number < 0;
  const digits = Number.isInteger(number) || decimals === 0 ? 0 : decimals;
  const formatted = Math.abs(number).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  const prefix = ["$", "€", "£", "₹", "¥"].includes(symbol) ? symbol : `${symbol} `;
  return `${negative ? "-" : ""}${prefix}${formatted}`;
}

export function money2(value, currency = "LKR") {
  return money(value, currency, 2);
}

export function shortMoney(value) {
  const number = Number(value || 0);
  const sign = number < 0 ? "-" : "";
  const abs = Math.abs(number);
  if (abs >= 1_000_000_000) return `${sign}Rs ${(abs / 1_000_000_000).toFixed(2)}B`;
  if (abs >= 1_000_000) return `${sign}Rs ${(abs / 1_000_000).toFixed(2)}M`;
  if (abs >= 10_000) return `${sign}Rs ${(abs / 1_000).toFixed(0)}K`;
  return money(number);
}

export function num(value, decimals = 0) {
  return Number(value || 0).toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function pct(value, decimals = 1) {
  return `${Number(value || 0).toFixed(decimals)}%`;
}

export function dateText(iso, style = "medium") {
  if (!iso) return "—";
  const parsed = new Date(`${String(iso).slice(0, 10)}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return iso;
  if (style === "short") return parsed.toLocaleDateString("en-GB", { day: "2-digit", month: "short" });
  if (style === "month") return parsed.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
  return parsed.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function monthText(month) {
  if (!month) return "—";
  const parsed = new Date(`${month}-01T00:00:00`);
  return Number.isNaN(parsed.getTime())
    ? month
    : parsed.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
}

export function monthShort(month) {
  const parsed = new Date(`${month}-01T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? month : parsed.toLocaleDateString("en-GB", { month: "short" });
}

export function daysLabel(iso) {
  if (!iso) return "";
  const target = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(target.getTime())) return "";
  const diff = Math.round((target - new Date(new Date().toDateString())) / 86400000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff < 0) return `${Math.abs(diff)}d overdue`;
  return `in ${diff}d`;
}

export function initials(name) {
  return String(name || "?")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join("");
}

export function personName(id) {
  if (!id) return "All people";
  return state.persons.find((person) => Number(person.id) === Number(id))?.name || "Unknown";
}

export function category(id) {
  return state.categories.find((item) => Number(item.id) === Number(id)) || null;
}

export function personQuery(extra = {}) {
  const params = new URLSearchParams();
  if (state.personId && state.personId !== "all") params.set("person_id", state.personId);
  for (const [key, value] of Object.entries(extra)) {
    if (value !== undefined && value !== null && value !== "") params.set(key, value);
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function currentPersonId() {
  if (state.personId && state.personId !== "all") return Number(state.personId);
  const primary = state.persons.find((person) => person.is_primary) || state.persons[0];
  return primary ? Number(primary.id) : null;
}

export function typeLabel(type) {
  const labels = {
    purchase: "Purchase", installment: "Installment", fee: "Fee", interest: "Interest",
    cash_advance: "Cash advance", expense: "Expense", payment: "Payment", card_payment: "Card payment",
    refund: "Refund", transfer: "Transfer", income_deposit: "Income", loan_payment: "Loan payment",
    adjustment: "Adjustment",
  };
  return labels[type] || type;
}

/* -------------------------------------------------------------------------- */
/* Icons                                                                      */
/* -------------------------------------------------------------------------- */
export const ICONS = {
  dashboard: '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
  cards: '<rect x="2.5" y="5" width="19" height="14" rx="2.5"/><path d="M2.5 10h19"/><path d="M7 15h4"/>',
  transactions: '<path d="M4 7h13l-3-3"/><path d="M20 17H7l3 3"/><path d="M4 12h16" opacity=".45"/>',
  accounts: '<path d="M3 10l9-6 9 6"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/><path d="M3 21h18"/>',
  installments: '<rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M3 9h18M8 2v4M16 2v4"/><path d="M8 14h3M13 14h3M8 17.5h3"/>',
  loans: '<path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.4"/><circle cx="17" cy="17" r="2.4"/>',
  networth: '<path d="M12 3v9l6.5 6.5"/><circle cx="12" cy="12" r="9"/><path d="M12 7v2" opacity=".5"/>',
  income: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  tax: '<path d="M6 2.5h8l5 5v14H6z"/><path d="M14 2.5v5h5"/><path d="M9 12h6M9 16h6"/>',
  insights: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  people: '<circle cx="9" cy="8" r="3.4"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><path d="M16 5.2a3.4 3.4 0 0 1 0 5.6M17.5 14.2c2.4.6 4 2.6 4 5.8"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .34 1.87l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.7 1.7 0 0 0-1.87-.34 1.7 1.7 0 0 0-1 1.55V21a2 2 0 0 1-4 0v-.09A1.7 1.7 0 0 0 9 19.36a1.7 1.7 0 0 0-1.87.34l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.7 1.7 0 0 0 4.64 15a1.7 1.7 0 0 0-1.55-1H3a2 2 0 0 1 0-4h.09A1.7 1.7 0 0 0 4.64 9a1.7 1.7 0 0 0-.34-1.87l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.7 1.7 0 0 0 9 4.64 1.7 1.7 0 0 0 10 3.09V3a2 2 0 0 1 4 0v.09a1.7 1.7 0 0 0 1 1.55 1.7 1.7 0 0 0 1.87-.34l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.7 1.7 0 0 0 19.36 9a1.7 1.7 0 0 0 1.55 1H21a2 2 0 0 1 0 4h-.09a1.7 1.7 0 0 0-1.55 1z"/>',
  api: '<path d="M8 9l-4 3 4 3M16 9l4 3-4 3M13.5 5l-3 14"/>',
  bell: '<path d="M18 8.5a6 6 0 0 0-12 0c0 6.5-2.5 8.5-2.5 8.5h17S18 15 18 8.5"/><path d="M13.7 20.5a2 2 0 0 1-3.4 0"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  moon: '<path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.6 6.6 0 0 0 9.8 9.8z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  chevronRight: '<path d="M9 5l7 7-7 7"/>',
  chevronLeft: '<path d="M15 5l-7 7 7 7"/>',
  arrowLeft: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
  arrowUpRight: '<path d="M7 17L17 7M8 7h9v9"/>',
  arrowDownRight: '<path d="M7 7l10 10M17 8v9H8"/>',
  download: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 20h16"/>',
  upload: '<path d="M12 16V4M7 9l5-5 5 5"/><path d="M4 20h16"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 14h10l1-14"/><path d="M10 11v6M14 11v6"/>',
  edit: '<path d="M4 20h4l11-11-4-4L4 16v4z"/><path d="M13.5 6.5l4 4"/>',
  check: '<path d="M4 12.5l5 5L20 6.5"/>',
  alert: '<path d="M12 3l9.5 17h-19z"/><path d="M12 9v5M12 17.5v.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 7.5v.01"/>',
  shield: '<path d="M12 3l8 3v6c0 4.5-3.2 7.8-8 9-4.8-1.2-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5 4.5-5"/>',
  wallet: '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H19a2 2 0 0 1 2 2v12H5.5A2.5 2.5 0 0 1 3 16.5z"/><path d="M3 8h18"/><circle cx="16.5" cy="13.5" r="1"/>',
  bank: '<path d="M3 10l9-6 9 6"/><path d="M5 10v8M9.5 10v8M14.5 10v8M19 10v8"/><path d="M3 21h18"/>',
  refresh: '<path d="M20 11a8 8 0 1 0 .4 4"/><path d="M20 4v7h-7"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  calendar: '<rect x="3" y="4" width="18" height="17" rx="2.5"/><path d="M3 9h18M8 2v4M16 2v4"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4 2v-8z"/>',
  eye: '<path d="M2 12s3.5-6.5 10-6.5S22 12 22 12s-3.5 6.5-10 6.5S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/>',
  eyeOff: '<path d="M3 3l18 18"/><path d="M10.6 6.1A10.9 10.9 0 0 1 12 6c6.5 0 10 6 10 6a17.4 17.4 0 0 1-3.2 3.9M6.2 6.2A17.5 17.5 0 0 0 2 12s3.5 6 10 6a10.7 10.7 0 0 0 4.1-.8"/>',
  sparkles: '<path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6z"/><path d="M19 15l.8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8zM5 3l.6 1.4L7 5l-1.4.6L5 7l-.6-1.4L3 5l1.4-.6z"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
  zap: '<path d="M13 2L4 14h7l-1 8 9-12h-7z"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v6c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 11v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6"/>',
  key: '<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M14 9l2 2"/>',
  pie: '<path d="M21 12a9 9 0 1 1-9-9v9z"/><path d="M12 3a9 9 0 0 1 9 9h-9z" opacity=".45"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1.5"/>',
  repeat: '<path d="M17 2l4 4-4 4"/><path d="M3 11V9a3 3 0 0 1 3-3h15"/><path d="M7 22l-4-4 4-4"/><path d="M21 13v2a3 3 0 0 1-3 3H3"/>',
  receipt: '<path d="M5 2.5h14v19l-3-2-2 2-2-2-2 2-2-2-3 2z"/><path d="M9 7h6M9 11h6M9 15h3"/>',
  logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/>',
  percent: '<path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.4"/><circle cx="17" cy="17" r="2.4"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  code: '<path d="M8 9l-4 3 4 3M16 9l4 3-4 3"/>',
  users: '<circle cx="9" cy="8" r="3.4"/><path d="M2.5 20c0-3.6 2.9-6 6.5-6s6.5 2.4 6.5 6"/><path d="M16 5.2a3.4 3.4 0 0 1 0 5.6M17.5 14.2c2.4.6 4 2.6 4 5.8"/>',
  dot: '<circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/>',
};

export function icon(name, extraClass = "") {
  const body = ICONS[name] || ICONS.dot;
  return `<svg class="ico ${extraClass}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${body}</svg>`;
}

export const ic = (name, cls = "") => `<span class="ic ${cls}">${icon(name)}</span>`;

export function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((element) => {
    if (!element.dataset.hydrated) {
      element.innerHTML = icon(element.dataset.icon);
      element.dataset.hydrated = "1";
    }
  });
}

/* -------------------------------------------------------------------------- */
/* Charts                                                                     */
/* -------------------------------------------------------------------------- */
export function donut(items, { size = 152, thickness = 16, centerLabel = "", centerValue = "" } = {}) {
  const total = items.reduce((sum, item) => sum + Math.max(0, Number(item.amount || 0)), 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const segments = items.map((item) => {
    const value = Math.max(0, Number(item.amount || 0));
    const length = total > 0 ? (value / total) * circumference : 0;
    const dash = `${length} ${circumference - length}`;
    const segment = `<circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none"
      stroke="${esc(item.color || "#6366f1")}" stroke-width="${thickness}" stroke-dasharray="${dash}"
      stroke-dashoffset="${-offset}" transform="rotate(-90 ${size / 2} ${size / 2})" stroke-linecap="butt"/>`;
    offset += length;
    return segment;
  }).join("");
  return `<svg class="donut" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img">
    <circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="var(--panel-2)" stroke-width="${thickness}"/>
    ${segments}
    <text x="50%" y="47%" text-anchor="middle" class="donut-center-label">${esc(centerLabel)}</text>
    <text x="50%" y="60%" text-anchor="middle" class="donut-center-value">${esc(centerValue)}</text>
  </svg>`;
}

export function ring(value, size = 118, thickness = 11, color = null) {
  const safe = Math.max(0, Math.min(100, Number(value || 0)));
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const length = (safe / 100) * circumference;
  const stroke = color || (safe >= 75 ? "var(--red)" : safe >= 30 ? "var(--amber)" : "var(--green)");
  return `<svg class="donut" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img">
    <circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="var(--panel-2)" stroke-width="${thickness}"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${radius}" fill="none" stroke="${stroke}" stroke-width="${thickness}"
      stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="0"
      transform="rotate(-90 ${size / 2} ${size / 2})" stroke-linecap="round"/>
    <text x="50%" y="49%" text-anchor="middle" class="donut-center-value">${safe.toFixed(0)}%</text>
    <text x="50%" y="60%" text-anchor="middle" class="donut-center-label">used</text>
  </svg>`;
}

export function barChart(series) {
  const max = Math.max(1, ...series.flatMap((row) => [Number(row.income || 0), Number(row.expenses || 0)]));
  return `<div class="bars">${series.map((row) => {
    const income = Math.max(0, Number(row.income || 0));
    const expenses = Math.max(0, Number(row.expenses || 0));
    return `<div class="bar-group" title="${esc(monthText(row.month))} · Income ${money(income)} · Expenses ${money(expenses)}">
      <div class="bar-pair">
        <i class="bar income" style="height:${Math.max(2, (income / max) * 100)}%"></i>
        <i class="bar expense" style="height:${Math.max(2, (expenses / max) * 100)}%"></i>
      </div>
      <span class="bar-label">${esc(monthShort(row.month))}</span>
    </div>`;
  }).join("")}</div>`;
}

export function lineChart(history, { height = 170, minimal = false } = {}) {
  if (!history || history.length === 0) {
    return `<div class="empty" style="padding:24px"><p>No history yet. The chart fills in as you use FinVault.</p></div>`;
  }
  const width = 600;
  const padX = minimal ? 2 : 34;
  const padTop = minimal ? 3 : 12;
  const padBottom = minimal ? 3 : 24;
  const values = history.map((row) => Number(row.net_worth || 0));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || Math.max(1, Math.abs(max) * 0.1);
  const low = min - span * 0.12;
  const high = max + span * 0.12;
  const plotW = width - padX * 2;
  const plotH = height - padTop - padBottom;
  const points = values.map((value, index) => {
    const x = padX + (history.length === 1 ? plotW / 2 : (index / (history.length - 1)) * plotW);
    const y = padTop + (1 - (value - low) / (high - low)) * plotH;
    return [x, y];
  });
  const line = points.map(([x, y], index) => `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${points[points.length - 1][0].toFixed(1)},${(height - padBottom).toFixed(1)} L${points[0][0].toFixed(1)},${(height - padBottom).toFixed(1)} Z`;
  const gradientId = `lineGradient-${Math.random().toString(36).slice(2, 9)}`;
  const gridLines = minimal ? "" : [0.25, 0.5, 0.75].map((ratio) => {
    const y = padTop + plotH * ratio;
    return `<line class="grid" x1="${padX}" y1="${y}" x2="${width - padX}" y2="${y}" stroke-dasharray="3 5"/>`;
  }).join("");
  const labels = minimal ? "" : [0, Math.floor((history.length - 1) / 2), history.length - 1]
    .filter((value, index, arr) => value >= 0 && arr.indexOf(value) === index)
    .map((index) => {
      const x = padX + (history.length === 1 ? plotW / 2 : (index / (history.length - 1)) * plotW);
      return `<text x="${x}" y="${height - 6}" text-anchor="${index === 0 ? "start" : index === history.length - 1 ? "end" : "middle"}">${esc(dateText(history[index].date, "short"))}</text>`;
    }).join("");
  const last = points[points.length - 1];
  return `<svg class="line-chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="img">
    <defs><linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#6366f1" stop-opacity=".5"/>
      <stop offset="100%" stop-color="#6366f1" stop-opacity="0"/>
    </linearGradient></defs>
    ${gridLines}
    <path d="${area}" fill="url(#${gradientId})"/>
    <path class="line" d="${line}"/>
    ${minimal ? "" : `<circle class="dot" cx="${last[0]}" cy="${last[1]}" r="3.5"/>`}
    ${labels}
  </svg>`;
}

/* -------------------------------------------------------------------------- */
/* UI helpers                                                                 */
/* -------------------------------------------------------------------------- */
export function toast(message, type = "success", title = "") {
  const root = document.getElementById("toastRoot");
  if (!root) return;
  const icons = { success: "check", error: "alert", warning: "alert", info: "info" };
  const element = document.createElement("div");
  element.className = `toast ${type}`;
  element.innerHTML = `<span class="ico">${icon(icons[type] || "info")}</span>
    <div><strong>${esc(title || (type === "error" ? "Something went wrong" : type === "warning" ? "Heads up" : "Done"))}</strong>
    <span>${esc(message)}</span></div>`;
  root.appendChild(element);
  setTimeout(() => {
    element.style.opacity = "0";
    element.style.transform = "translateY(8px)";
    element.style.transition = "all .2s ease";
    setTimeout(() => element.remove(), 220);
  }, type === "error" ? 6200 : 3800);
}

let activeModal = null;

export function closeModal() {
  if (!activeModal) return;
  activeModal.remove();
  activeModal = null;
  document.body.style.overflow = "";
}

export function openModal(options) {
  const {
    title, subtitle = "", body = "", submitLabel = "Save", cancelLabel = "Cancel",
    onSubmit = null, size = "", danger = false, footerExtra = "", onMount = null,
    hideSubmit = false,
  } = options;
  closeModal();
  const root = document.getElementById("modalRoot");
  const wrap = document.createElement("div");
  wrap.className = "modal-backdrop";
  wrap.innerHTML = `<form class="modal ${size}" novalidate>
    <div class="modal-head">
      <div><h2>${esc(title)}</h2>${subtitle ? `<p>${esc(subtitle)}</p>` : ""}</div>
      <button type="button" class="icon-btn small modal-close" data-modal-close aria-label="Close">${icon("close")}</button>
    </div>
    <div class="modal-body">${body}</div>
    <div class="modal-foot">
      ${footerExtra ? `<div class="left">${footerExtra}</div>` : ""}
      <button type="button" class="btn btn-ghost" data-modal-close>${esc(cancelLabel)}</button>
      ${hideSubmit ? "" : `<button type="submit" class="btn ${danger ? "btn-danger" : "btn-primary"}">${esc(submitLabel)}</button>`}
    </div>
  </form>`;
  root.appendChild(wrap);
  activeModal = wrap;
  document.body.style.overflow = "hidden";
  hydrateIcons(wrap);
  wrap.addEventListener("mousedown", (event) => {
    if (event.target === wrap) closeModal();
  });
  wrap.querySelectorAll("[data-modal-close]").forEach((button) => {
    button.addEventListener("click", closeModal);
  });
  const form = wrap.querySelector("form");
  const submitButton = form.querySelector('button[type="submit"]');
  if (onSubmit) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (submitButton) {
        submitButton.disabled = true;
        submitButton.dataset.original = submitButton.textContent;
        submitButton.textContent = "Saving…";
      }
      try {
        await onSubmit(formToObject(form), form);
        closeModal();
      } catch (error) {
        toast(error.message || "Could not save", "error");
        if (error.field) {
          const field = form.querySelector(`[name="${error.field}"]`);
          if (field) {
            field.focus();
            field.style.borderColor = "var(--red)";
            setTimeout(() => { field.style.borderColor = ""; }, 2400);
          }
        }
      } finally {
        if (submitButton) {
          submitButton.disabled = false;
          submitButton.textContent = submitButton.dataset.original || submitLabel;
        }
      }
    });
  }
  const firstInput = wrap.querySelector("input:not([type=hidden]):not([type=checkbox]), select, textarea");
  if (firstInput) setTimeout(() => firstInput.focus(), 60);
  if (onMount) onMount(form, wrap);
  wrap.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeModal();
  });
  return { form, wrap };
}

export function formToObject(form) {
  const result = {};
  for (const [key, value] of new FormData(form)) result[key] = value;
  return result;
}

export async function confirmAction({ title, message, confirmLabel = "Delete", danger = true, onConfirm }) {
  openModal({
    title,
    subtitle: "",
    size: "sm",
    body: `<div class="inline-note ${danger ? "danger" : ""}">${icon(danger ? "alert" : "info")}<div>${esc(message)}</div></div>`,
    submitLabel: confirmLabel,
    danger,
    onSubmit: async () => onConfirm(),
  });
}

export function emptyState(iconName, title, message, actions = "") {
  return `<div class="empty">
    <div class="empty-icon">${icon(iconName)}</div>
    <h3>${esc(title)}</h3>
    <p>${esc(message)}</p>
    ${actions ? `<div class="empty-actions">${actions}</div>` : ""}
  </div>`;
}

export function options(items, selected, { value = "id", label = "name", placeholder = "" } = {}) {
  const head = placeholder ? `<option value="">${esc(placeholder)}</option>` : "";
  return head + items.map((item) => {
    const itemValue = typeof item === "object" ? item[value] : item;
    const itemLabel = typeof item === "object" ? item[label] : item;
    const isSelected = String(itemValue) === String(selected ?? "") ? " selected" : "";
    return `<option value="${esc(itemValue)}"${isSelected}>${esc(itemLabel)}</option>`;
  }).join("");
}

export function categoryOptions(selected = "", kind = null) {
  const items = state.categories.filter((item) => !kind || item.kind === kind);
  return `<option value="">Uncategorized</option>` + items.map((item) =>
    `<option value="${item.id}"${String(selected) === String(item.id) ? " selected" : ""}>${esc(item.icon)} ${esc(item.name)}</option>`
  ).join("");
}

export function cardOptions(selected = "", { includeAccounts = false, personId = null } = {}) {
  let html = `<option value="">Select…</option>`;
  const cards = state.pageData.cardsRef || [];
  const accounts = state.pageData.accountsRef || [];
  const filteredCards = personId ? cards.filter((card) => Number(card.person_id) === Number(personId)) : cards;
  const filteredAccounts = personId ? accounts.filter((acct) => Number(acct.person_id) === Number(personId)) : accounts;
  if (filteredCards.length) {
    html += `<optgroup label="Credit cards">` + filteredCards.map((card) =>
      `<option value="card:${card.id}"${String(selected) === `card:${card.id}` ? " selected" : ""}>${esc(card.name)}${card.last4 ? ` ••${card.last4}` : ""}</option>`
    ).join("") + `</optgroup>`;
  }
  if (includeAccounts && filteredAccounts.length) {
    html += `<optgroup label="Bank accounts">` + filteredAccounts.map((acct) =>
      `<option value="account:${acct.id}"${String(selected) === `account:${acct.id}` ? " selected" : ""}>${esc(acct.name)}</option>`
    ).join("") + `</optgroup>`;
  }
  return html;
}

export function progress(value, cls = "") {
  const safe = Math.max(0, Math.min(100, Number(value || 0)));
  return `<div class="progress ${cls}"><i style="width:${safe}%"></i></div>`;
}

export function statusTag(status) {
  const map = {
    active: ["success", "Active"], paid: ["success", "Paid"], completed: ["success", "Completed"],
    unpaid: ["warning", "Unpaid"], partial: ["warning", "Partial"], overdue: ["danger", "Overdue"],
    closed: ["neutral", "Closed"], cancelled: ["neutral", "Cancelled"],
  };
  const [cls, label] = map[status] || ["neutral", status || "—"];
  return `<span class="tag ${cls}">${esc(label)}</span>`;
}

export function severityIcon(severity) {
  return severity === "critical" ? "alert" : severity === "warning" ? "alert" : severity === "success" ? "check" : "sparkles";
}

export async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast("Copied to clipboard");
  } catch (error) {
    const area = document.createElement("textarea");
    area.value = text;
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); toast("Copied to clipboard"); } catch (err) { toast("Could not copy", "error"); }
    area.remove();
  }
}

export function refresh() {
  document.dispatchEvent(new CustomEvent("fv:refresh"));
}

export function navigate(hash) {
  window.location.hash = hash;
}

export function tapAction(action, dataset = {}) {
  const element = document.createElement("button");
  element.dataset.action = action;
  Object.assign(element.dataset, dataset);
  document.body.appendChild(element);
  element.click();
  element.remove();
}

export function relativeDays(iso) {
  const label = daysLabel(iso);
  return label;
}

export function attr(value) {
  return esc(value).replaceAll("\n", " ");
}

/* -------------------------------------------------------------------------- */
/* Shared page building blocks                                                */
/* -------------------------------------------------------------------------- */
export function pageHead({ eyebrow = "", title, subtitle = "", actions = "" }) {
  return `<div class="page-head">
    <div>
      ${eyebrow ? `<div class="eyebrow">${esc(eyebrow)}</div>` : ""}
      <h1>${esc(title)}</h1>
      ${subtitle ? `<div class="subtitle">${subtitle}</div>` : ""}
    </div>
    ${actions ? `<div class="actions">${actions}</div>` : ""}
  </div>`;
}

export function statCard({ label, value, foot = "", iconName = "chart", tone = "", hint = "" }) {
  return `<div class="stat ${tone}" ${hint ? `title="${attr(hint)}"` : ""}>
    <div class="stat-top"><span class="stat-label">${esc(label)}</span>
      <span class="stat-icon">${icon(iconName)}</span></div>
    <div class="stat-value">${value}</div>
    ${foot ? `<div class="stat-foot">${foot}</div>` : ""}
  </div>`;
}

export function panelHead(title, subtitle = "", right = "", iconName = "") {
  return `<div class="panel-head">
    <div><div class="panel-title">${iconName ? icon(iconName) : ""}${esc(title)}</div>
    ${subtitle ? `<div class="panel-sub">${esc(subtitle)}</div>` : ""}</div>
    ${right || ""}
  </div>`;
}

export function creditCard(card, { large = false } = {}) {
  const utilization = Math.max(0, Math.min(100, Number(card.utilization || 0)));
  const due = card.due_date ? `Due ${dateText(card.due_date, "short")}` : "No payment due";
  return `<div class="credit-card ${card.status === "closed" ? "cc-closed" : ""} ${large ? "detail-card-large" : ""}"
      style="--from:${attr(card.color_from || "#4f46e5")};--to:${attr(card.color_to || "#0ea5e9")}"
      data-action="openCard" data-id="${card.id}" role="button" tabindex="0" aria-label="Open ${attr(card.name)}">
    <div class="cc-top">
      <div><div class="cc-issuer">${esc(card.issuer || card.name)}</div>
        <div class="cc-purpose">${esc(card.purpose || "personal")} · ${esc(card.network || "credit")}</div></div>
      <div class="cc-chip"></div>
    </div>
    <div class="cc-number">•••• &nbsp;•••• &nbsp;•••• &nbsp;${esc(card.last4 || "••••")}</div>
    <div class="cc-bottom"><span class="cc-name">${esc(card.name)}</span><span class="cc-network">${esc(card.network || "CARD")}</span></div>
    <div class="cc-stats">
      <div><div class="cc-out-label">Outstanding</div><div class="cc-out">${money(card.outstanding, card.currency)}</div></div>
      <div class="cc-limit">Limit ${money(card.credit_limit, card.currency)}<br>${utilization.toFixed(0)}% used</div>
    </div>
    <div class="cc-util"><i style="width:${utilization}%"></i></div>
    <div class="cc-due"><span>${esc(due)}</span><span>${card.minimum_due ? `Min ${money(card.minimum_due, card.currency)}` : ""}</span></div>
  </div>`;
}

export function miniCard(card) {
  const utilization = Math.max(0, Math.min(100, Number(card.utilization || 0)));
  return `<div class="mini-card" style="--from:${attr(card.color_from || "#4f46e5")};--to:${attr(card.color_to || "#0ea5e9")}"
      data-action="openCard" data-id="${card.id}" role="button" tabindex="0">
    <div class="mini-card-top"><span>${esc(card.issuer || "Card")}</span><span>${utilization.toFixed(0)}%</span></div>
    <div class="mini-card-name">${esc(card.name)}${card.last4 ? ` ·· ${esc(card.last4)}` : ""}</div>
    <div class="mini-card-bal">${money(card.outstanding, card.currency)}</div>
    <div class="mini-card-foot"><span>${utilization.toFixed(0)}% of ${money(card.credit_limit, card.currency)}</span><span>${card.due_date ? dateText(card.due_date, "short") : ""}</span></div>
  </div>`;
}

export function amountClass(direction, type) {
  if (type === "payment" || type === "refund" || direction === "in") return "pos";
  return "neg";
}

export function signedAmount(amount, direction, currency = "LKR") {
  return `${direction === "in" ? "+" : "−"}${money(amount, currency)}`;
}

export function categoryTag(id) {
  const cat = category(id);
  if (!cat) return `<span class="tag category">Uncategorized</span>`;
  return `<span class="tag category"><span class="dot" style="background:${attr(cat.color)}"></span>${esc(cat.icon)} ${esc(cat.name)}</span>`;
}

export function errorPanel(error) {
  return `<div class="panel error-panel">
    <div class="panel-title">${icon("alert")} Could not load this page</div>
    <div class="panel-sub" style="margin-top:8px">${esc(error.message || String(error))}</div>
    <div style="margin-top:14px"><button class="btn" data-action="reload">${icon("refresh")} Try again</button></div>
  </div>`;
}

