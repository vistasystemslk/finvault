/* FinVault pages: tax, insights, people, settings, API docs. */
import {
  api, CONFIG, state, money, shortMoney, pct, num, dateText, monthText, monthShort, icon,
  donut, barChart, emptyState, options, progress, statusTag, esc, attr, personQuery,
  currentPersonId, pageHead, statCard, panelHead, severityIcon, copyText,
} from "./core.js";

export async function pageTax() {
  const years = await api("/tax/years");
  const year = state.taxYear || years.current || years.years[0]?.year_label;
  state.taxYear = year;
  const personId = currentPersonId();
  if (!personId) return errorCard("Create a person first before calculating tax.");
  const estimate = await api(`/tax/summary?person_id=${personId}&year_label=${encodeURIComponent(year)}`);
  state.pageData.tax = estimate;
  const h = estimate.heads;
  const maxHead = Math.max(1, ...Object.values(h).map(Number));
  const payable = Number(estimate.tax_payable);
  const headLabels = { employment: "Employment", business: "Business", investment: "Investment", rental: "Rental", other: "Other" };
  const reliefs = estimate.reliefs || [];
  const credits = estimate.credit_items || [];

  return `${pageHead({
    eyebrow: "Tax",
    title: "Income tax",
    subtitle: `Sri Lankan personal income tax for ${esc(year)}. Rates are editable, so you can match your official tax sheet exactly.`,
    actions: `<select class="select" data-change="taxYear" style="width:150px">${options(years.years, year, { value: "year_label", label: "label", placeholder: "" })}</select>
      <button class="btn" data-action="exportTax" data-year="${attr(year)}" data-person="${personId}">${icon("download")} Export CSV</button>
      <button class="btn" data-action="editTaxRules" data-year="${attr(year)}">${icon("edit")} Tax rates</button>
      <button class="btn btn-primary" data-action="addIncome">${icon("plus")} Add income</button>`,
  })}
  ${state.personId === "all" ? `<div class="inline-note" style="margin-bottom:15px">${icon("info")}<div>Tax is calculated per person. Showing <strong>${esc(estimate.person.name)}</strong> because “All people” is selected. Choose a person in the top bar to switch.</div></div>` : ""}

  <div class="tax-summary">
    <div class="tax-highlight"><span>Total assessable income</span><strong>${money(estimate.total_assessable)}</strong><small>${esc(estimate.year_range.start)} → ${esc(estimate.year_range.end)}</small></div>
    <div class="tax-highlight"><span>Taxable income</span><strong>${money(estimate.taxable_income)}</strong><small>After ${money(estimate.deductions.total)} reliefs</small></div>
    <div class="tax-highlight"><span>Gross tax</span><strong>${money(estimate.gross_tax)}</strong><small>Effective rate ${pct(estimate.effective_rate)}</small></div>
    <div class="tax-highlight ${payable > 0 ? "payable" : "refund"}"><span>${payable > 0 ? "Tax payable" : "Refund / credit"}</span><strong>${money(Math.abs(payable))}</strong><small>After ${money(estimate.credits.total)} credits</small></div>
  </div>

  <div class="dash-grid equal">
    <section class="panel">
      ${panelHead("Income by head", `${estimate.incomes.length} income entr${estimate.incomes.length === 1 ? "y" : "ies"} in this tax year`, `<button class="btn btn-sm" data-action="addIncome">${icon("plus")} Add</button>`, "income")}
      ${Object.entries(h).map(([key, value]) => `<div class="head-bar">
        <span class="name">${esc(headLabels[key] || key)}</span>
        <div class="bar-track"><i style="width:${Math.max(0, (Number(value) / maxHead) * 100)}%"></i></div>
        <span class="val">${money(value)}</span>
      </div>`).join("")}
      <div class="divider"></div>
      <div class="stat-line"><span>Deductible business expenses</span><strong class="pos">− ${money(estimate.deductions.used_against_business)}</strong></div>
      ${estimate.deductions.unused > 0 ? `<div class="small-note">${money(estimate.deductions.unused)} of deductible expenses could not be used against business income.</div>` : ""}
      <div class="stat-line"><span>Marginal rate</span><strong>${pct(estimate.marginal_rate * 100)}</strong></div>
    </section>

    <section class="panel">
      ${panelHead("Reliefs & deductions", "Reduce your taxable income", `<button class="btn btn-sm" data-action="addTaxRelief" data-year="${attr(year)}">${icon("plus")} Add relief</button>`, "shield")}
      <div class="stat-line"><span>Rent relief (${estimate.rules.rent_relief_pct}% of rental income)</span><strong>${money(estimate.deductions.rent_relief)}</strong></div>
      <div class="stat-line"><span>Qualifying reliefs</span><strong>${money(estimate.deductions.qualifying_reliefs)}</strong></div>
      <div class="stat-line"><span>Total reliefs</span><strong>${money(estimate.deductions.total)}</strong></div>
      ${reliefs.length ? `<div class="divider"></div><div class="section-title">Saved reliefs</div>
        <div class="table-wrap"><table class="table table-compact"><tbody>${reliefs.map((row) => `<tr>
          <td>${esc(row.name)}<div class="row-sub">${esc(row.kind)}</div></td>
          <td class="num">${money(row.amount)}</td>
          <td class="actions-cell"><button class="icon-btn small" data-action="editTaxRelief" data-id="${row.id}">${icon("edit")}</button><button class="icon-btn small danger" data-action="deleteTaxRelief" data-id="${row.id}">${icon("trash")}</button></td>
        </tr>`).join("")}</tbody></table></div>` : `<div class="small-note" style="margin-top:10px">No qualifying reliefs recorded for this year.</div>`}
    </section>
  </div>

  <div class="dash-grid equal">
    <section class="panel">
      ${panelHead("Tax slab calculation", "Progressive rates applied to taxable income", "", "tax")}
      <div class="table-wrap"><table class="table tax-slab-table">
        <thead><tr><th>Band</th><th class="num">Rate</th><th class="num">Taxable in band</th><th class="num">Tax</th></tr></thead>
        <tbody>${(estimate.slabs || []).map((slab) => `<tr>
          <td>${money(slab.from)}${slab.to ? ` – ${money(slab.to)}` : "+"}</td>
          <td class="num">${pct(slab.rate * 100, 0)}</td>
          <td class="num">${money(slab.amount)}</td>
          <td class="num">${money(slab.tax)}</td>
        </tr>`).join("") || `<tr><td colspan="4" class="muted">No tax is due on this taxable income.</td></tr>`}</tbody>
        <tfoot><tr><th colspan="3" class="right">Gross tax</th><th class="num">${money(estimate.gross_tax)}</th></tr></tfoot>
      </table></div>
      <div class="small-note" style="margin-top:10px">Personal relief of ${money(estimate.rules.personal_relief)} is built into the first 0% band.</div>
    </section>

    <section class="panel">
      ${panelHead("Tax credits", "APIT, WHT and other payments already made", `<button class="btn btn-sm" data-action="addTaxCredit" data-year="${attr(year)}">${icon("plus")} Add credit</button>`, "check")}
      <div class="stat-line"><span>APIT (employment tax)</span><strong>${money(estimate.credits.apit)}</strong></div>
      <div class="stat-line"><span>WHT</span><strong>${money(estimate.credits.wht)}</strong></div>
      <div class="stat-line"><span>Other credits</span><strong>${money(estimate.credits.other)}</strong></div>
      <div class="stat-line"><span>Total credits</span><strong>${money(estimate.credits.total)}</strong></div>
      ${credits.length ? `<div class="divider"></div><div class="table-wrap"><table class="table table-compact"><tbody>${credits.map((row) => `<tr>
        <td>${esc(row.name)}<div class="row-sub">${esc(row.kind)}</div></td>
        <td class="num">${money(row.amount)}</td>
        <td class="actions-cell"><button class="icon-btn small" data-action="editTaxCredit" data-id="${row.id}">${icon("edit")}</button><button class="icon-btn small danger" data-action="deleteTaxCredit" data-id="${row.id}">${icon("trash")}</button></td>
      </tr>`).join("")}</tbody></table></div>` : ""}
      <div class="inline-note" style="margin-top:14px">${icon("info")}<div>${payable > 0 ? `Estimated balance payable: <strong>${money(payable)}</strong> (about ${money(estimate.monthly_estimate)}/month).` : `You have ${money(Math.abs(payable))} more credits than tax due — potentially a refund.`}</div></div>
    </section>
  </div>

  <section class="panel" style="margin-top:16px">
    ${panelHead("Tax rules used", esc(year), `<button class="btn btn-sm" data-action="editTaxRules" data-year="${attr(year)}">${icon("edit")} Edit</button>`, "settings")}
    <div class="small-note">${esc(estimate.rules_note || "Verify these rates against the official Inland Revenue guidance.")}</div>
    <div class="small-note" style="margin-top:6px">When you share your Sri Lankan tax sheet, these slabs, reliefs and credit fields can be mapped one-to-one.</div>
  </section>`;
}

function errorCard(message) {
  return `<div class="panel error-panel"><div class="panel-title">${icon("alert")} ${esc(message)}</div></div>`;
}

function insightCards(insights) {
  return `<div class="insights-list">${(insights || []).map((insight) => `
    <div class="insight ${esc(insight.severity)}">
      <div class="insight-icon">${icon(severityIcon(insight.severity))}</div>
      <div class="insight-body"><div class="insight-title">${esc(insight.title)}</div><div class="insight-text">${esc(insight.message)}</div></div>
      ${insight.metric ? `<div class="insight-metric">${esc(insight.metric)}</div>` : ""}
    </div>`).join("")}</div>`;
}

function rangeDates(range) {
  const now = new Date();
  const end = now.toISOString().slice(0, 10);
  if (range === "ytd") return { start: `${now.getFullYear()}-01-01`, end };
  const months = Number(range.replace("m", "")) || 6;
  const start = new Date(now.getFullYear(), now.getMonth() - months + 1, 1);
  return { start: start.toISOString().slice(0, 10), end };
}

export async function pageInsights() {
  const { start, end } = rangeDates(state.spendingRange);
  const [insights, spending] = await Promise.all([
    api(`/insights${personQuery({ month: state.month })}`),
    api(`/analytics/spending${personQuery({ from: start, to: end })}`),
  ]);
  state.pageData.insights = insights;
  state.pageData.spending = spending;
  const cats = (spending.categories || []).slice(0, 8);
  const maxCat = Math.max(1, ...cats.map((cat) => Number(cat.amount || 0)));
  const business = Number(spending.business_spend || 0);
  const personal = Number(spending.personal_spend || 0);
  const total = Number(spending.total_spend || 0);

  return `${pageHead({
    eyebrow: "Intelligence",
    title: "Insights & spending",
    subtitle: "Patterns, anomalies and recommendations built from your own transactions. Nothing leaves this computer.",
    actions: `<div class="chip-row">${[["3m", "3 months"], ["6m", "6 months"], ["12m", "12 months"], ["ytd", "This year"]].map(([key, label]) => `<button class="chip ${state.spendingRange === key ? "active" : ""}" data-action="spendingRange" data-range="${key}">${label}</button>`).join("")}</div>`,
  })}
  <div class="stat-grid">
    ${statCard({ label: "Total spend", value: money(spending.total_spend), foot: `${esc(dateText(start, "short"))} – ${esc(dateText(end, "short"))}`, iconName: "transactions", tone: "red" })}
    ${statCard({ label: "Business spend", value: money(business), foot: `${pct(total ? (business / total) * 100 : 0)} of spending`, iconName: "tax", tone: "cyan" })}
    ${statCard({ label: "Personal spend", value: money(personal), foot: `${pct(total ? (personal / total) * 100 : 0)} of spending`, iconName: "wallet" })}
    ${statCard({ label: "Tax deductible", value: money(spending.tax_deductible), foot: "Ready for your tax return", iconName: "shield", tone: "green" })}
  </div>

  <section class="panel" style="margin-bottom:16px">
    ${panelHead("Recommendations", "Ranked by impact on your finances", "", "sparkles")}
    ${insightCards(insights)}
  </section>

  <div class="dash-grid">
    <section class="panel">
      ${panelHead("Spending by category", "Largest categories in the selected range", "", "pie")}
      ${cats.length ? `<div class="donut-wrap">
        ${donut(cats, { size: 160, thickness: 17, centerLabel: "spent", centerValue: shortMoney(total) })}
        <div class="legend" style="flex:1;min-width:200px">${cats.map((cat) => `<div class="legend-row"><span class="swatch" style="background:${attr(cat.color)}"></span><span class="name">${esc(cat.name)}</span><span class="val">${money(cat.amount)}</span></div>`).join("")}</div>
      </div>` : `<div class="empty" style="padding:30px"><p>No spending in this range.</p></div>`}
    </section>
    <section class="panel">
      ${panelHead("Monthly trend", "Income vs expenses", `<div class="legend-inline"><span><i style="background:#10b981"></i>Income</span><span><i style="background:#fb7185"></i>Expenses</span></div>`, "insights")}
      ${barChart(spending.monthly || [])}
    </section>
  </div>

  <div class="dash-grid thirds">
    <section class="panel">
      ${panelHead("Top merchants", "Where the money goes", "", "receipt")}
      ${(spending.merchants || []).length ? `<div class="list">${spending.merchants.slice(0, 8).map((merchant, index) => `<div class="list-row">
        <div class="list-icon">${index + 1}</div><div class="list-main"><div class="list-title">${esc(merchant.name)}</div></div><div class="list-end"><div class="list-amount">${money(merchant.amount)}</div></div>
      </div>`).join("")}</div>` : `<div class="small-note">No merchant data yet.</div>`}
    </section>
    <section class="panel">
      ${panelHead("Spend by card", "Which card carries the load", "", "cards")}
      ${(spending.cards || []).length ? `<div class="list">${spending.cards.map((row) => `<div class="list-row">
        <div class="list-icon">${icon("cards")}</div><div class="list-main"><div class="list-title">${esc(row.name)}</div><div class="list-sub">${pct(total ? (row.amount / total) * 100 : 0)} of spend</div></div>
        <div class="list-end"><div class="list-amount">${money(row.amount)}</div></div>
      </div>`).join("")}</div>` : `<div class="small-note">No card spending in this range.</div>`}
    </section>
    <section class="panel">
      ${panelHead("Recurring charges", "Subscription-like patterns", "", "repeat")}
      ${(spending.subscriptions || []).length ? `<div class="list">${spending.subscriptions.map((sub) => `<div class="list-row">
        <div class="list-icon">${icon("repeat")}</div><div class="list-main"><div class="list-title">${esc(sub.name)}</div><div class="list-sub">${sub.months} months · ${money(sub.average)}/mo</div></div>
        <div class="list-end"><div class="list-amount">${money(sub.annual_cost)}/yr</div></div>
      </div>`).join("")}</div>` : `<div class="small-note">No repeating charges detected yet. Import more months to improve detection.</div>`}
    </section>
  </div>

  <div class="dash-grid equal">
    <section class="panel">
      ${panelHead("Business vs personal", "Keep tax time simple", "", "tax")}
      <div class="head-bar"><span class="name">Business</span><div class="bar-track"><i style="width:${total ? (business / Math.max(business, personal, 1)) * 100 : 0}%;background:linear-gradient(90deg,#06b6d4,#6366f1)"></i></div><span class="val">${money(business)}</span></div>
      <div class="head-bar"><span class="name">Personal</span><div class="bar-track"><i style="width:${total ? (personal / Math.max(business, personal, 1)) * 100 : 0}%;background:linear-gradient(90deg,#f59e0b,#fb7185)"></i></div><span class="val">${money(personal)}</span></div>
      <div class="inline-note" style="margin-top:14px">${icon("info")}<div>Tag business purchases and deductible expenses on the transaction form. FinVault uses those tags for your tax estimate and business/personal split.</div></div>
    </section>
    <section class="panel">
      ${panelHead("Biggest transactions", "A quick sanity check", "", "transactions")}
      ${(spending.biggest || []).length ? `<div class="table-wrap"><table class="table table-compact"><tbody>${spending.biggest.map((tx) => `<tr>
        <td><div class="row-title">${esc(tx.description)}</div><div class="row-sub">${esc(dateText(tx.date))} · ${esc(tx.category)}</div></td>
        <td class="num neg">${money(tx.amount)}</td>
      </tr>`).join("")}</tbody></table></div>` : `<div class="small-note">No transactions in this range.</div>`}
    </section>
  </div>`;
}

export async function pagePeople() {
  const persons = await api("/persons");
  state.pageData.people = persons;
  const palette = ["#6366f1", "#06b6d4", "#f59e0b", "#ec4899", "#10b981", "#a78bfa"];

  return `${pageHead({
    eyebrow: "System",
    title: "People",
    subtitle: "Manage yourself, your wife, or anyone else whose finances you track. Every card, account, loan and tax return belongs to a person.",
    actions: `<button class="btn btn-primary" data-action="addPerson">${icon("plus")} Add person</button>`,
  })}
  <div class="cards-grid">${persons.map((person, index) => `
    <section class="panel" style="display:flex;flex-direction:column;gap:15px">
      <div style="display:flex;align-items:center;gap:13px">
        <div style="width:48px;height:48px;border-radius:14px;display:flex;align-items:center;justify-content:center;font-weight:750;font-size:16px;color:#fff;background:linear-gradient(135deg,${esc(person.color || palette[index % palette.length])},rgba(6,182,212,.75))">${esc(initialsSafe(person.name))}</div>
        <div><div class="row-title" style="font-size:15px">${esc(person.name)}</div><div class="row-sub">${esc(person.relationship || "person")} ${person.is_primary ? "· primary" : ""}</div></div>
        ${person.is_primary ? `<span class="tag success" style="margin-left:auto">Primary</span>` : ""}
      </div>
      <div class="stat-line"><span>Credit cards</span><strong>${person.card_count}</strong></div>
      <div class="stat-line"><span>Bank accounts</span><strong>${person.account_count}</strong></div>
      <div class="stat-line"><span>TIN</span><strong>${esc(person.tin || "—")}</strong></div>
      <div style="display:flex;gap:7px;margin-top:auto">
        <button class="btn btn-sm" data-action="filterPerson" data-id="${person.id}">${icon("eye")} View</button>
        <button class="btn btn-sm" data-action="editPerson" data-id="${person.id}">${icon("edit")} Edit</button>
        ${persons.length > 1 ? `<button class="icon-btn small danger" data-action="deletePerson" data-id="${person.id}" title="Delete">${icon("trash")}</button>` : ""}
      </div>
    </section>`).join("")}</div>
  <div class="inline-note" style="margin-top:18px">${icon("shield")}<div>Each person’s data is kept separate in reports but stored in the same private database. Use the person picker in the top bar to switch between individual and combined views.</div></div>`;
}

function initialsSafe(name) {
  return String(name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join("");
}

function fileSize(bytes) {
  const value = Number(bytes || 0);
  if (value > 1024 * 1024) return `${(value / 1024 / 1024).toFixed(1)} MB`;
  if (value > 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${value} B`;
}

export async function pageSettings() {
  const [stats, backups, fx] = await Promise.all([
    api("/admin/stats"), api("/admin/backups"), api("/fx"),
  ]);
  state.pageData.stats = stats;
  state.pageData.backups = backups;
  state.pageData.fx = fx;
  const settings = state.settings || {};
  const key = settings.api_key || "";
  const masked = state.showKey ? key : `${key.slice(0, 6)}${"•".repeat(Math.max(8, Math.min(28, key.length - 10)))}${key.slice(-4)}`;
  const baseUrl = `${window.location.origin}${CONFIG.base}`;
  const currencies = ["LKR", "USD", "EUR", "GBP", "INR", "AUD", "CAD", "AED", "SGD", "JPY", "CNY"];

  return `${pageHead({
    eyebrow: "System",
    title: "Settings",
    subtitle: "Currency, API access, exchange rates, backups and local data diagnostics.",
  })}
  <div class="settings-grid">
    <section class="panel">
      ${panelHead("General", "Defaults for the whole workspace", "", "settings")}
      <div class="form-grid">
        <div class="field"><label>Base currency</label><select class="select" id="setBaseCurrency">${options(currencies, settings.base_currency || "LKR")}</select></div>
        <div class="field"><label>Theme</label><select class="select" id="setTheme">${options([{ id: "dark", name: "Dark" }, { id: "light", name: "Light" }], settings.theme || "dark")}</select></div>
        <div class="field"><label>Auto-backup interval (hours)</label><input class="input" type="number" id="setBackupHours" min="1" max="720" value="${attr(settings.backup_interval_hours || "12")}"></div>
        <div class="field"><label>Quit when idle (minutes)</label><input class="input" type="number" id="setIdleQuit" min="0" max="1440" step="1" value="${attr(settings.idle_quit_minutes ?? "30")}"><div class="hint">0 = never. The app quits after this long with no open tab or API call.</div></div>
        <div class="field"><label>Tax year starts</label><select class="select" id="setFiscalMonth">${options([{ id: "1", name: "January" }, { id: "4", name: "April (Sri Lanka)" }, { id: "7", name: "July" }, { id: "10", name: "October" }], settings.fiscal_year_start_month || "4")}</select></div>
      </div>
      <div style="margin-top:14px"><button class="btn btn-primary" data-action="saveGeneral">${icon("check")} Save settings</button></div>
    </section>

    <section class="panel">
      ${panelHead("API access", "Let other applications read and write FinVault", `<a href="#/api" class="panel-link">Full docs →</a>`, "api")}
      <div class="api-base" style="margin-bottom:12px"><span style="flex:1">${esc(baseUrl)}</span><button class="icon-btn small" data-action="copyBaseUrl" data-value="${attr(baseUrl)}" title="Copy">${icon("copy")}</button></div>
      <div class="key-box"><span>${esc(masked)}</span>
        <button class="icon-btn small" data-action="toggleKey" title="Show / hide">${icon(state.showKey ? "eyeOff" : "eye")}</button>
        <button class="icon-btn small" data-action="copyKey" title="Copy API key">${icon("copy")}</button>
      </div>
      <div class="small-note" style="margin-top:8px">Send the key as <span class="mono">X-API-Key</span> or <span class="mono">Authorization: Bearer …</span>. The API listens on localhost only.</div>
      <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn btn-sm" data-action="copyKey">${icon("copy")} Copy key</button>
        <button class="btn btn-sm btn-danger" data-action="rotateKey">${icon("refresh")} Rotate key</button>
      </div>
    </section>
  </div>

  <div class="settings-grid" style="margin-top:14px">
    <section class="panel">
      ${panelHead("Exchange rates", "Value of 1 unit in your base currency", `<button class="btn btn-sm" data-action="saveFx">${icon("check")} Save rates</button>`, "refresh")}
      <div class="table-wrap"><table class="table table-compact">
        <thead><tr><th>Currency</th><th class="num">Rate to LKR</th></tr></thead>
        <tbody>${fx.map((row) => `<tr><td class="mono">${esc(row.currency)}</td><td class="num"><input class="input" style="height:30px;text-align:right;max-width:140px;margin-left:auto" type="number" step="0.000001" min="0.000001" value="${attr(row.rate)}" data-fx="${attr(row.currency)}"></td></tr>`).join("")}</tbody>
      </table></div>
      <div class="small-note" style="margin-top:8px">Used to convert foreign-currency cards and accounts into your base currency totals.</div>
    </section>

    <section class="panel">
      ${panelHead("Backups", `Automatic every ${esc(settings.backup_interval_hours || "12")} hours`, `<button class="btn btn-sm btn-primary" data-action="backupNow">${icon("download")} Backup now</button>`, "database")}
      <div id="backupList">${backups.length ? backups.slice(0, 8).map((backup) => `<div class="backup-row">
        <div class="list-icon">${icon("database")}</div>
        <div class="list-main"><div class="list-title">${esc(backup.name)}</div><div class="list-sub">${esc(backup.modified.replace("T", " "))} · ${fileSize(backup.size)}</div></div>
        <button class="icon-btn small" data-action="restoreBackup" data-name="${attr(backup.name)}" title="Restore this backup">${icon("refresh")}</button>
      </div>`).join("") : `<div class="small-note">No backups yet.</div>`}</div>
      <div class="inline-note warning" style="margin-top:12px">${icon("alert")}<div>Backups are stored in the <span class="mono">backups</span> folder next to FinVault. Restoring replaces the live database. A pre-restore backup is created automatically.</div></div>
    </section>
  </div>

  <section class="panel" style="margin-top:14px">
    ${panelHead("Local data", "Everything lives beside the application", "", "database")}
    <div class="settings-grid" style="grid-template-columns:1fr 1fr;gap:24px">
      <div>
        <div class="stat-line"><span>Database</span><strong class="mono" style="font-size:10px;word-break:break-all">${esc(stats.database_path)}</strong></div>
        <div class="stat-line"><span>Database size</span><strong>${fileSize(stats.database_size)}</strong></div>
        <div class="stat-line"><span>Integrity</span><strong class="${stats.integrity === "ok" ? "pos" : "neg"}">${esc(stats.integrity)}</strong></div>
        <div class="stat-line"><span>Records</span><strong>${Object.values(stats.counts).reduce((a, b) => a + Number(b || 0), 0)}</strong></div>
        <div class="stat-line"><span>App version</span><strong>${esc(stats.app_version)}</strong></div>
      </div>
      <div>
        <div class="settings-row"><div><div class="label">Export everything</div><div class="hint">Full JSON snapshot of all tables for safekeeping.</div></div><button class="btn btn-sm" data-action="exportJson">${icon("download")} JSON</button></div>
        <div class="settings-row"><div><div class="label">Export transactions</div><div class="hint">CSV of every transaction for spreadsheets.</div></div><button class="btn btn-sm" data-action="exportCsv">${icon("download")} CSV</button></div>
        <div class="settings-row"><div><div class="label">Export tax summary</div><div class="hint">Current tax year, ready for your accountant.</div></div><button class="btn btn-sm" data-action="exportTaxCurrent">${icon("download")} CSV</button></div>
        <div class="settings-row"><div><div class="label">Open data folder</div><div class="hint">Path: ${esc(stats.app_dir)}</div></div><button class="btn btn-sm" data-action="copyPath" data-value="${attr(stats.app_dir)}">${icon("copy")} Copy path</button></div>
      </div>
    </div>
  </section>

  <section class="panel" style="margin-top:14px">
    ${panelHead("Privacy & cloud sync", "Read this if the app lives in Google Drive", "", "shield")}
    <div class="settings-grid" style="grid-template-columns:1fr 1fr;gap:24px">
      <div class="privacy-note">${icon("shield")}<div>FinVault binds to <span class="mono">127.0.0.1</span> only. Nothing is uploaded anywhere. Your database is a single SQLite file beside the EXE.</div></div>
      <div class="inline-note warning">${icon("alert")}<div>Do not run the same copied app on two computers at once while Google Drive is syncing. Close FinVault before moving the folder. Keep the automatic backups — they are your safety net.</div></div>
    </div>
    <div class="divider"></div>
    <div class="settings-row">
      <div><div class="label">Quit FinVault</div><div class="hint">Stops the local server. Safe to close the browser tab afterwards.</div></div>
      <button class="btn btn-danger" data-action="quitApp">${icon("logout")} Quit app</button>
    </div>
  </section>`;
}

const API_GROUPS = [
  ["System", [
    ["GET", "/api/health", "Health check (no key required)"],
    ["GET", "/api/v1/bootstrap", "People, categories, FX and settings"],
    ["GET", "/api/v1/dashboard", "Dashboard summary, cards, trend, insights"],
    ["GET", "/api/v1/search?q=", "Search across all records"],
    ["GET", "/api/v1/export?format=json|csv&table=", "Export data"],
  ]],
  ["People & cards", [
    ["GET", "/api/v1/persons", "List people"],
    ["POST", "/api/v1/persons", "Create a person"],
    ["GET", "/api/v1/cards", "List cards with balances"],
    ["POST", "/api/v1/cards", "Create a card"],
    ["GET", "/api/v1/cards/{id}", "Card detail, statements, installments"],
    ["POST", "/api/v1/cards/{id}/payments", "Record a card payment"],
    ["GET", "/api/v1/accounts", "List bank accounts with balances"],
    ["POST", "/api/v1/accounts", "Create a bank account"],
  ]],
  ["Transactions", [
    ["GET", "/api/v1/transactions?from=&to=&card_id=&q=", "Filter transactions"],
    ["POST", "/api/v1/transactions", "Create a transaction"],
    ["GET", "/api/v1/transactions/{id}", "Transaction detail"],
    ["PUT", "/api/v1/transactions/{id}", "Update a transaction"],
    ["DELETE", "/api/v1/transactions/{id}", "Delete a transaction"],
    ["POST", "/api/v1/transfers", "Move money between accounts/cards"],
    ["POST", "/api/v1/import/transactions", "Bulk JSON import"],
    ["POST", "/api/v1/import/csv", "CSV statement import with mapping"],
    ["POST", "/api/v1/import/card-statement", "Statement + transactions in one call"],
  ]],
  ["Debt & plans", [
    ["GET", "/api/v1/statements", "List card statements"],
    ["POST", "/api/v1/statements/{id}/pay", "Pay a statement"],
    ["GET", "/api/v1/installments", "List installment plans"],
    ["POST", "/api/v1/installments/{id}/post", "Log one installment charge"],
    ["GET", "/api/v1/loans", "List loans with payoff projections"],
    ["POST", "/api/v1/loans/{id}/payments", "Record a loan payment"],
  ]],
  ["Reminders", [
    ["GET", "/api/v1/scheduled", "List scheduled transactions"],
    ["POST", "/api/v1/scheduled", "Create a reminder"],
    ["PUT", "/api/v1/scheduled/{id}", "Edit a reminder"],
    ["DELETE", "/api/v1/scheduled/{id}", "Delete a reminder"],
    ["POST", "/api/v1/scheduled/{id}/settle", "Mark paid; posts a transaction and advances the date"],
    ["GET", "/api/v1/reminders?days=21", "Overdue and imminent commitments"],
  ]],
  ["Wealth & income", [
    ["GET", "/api/v1/networth", "Net worth, assets, debts, history"],
    ["GET/POST", "/api/v1/assets", "List or create assets"],
    ["GET/POST", "/api/v1/liabilities", "List or create liabilities"],
    ["GET/POST", "/api/v1/incomes", "List or create income"],
    ["POST", "/api/v1/incomes/{id}/repeat", "Generate future income entries"],
  ]],
  ["Tax", [
    ["GET", "/api/v1/tax/estimate?person_id=&year_label=", "Sri Lankan tax estimate"],
    ["GET", "/api/v1/tax/years", "Available tax years and slabs"],
    ["PUT", "/api/v1/tax/rules/{year_label}", "Update slabs and reliefs"],
    ["GET/POST", "/api/v1/tax/reliefs", "Qualifying reliefs"],
    ["GET/POST", "/api/v1/tax/credits", "APIT / WHT credits"],
  ]],
  ["Analytics", [
    ["GET", "/api/v1/analytics/spending?from=&to=", "Categories, merchants, subscriptions"],
    ["GET", "/api/v1/insights", "Ranked recommendations"],
    ["GET", "/api/v1/admin/backup", "Create a database backup (POST)"],
    ["GET", "/api/v1/admin/backups", "List backups"],
  ]],
];

export async function pageApi() {
  const key = state.settings?.api_key || "";
  const base = `${window.location.origin}${CONFIG.base}`;
  const sampleKey = key || "YOUR_API_KEY";
  const curl = `curl -H "X-API-Key: ${sampleKey}" \\\n  "${base}/dashboard"`;
  const js = `const res = await fetch("${base}/transactions", {\n  method: "POST",\n  headers: {\n    "Content-Type": "application/json",\n    "X-API-Key": "${sampleKey}"\n  },\n  body: JSON.stringify({\n    card_id: 1,\n    date: "2026-11-16",\n    description: "Office supplies",\n    amount: 12500,\n    type: "purchase",\n    category_id: 18,\n    is_business: true,\n    tax_deductible: true\n  })\n});\nconst json = await res.json();`;

  return `${pageHead({
    eyebrow: "Developers",
    title: "API & integrations",
    subtitle: "Drive FinVault from another app, a script or an automation. Localhost only, key-protected, JSON in and JSON out.",
    actions: `<button class="btn" data-action="copyKey">${icon("copy")} Copy API key</button>`,
  })}
  <div class="settings-grid">
    <section class="panel">
      ${panelHead("Connection", "Everything you need to make the first call", "", "api")}
      <div class="field" style="margin-bottom:11px"><label>Base URL</label>
        <div class="api-base"><span style="flex:1">${esc(base)}</span><button class="icon-btn small" data-action="copyBaseUrl" data-value="${attr(base)}">${icon("copy")}</button></div>
      </div>
      <div class="field" style="margin-bottom:11px"><label>API key</label>
        <div class="key-box"><span>${esc(key)}</span><button class="icon-btn small" data-action="copyKey">${icon("copy")}</button></div>
      </div>
      <div class="inline-note">${icon("shield")}<div>Send the key as <span class="mono">X-API-Key</span> or <span class="mono">Authorization: Bearer &lt;key&gt;</span>. CORS is enabled for browser-based integrations. The server is bound to 127.0.0.1, so access is local to this machine.</div></div>
      <div class="small-note" style="margin-top:10px">Response envelope: <span class="mono">{ "ok": true, "data": … }</span>. Errors: <span class="mono">{ "ok": false, "error": { "message": … } }</span>.</div>
    </section>

    <section class="panel">
      ${panelHead("Quick start", "Copy, paste, call", "", "code")}
      <div class="section-title">curl</div>
      <div class="code-block">${esc(curl)}<button class="icon-btn small copy-code" data-action="copyText" data-text="${attr(curl)}">${icon("copy")}</button></div>
      <div class="section-title" style="margin-top:14px">JavaScript</div>
      <div class="code-block">${esc(js)}<button class="icon-btn small copy-code" data-action="copyText" data-text="${attr(js)}">${icon("copy")}</button></div>
    </section>
  </div>

  ${API_GROUPS.map(([group, endpoints]) => `<section class="panel" style="margin-top:14px">
    ${panelHead(group, `${endpoints.length} endpoint${endpoints.length === 1 ? "" : "s"}`, "", "api")}
    <div class="table-wrap"><table class="table endpoint-table">
      <thead><tr><th style="width:80px">Method</th><th>Endpoint</th><th>What it does</th></tr></thead>
      <tbody>${endpoints.map(([method, path, description]) => `<tr>
        <td>${method.split("/").map((m) => `<span class="method ${m}">${m}</span>`).join(" ")}</td>
        <td>${esc(path)}</td>
        <td style="font-family:var(--font);color:var(--muted)">${esc(description)}</td>
      </tr>`).join("")}</tbody>
    </table></div>
  </section>`).join("")}

  <section class="panel" style="margin-top:14px">
    ${panelHead("Sending me statements", "A workflow for bulk data entry", "", "upload")}
    <div class="small-note">Use <span class="mono">POST /api/v1/import/card-statement</span> to create a statement and all of its transactions in one call. Or send <span class="mono">POST /api/v1/import/transactions</span> with an array of transaction objects. Both accept category names (for example <span class="mono">"Business"</span>) as well as IDs.</div>
    <div class="small-note" style="margin-top:8px">When you share previous statements, I can build these payloads for you and load them into FinVault directly.</div>
  </section>`;
}

export function pageNotFound() {
  return `<div class="panel">${emptyState("search", "Page not found", "This page does not exist. Use the sidebar to get back.", `<a class="btn btn-primary" href="#/dashboard">${icon("dashboard")} Dashboard</a>`)}</div>`;
}
