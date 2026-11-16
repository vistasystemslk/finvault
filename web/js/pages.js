/* FinVault pages: dashboard, cards, transactions, accounts. */
import {
  api, state, money, shortMoney, pct, num, dateText, monthText, monthShort, daysLabel,
  icon, donut, ring, barChart, lineChart, emptyState, options, categoryOptions, progress,
  statusTag, esc, attr, personQuery, currentPersonId, typeLabel, pageHead, statCard,
  panelHead, creditCard, miniCard, signedAmount, categoryTag, errorPanel,
} from "./core.js";

function insightRows(insights, limit = 4) {
  return (insights || []).slice(0, limit).map((insight) => `
    <div class="insight ${esc(insight.severity)}">
      <div class="insight-icon">${icon(insight.severity === "success" ? "check" : insight.severity === "info" ? "sparkles" : "alert")}</div>
      <div class="insight-body">
        <div class="insight-title">${esc(insight.title)}</div>
        <div class="insight-text">${esc(insight.message)}</div>
        ${insight.action ? `<span class="insight-action" data-action="insightGo" data-page="${attr(insight.page || "")}" data-entity="${attr(insight.entity_id || "")}">${esc(insight.action)} →</span>` : ""}
      </div>
      ${insight.metric ? `<div class="insight-metric">${esc(insight.metric)}</div>` : ""}
    </div>`).join("");
}

function dueBadge(date) {
  if (!date) return `<div class="due-badge"><strong>—</strong><small>due</small></div>`;
  const parsed = new Date(`${date}T00:00:00`);
  const diff = daysLabel(date);
  const cls = diff.includes("overdue") ? "overdue" : diff === "Today" || diff === "Tomorrow" || /^in [1-7]d/.test(diff) ? "soon" : "";
  return `<div class="due-badge ${cls}"><strong>${parsed.getDate()}</strong><small>${parsed.toLocaleDateString("en-GB", { month: "short" })}</small></div>`;
}

function reminderBanner(items) {
  const urgent = (items || []).filter((item) => ["overdue", "today", "soon"].includes(item.status)).slice(0, 4);
  if (!urgent.length) return "";
  const label = { overdue: "Overdue", today: "Due today", soon: "Due soon" };
  return `<section class="panel reminder-panel" style="margin-bottom:16px">
    ${panelHead("Needs attention", `${urgent.length} item${urgent.length === 1 ? "" : "s"} overdue or due within 3 days`,
      `<span class="panel-link" data-action="goto" data-page="scheduled">Scheduled &amp; reminders →</span>`, "bell")}
    ${urgent.map((item) => `<div class="upcoming-row">
      ${dueBadge(item.due_date)}
      <div class="list-main">
        <div class="list-title">${esc(item.name)}</div>
        <div class="list-sub">${esc(item.detail || "")} · ${esc(daysLabel(item.due_date))}</div>
      </div>
      <div class="list-end">
        <div class="list-amount">${money(item.amount)}</div>
        <div class="list-meta">${esc(label[item.status] || item.status)}</div>
      </div>
    </div>`).join("")}
  </section>`;
}

function groupedCategories(items) {  const rows = (items || []).slice();
  if (rows.length <= 5) return rows;
  const top = rows.slice(0, 5);
  const rest = rows.slice(5).reduce((sum, row) => sum + Number(row.amount || 0), 0);
  if (rest > 0) top.push({ name: "Other", amount: rest, color: "#64748b" });
  return top;
}

function onboardingPanel() {
  const counts = state.counts || {};
  if (counts.transactions > 0) return "";
  return `<div class="onboarding">
    <div class="onboarding-main">
      <div class="eyebrow">Getting started</div>
      <h2>Let’s build your financial picture</h2>
      <p>Add your cards, bank accounts and income. Then import a statement or two — FinVault does the heavy lifting from there.</p>
    </div>
    <div class="onboarding-steps">
      <div class="step-chip" data-action="addCard"><span class="n">1</span> Add a credit card</div>
      <div class="step-chip" data-action="addAccount"><span class="n">2</span> Add a bank account</div>
      <div class="step-chip" data-action="addIncome"><span class="n">3</span> Add income</div>
      <div class="step-chip" data-action="importCsv"><span class="n">4</span> Import a statement</div>
    </div>
  </div>`;
}

export async function pageDashboard() {
  const [data, networth] = await Promise.all([
    api(`/dashboard${personQuery({ month: state.month })}`),
    api(`/networth${personQuery()}`),
  ]);
  state.pageData.dashboard = data;
  state.pageData.networth = networth;
  state.pageData.cardsRef = data.cards;
  state.pageData.accountsRef = data.accounts;

  const s = data.summary;
  const nw = networth.summary;
  const history = networth.history || [];
  const delta = history.length > 1
    ? Number(history[history.length - 1].net_worth || 0) - Number(history[history.length - 2].net_worth || 0)
    : null;
  const util = Number(s.credit_utilization || 0);
  const cats = groupedCategories(data.spend_by_category);
  const monthMax = Math.max(1, Number(s.month_income || 0), Number(s.month_expenses || 0));

  return `${pageHead({
    eyebrow: "Overview",
    title: "Dashboard",
    subtitle: `A live view of your money ${state.personId !== "all" ? `for ${esc(state.persons.find((p) => String(p.id) === String(state.personId))?.name || "")}` : "across everyone"}.`,
    actions: `<input class="input" type="month" value="${esc(state.month)}" style="width:155px" data-change="dashboardMonth" aria-label="Dashboard month">
      <button class="btn" data-action="refreshPage">${icon("refresh")} Refresh</button>
      <button class="btn btn-primary" data-action="addTransaction">${icon("plus")} Add transaction</button>`,
  })}
  ${onboardingPanel()}
  ${reminderBanner(data.reminders)}

  <div class="dash-hero">
    <section class="hero-card">
      <div class="hero-label">Total net worth</div>
      <div class="hero-value">${money(nw.net_worth)}</div>
      <div class="hero-delta ${delta !== null && delta < 0 ? "neg" : ""}">
        ${icon(delta !== null && delta < 0 ? "arrowDownRight" : "arrowUpRight")}
        ${delta === null ? "Tracking starts today" : `${delta >= 0 ? "+" : "−"}${money(Math.abs(delta))} since last snapshot`}
      </div>
      <div class="hero-meta">
        <div class="hero-meta-item"><span>Assets</span><strong>${money(nw.assets + nw.cash)}</strong></div>
        <div class="hero-meta-item"><span>Debts</span><strong class="neg">${money(nw.total_debt)}</strong></div>
        <div class="hero-meta-item"><span>Liquid</span><strong>${money(nw.liquid)}</strong></div>
      </div>
      <div class="hero-spark">${lineChart(history, { height: 64, minimal: true })}</div>
    </section>

    <section class="panel health-card">
      ${panelHead("Credit health", "Across active cards")}
      <div class="health-ring">${ring(util, 124, 12)}</div>
      <div class="health-meta">
        <div><span>Card debt</span><strong>${money(s.total_card_outstanding)}</strong></div>
        <div><span>Available</span><strong class="pos">${money(s.total_available_credit)}</strong></div>
      </div>
    </section>

    <section class="panel month-card">
      ${panelHead(monthText(data.month), "Income vs spending")}
      <div class="month-row"><span>Income</span><strong class="pos">${money(s.month_income)}</strong></div>
      <div class="progress green"><i style="width:${Math.max(2, (Number(s.month_income) / monthMax) * 100)}%"></i></div>
      <div class="month-row"><span>Spending</span><strong class="neg">${money(s.month_expenses)}</strong></div>
      <div class="progress red"><i style="width:${Math.max(2, (Number(s.month_expenses) / monthMax) * 100)}%"></i></div>
      <div class="month-net">
        <span>Net cash flow</span>
        <strong class="${Number(s.month_net) >= 0 ? "pos" : "neg"}">${money(s.month_net)}</strong>
        <div class="small-note">Savings rate ${pct(s.savings_rate)} · ${s.month_loan_payments ? `loan payments ${money(s.month_loan_payments)}` : "no loan payments"}</div>
      </div>
    </section>
  </div>

  <div class="stat-grid">
    ${statCard({ label: "Card outstanding", value: money(s.total_card_outstanding), foot: `${pct(util)} of ${money(s.total_credit_limit)} limit`, iconName: "cards", tone: "red" })}
    ${statCard({ label: "Available credit", value: money(s.total_available_credit), foot: `Min due ${money(s.minimum_due)}`, iconName: "shield", tone: "green" })}
    ${statCard({ label: "Bank balance", value: money(s.bank_balance), foot: `${data.accounts.length} account${data.accounts.length === 1 ? "" : "s"}`, iconName: "bank", tone: "cyan" })}
    ${statCard({ label: `Spend · ${monthShort(data.month)}`, value: money(s.month_expenses), foot: `Business ${money(s.month_business_spend)} · Tax deductible ${money(s.month_tax_deductible)}`, iconName: "transactions", tone: "amber" })}
  </div>

  <div class="dash-grid">
    <section class="panel">
      ${panelHead("Cash flow", "Income and expenses, last 6 months", `<div class="legend-inline"><span><i style="background:#10b981"></i>Income</span><span><i style="background:#fb7185"></i>Expenses</span></div>`, "insights")}
      ${barChart(data.trend || [])}
    </section>
    <section class="panel">
      ${panelHead("Where money went", monthText(data.month), `<span class="panel-link" data-action="goto" data-page="insights">Details →</span>`, "pie")}
      ${cats.length ? `<div class="donut-wrap">
        ${donut(cats, { size: 148, thickness: 16, centerLabel: "spent", centerValue: shortMoney(s.month_expenses) })}
        <div class="legend" style="flex:1;min-width:150px">
          ${cats.map((item) => `<div class="legend-row"><span class="swatch" style="background:${attr(item.color)}"></span><span class="name">${esc(item.name)}</span><span class="val">${money(item.amount)}</span></div>`).join("")}
        </div>
      </div>` : emptyState("pie", "No spending yet", "Purchases and expenses will be broken down here.")}
    </section>
  </div>

  <div class="dash-grid equal">
    <section class="panel">
      ${panelHead("Upcoming payments", "Next 45 days", `<span class="panel-link" data-action="goto" data-page="installments">Installments →</span>`, "calendar")}
      ${(data.upcoming || []).length ? (data.upcoming || []).slice(0, 6).map((item) => `
        <div class="upcoming-row">
          ${dueBadge(item.due_date)}
          <div class="list-main">
            <div class="list-title">${esc(item.name)}</div>
            <div class="list-sub">${esc(item.detail || "")} · ${esc(daysLabel(item.due_date))}</div>
          </div>
          <div class="list-end"><div class="list-amount">${money(item.amount)}</div><div class="list-meta">${esc(item.kind.replace("_", " "))}</div></div>
        </div>`).join("") : `<div class="empty" style="padding:24px"><div class="empty-icon">${icon("calendar")}</div><h3>Nothing due soon</h3><p>Statements, installments and loan payments will show up here.</p></div>`}
    </section>

    <section class="panel">
      ${panelHead("Insights & recommendations", "Based on your latest data", `<span class="panel-link" data-action="goto" data-page="insights">All insights →</span>`, "sparkles")}
      <div class="insights-list">${insightRows(data.insights, 4)}</div>
    </section>
  </div>

  <section class="panel" style="margin-bottom:16px">
    ${panelHead("Your cards", `${data.cards.length} card${data.cards.length === 1 ? "" : "s"}`, `<span class="panel-link" data-action="goto" data-page="cards">Manage cards →</span>`, "cards")}
    ${data.cards.length ? `<div class="mini-cards">${data.cards.slice(0, 6).map(miniCard).join("")}</div>` : emptyState("cards", "No cards yet", "Add your credit cards to track balances, utilization and due dates.", `<button class="btn btn-primary" data-action="addCard">${icon("plus")} Add your first card</button>`)}
  </section>

  <section class="panel">
    ${panelHead("Recent activity", "Latest transactions across cards and accounts", `<span class="panel-link" data-action="goto" data-page="transactions">View all →</span>`, "transactions")}
    ${(data.recent || []).length ? `<div class="table-wrap"><table class="table">
      <thead><tr><th>Date</th><th>Description</th><th>Source</th><th class="num">Amount</th></tr></thead>
      <tbody>${data.recent.map((tx) => `<tr>
        <td class="nowrap">${esc(dateText(tx.date))}</td>
        <td class="main-cell"><div class="row-title">${esc(tx.description || "—")}</div><div class="row-sub">${categoryTag(tx.category_id)}${tx.is_business ? ` <span class="tag business">Business</span>` : ""}</div></td>
        <td>${esc(tx.card_name || tx.account_name || "Cash")}</td>
        <td class="num ${tx.direction === "in" ? "pos" : ""}">${signedAmount(tx.amount, tx.direction, tx.currency)}</td>
      </tr>`).join("")}</tbody>
    </table></div>` : emptyState("transactions", "No transactions yet", "Add a transaction or import a credit card statement.", `<button class="btn btn-primary" data-action="addTransaction">${icon("plus")} Add transaction</button><button class="btn" data-action="importCsv">${icon("upload")} Import CSV</button>`)}
  </section>`;
}

export async function pageCards() {
  const [cards, accounts] = await Promise.all([api(`/cards${personQuery()}`), api(`/accounts${personQuery()}`)]);
  state.pageData.cardsRef = cards;
  state.pageData.accountsRef = accounts;
  const totalOut = cards.reduce((sum, card) => sum + Number(card.outstanding || 0), 0);
  const totalLimit = cards.reduce((sum, card) => sum + Number(card.credit_limit || 0), 0);
  const util = totalLimit ? (totalOut / totalLimit) * 100 : 0;
  const active = cards.filter((card) => card.status === "active");
  const closed = cards.filter((card) => card.status !== "active");

  return `${pageHead({
    eyebrow: "Money",
    title: "Credit cards",
    subtitle: "Balances, limits, statements and utilization for every card in one place.",
    actions: `<button class="btn btn-primary" data-action="addCard">${icon("plus")} Add card</button>`,
  })}
  <div class="stat-grid">
    ${statCard({ label: "Total outstanding", value: money(totalOut), foot: `${pct(util)} of combined limit`, iconName: "cards", tone: "red" })}
    ${statCard({ label: "Total credit limit", value: money(totalLimit), foot: `${active.length} active card${active.length === 1 ? "" : "s"}`, iconName: "shield" })}
    ${statCard({ label: "Available credit", value: money(Math.max(0, totalLimit - totalOut)), foot: "Across all active cards", iconName: "wallet", tone: "green" })}
    ${statCard({ label: "Average utilization", value: pct(util), foot: util >= 30 ? "Aim for below 30%" : "Healthy range", iconName: "pie", tone: util >= 75 ? "red" : util >= 30 ? "amber" : "green" })}
  </div>

  ${active.length ? `<div class="cards-grid">${active.map((card) => creditCard(card)).join("")}</div>` :
    emptyState("cards", "No active cards", "Add a credit card to start tracking spending, statements and installments.", `<button class="btn btn-primary" data-action="addCard">${icon("plus")} Add card</button>`)}
  ${closed.length ? `<div class="section-title" style="margin-top:24px">Closed cards</div><div class="cards-grid">${closed.map((card) => creditCard(card)).join("")}</div>` : ""}`;
}

export async function pageCardDetail(id) {
  const card = await api(`/cards/${id}`);
  state.pageData.card = card;
  const unpaid = (card.statements || []).find((row) => ["unpaid", "partial", "overdue"].includes(row.effective_status));
  const dueAmount = unpaid ? Math.max(0, Number(unpaid.closing_balance) - Number(unpaid.amount_paid)) : Number(card.outstanding || 0);
  const dueDate = unpaid?.due_date || "";
  const tab = state.cardTab || "transactions";

  const tabs = `<div class="tabs">
    ${["transactions", "statements", "installments"].map((name) =>
      `<button class="tab ${tab === name ? "active" : ""}" data-action="cardTab" data-tab="${name}">${name[0].toUpperCase() + name.slice(1)}</button>`).join("")}
  </div>`;

  let tabBody = "";
  if (tab === "transactions") {
    tabBody = (card.recent_transactions || []).length ? `<div class="table-wrap"><table class="table">
      <thead><tr><th>Date</th><th>Description</th><th>Type</th><th class="num">Amount</th><th class="actions-cell"></th></tr></thead>
      <tbody>${card.recent_transactions.map((tx) => `<tr>
        <td class="nowrap">${esc(dateText(tx.date))}</td>
        <td class="main-cell"><div class="row-title">${esc(tx.description || "—")}</div><div class="row-sub">${categoryTag(tx.category_id)} ${tx.is_business ? `<span class="tag business">Business</span>` : ""} ${tx.tax_deductible ? `<span class="tag deductible">Deductible</span>` : ""}</div></td>
        <td><span class="tag neutral">${esc(typeLabel(tx.type))}</span></td>
        <td class="num ${tx.direction === "in" ? "pos" : ""}">${signedAmount(tx.amount, tx.direction, tx.currency)}</td>
        <td class="actions-cell"><button class="icon-btn small" data-action="editTransaction" data-id="${tx.id}" title="Edit">${icon("edit")}</button>
          <button class="icon-btn small danger" data-action="deleteTransaction" data-id="${tx.id}" title="Delete">${icon("trash")}</button></td>
      </tr>`).join("")}</tbody></table></div>` : emptyState("transactions", "No transactions on this card", "Add a purchase or import a statement.", `<button class="btn btn-primary" data-action="addTransaction" data-card-id="${card.id}">${icon("plus")} Add transaction</button>`);
  } else if (tab === "statements") {
    tabBody = (card.statements || []).length ? `<div class="table-wrap"><table class="table">
      <thead><tr><th>Statement</th><th>Due</th><th>Closing</th><th>Remaining</th><th>Status</th><th class="actions-cell"></th></tr></thead>
      <tbody>${card.statements.map((row) => `<tr>
        <td><div class="row-title">${esc(dateText(row.statement_date))}</div><div class="row-sub">${row.period_start ? `${esc(dateText(row.period_start, "short"))} – ${esc(dateText(row.period_end, "short"))}` : ""}</div></td>
        <td>${esc(dateText(row.due_date))}<div class="row-sub">${esc(daysLabel(row.due_date))}</div></td>
        <td class="num">${money(row.closing_balance, card.currency)}</td>
        <td class="num">${money(row.remaining, card.currency)}</td>
        <td>${statusTag(row.effective_status)}</td>
        <td class="actions-cell">
          ${row.remaining > 0 ? `<button class="btn btn-sm btn-success" data-action="payStatement" data-id="${row.id}" data-card-id="${card.id}">Pay</button>` : ""}
          <button class="icon-btn small" data-action="editStatement" data-id="${row.id}" title="Edit">${icon("edit")}</button>
          <button class="icon-btn small danger" data-action="deleteStatement" data-id="${row.id}" title="Delete">${icon("trash")}</button>
        </td>
      </tr>`).join("")}</tbody></table></div>` : emptyState("receipt", "No statements yet", "Add statements to track due dates, minimum payments and balances.", `<button class="btn btn-primary" data-action="addStatement" data-card-id="${card.id}">${icon("plus")} Add statement</button>`);
  } else {
    tabBody = (card.installment_plans || []).length ? `<div class="table-wrap"><table class="table">
      <thead><tr><th>Plan</th><th>Monthly</th><th>Remaining</th><th>Progress</th><th class="actions-cell"></th></tr></thead>
      <tbody>${card.installment_plans.map((plan) => `<tr>
        <td><div class="row-title">${esc(plan.description)}</div><div class="row-sub">${plan.months} months · started ${esc(dateText(plan.start_date))}</div></td>
        <td class="num">${money(plan.monthly_amount, card.currency)}</td>
        <td class="num">${plan.remaining_months} / ${plan.months}</td>
        <td style="min-width:120px"><div class="progress-row">${progress(((plan.months - plan.remaining_months) / plan.months) * 100)}<span>${Math.round(((plan.months - plan.remaining_months) / plan.months) * 100)}%</span></div></td>
        <td class="actions-cell"><button class="icon-btn small" data-action="editInstallment" data-id="${plan.id}" title="Edit">${icon("edit")}</button></td>
      </tr>`).join("")}</tbody></table></div>` : emptyState("installments", "No installment plans", "Track installment purchases and their monthly commitment.", `<button class="btn btn-primary" data-action="addInstallment" data-card-id="${card.id}">${icon("plus")} Add plan</button>`);
  }

  return `<div class="back-link" data-action="goto" data-page="cards">${icon("arrowLeft")} Back to cards</div>
  ${pageHead({
    eyebrow: `${esc(card.person_name || "")} · ${esc(card.purpose || "personal")}`,
    title: card.name,
    subtitle: `${esc(card.issuer || "Credit card")}${card.last4 ? ` · ending ${esc(card.last4)}` : ""} · ${esc(card.currency)}`,
    actions: `<button class="btn" data-action="addTransaction" data-card-id="${card.id}">${icon("plus")} Transaction</button>
      <button class="btn btn-success" data-action="payCard" data-id="${card.id}">${icon("wallet")} Pay card</button>
      <button class="btn" data-action="addStatement" data-card-id="${card.id}">${icon("receipt")} Statement</button>
      <button class="icon-btn" data-action="editCard" data-id="${card.id}" title="Edit card">${icon("edit")}</button>
      <button class="icon-btn danger" data-action="deleteCard" data-id="${card.id}" title="Delete card">${icon("trash")}</button>`,
  })}

  <div class="detail-hero">
    ${creditCard(card, { large: true })}
    <div class="detail-stats">
      <div class="detail-stat"><span>Outstanding</span><strong>${money(card.outstanding, card.currency)}</strong><small>${money(card.outstanding_base)} in LKR</small></div>
      <div class="detail-stat"><span>Available</span><strong class="pos">${money(card.available, card.currency)}</strong><small>of ${money(card.credit_limit, card.currency)}</small></div>
      <div class="detail-stat"><span>Utilization</span><strong class="${card.utilization >= 75 ? "neg" : card.utilization >= 30 ? "warn" : "pos"}">${pct(card.utilization)}</strong><small>${card.utilization >= 30 ? "Aim for below 30%" : "Healthy"}</small></div>
      <div class="detail-stat"><span>Payment due</span><strong>${money(dueAmount, card.currency)}</strong><small>${dueDate ? `${dateText(dueDate)} · ${daysLabel(dueDate)}` : "No statement due"}</small></div>
      <div class="detail-stat"><span>Interest rate</span><strong>${pct(card.apr)}</strong><small>Annual percentage rate</small></div>
      <div class="detail-stat"><span>Statement / due day</span><strong>${card.statement_day || "—"} / ${card.due_day || "—"}</strong><small>Day of each month</small></div>
    </div>
  </div>

  <section class="panel">
    ${panelHead("Card activity", `${esc(card.name)} · ${esc(card.issuer || "")}`, `<button class="btn btn-sm" data-action="refreshPage">${icon("refresh")} Refresh</button>`)}
    ${tabs}
    ${tabBody}
  </section>`;
}

export async function pageTransactions() {
  const [cards, accounts] = await Promise.all([api(`/cards${personQuery()}`), api(`/accounts${personQuery()}`)]);
  state.pageData.cardsRef = cards;
  state.pageData.accountsRef = accounts;

  const params = new URLSearchParams();
  if (state.personId !== "all") params.set("person_id", state.personId);
  for (const [key, value] of Object.entries(state.txFilters)) {
    if (value !== "" && value !== null) params.set(key, value);
  }
  params.set("limit", String(state.txLimit));
  params.set("offset", String(state.txOffset));
  const data = await api(`/transactions?${params.toString()}`);
  state.pageData.transactions = data;

  const filters = state.txFilters;
  const cardName = (id) => cards.find((card) => String(card.id) === String(id))?.name;
  const accountName = (id) => accounts.find((account) => String(account.id) === String(id))?.name;
  const page = Math.floor(state.txOffset / state.txLimit) + 1;
  const pages = Math.max(1, Math.ceil(data.total / state.txLimit));

  return `${pageHead({
    eyebrow: "Money",
    title: "Transactions",
    subtitle: "Every purchase, payment, fee and transfer — searchable and filterable.",
    actions: `<button class="btn" data-action="importCsv">${icon("upload")} Import</button>
      <button class="btn btn-primary" data-action="addTransaction">${icon("plus")} Add transaction</button>`,
  })}

  <div class="toolbar">
    <input class="input search-input" type="search" placeholder="Search descriptions, notes, tags…" value="${attr(filters.q)}" data-filter="q" aria-label="Search transactions">
    <select class="select" data-filter="card_id" aria-label="Filter by card" style="width:160px">
      ${options([{ id: "", name: "All cards" }, ...cards], filters.card_id, { placeholder: "" })}
    </select>
    <select class="select" data-filter="account_id" aria-label="Filter by account" style="width:160px">
      ${options([{ id: "", name: "All accounts" }, ...accounts], filters.account_id, { placeholder: "" })}
    </select>
    <select class="select" data-filter="type" aria-label="Filter by type" style="width:145px">
      ${options([
        { id: "", name: "All types" }, { id: "purchase", name: "Purchases" }, { id: "payment", name: "Payments" },
        { id: "installment", name: "Installments" }, { id: "fee", name: "Fees" }, { id: "interest", name: "Interest" },
        { id: "refund", name: "Refunds" }, { id: "transfer", name: "Transfers" },
      ], filters.type)}
    </select>
    <select class="select" data-filter="business" aria-label="Business filter" style="width:135px">
      ${options([{ id: "", name: "Business + personal" }, { id: "1", name: "Business only" }, { id: "0", name: "Personal only" }], filters.business)}
    </select>
    <input class="input" type="month" data-filter="month" value="${attr(filters.month)}" aria-label="Filter by month" style="width:145px">
    <button class="btn btn-sm btn-ghost" data-action="clearTxFilters">${icon("close")} Clear</button>
    <div class="toolbar-sep"></div>
    <span class="metric-inline">${num(data.total)} result${data.total === 1 ? "" : "s"}</span>
  </div>

  <section class="panel">
    <div class="split-head">
      <div class="legend-inline">
        <span class="pos">In ${money(data.summary.in)}</span>
        <span class="neg">Out ${money(data.summary.out)}</span>
        <span class="muted">Net ${money(data.summary.net)}</span>
      </div>
      <span class="small-note">${page} / ${pages}</span>
    </div>
    ${data.items.length ? `<div class="table-wrap"><table class="table">
      <thead><tr><th>Date</th><th>Description</th><th>Source</th><th>Type</th><th>Flags</th><th class="num">Amount</th><th class="actions-cell"></th></tr></thead>
      <tbody>${data.items.map((tx) => `<tr>
        <td class="nowrap">${esc(dateText(tx.date))}</td>
        <td class="main-cell"><div class="row-title">${esc(tx.description || "—")}</div><div class="row-sub">${categoryTag(tx.category_id)}${tx.notes ? ` · ${esc(tx.notes)}` : ""}</div></td>
        <td>${esc(tx.card_name || tx.account_name || "Cash")}</td>
        <td><span class="tag neutral">${esc(typeLabel(tx.type))}</span></td>
        <td>${tx.is_business ? `<span class="tag business">Business</span>` : ""} ${tx.tax_deductible ? `<span class="tag deductible">Deductible</span>` : ""} ${tx.transfer_group ? `<span class="tag">Transfer</span>` : ""}</td>
        <td class="num ${tx.direction === "in" ? "pos" : ""}">${signedAmount(tx.amount, tx.direction, tx.currency)}</td>
        <td class="actions-cell"><button class="icon-btn small" data-action="editTransaction" data-id="${tx.id}" title="Edit">${icon("edit")}</button>
          <button class="icon-btn small danger" data-action="deleteTransaction" data-id="${tx.id}" title="Delete">${icon("trash")}</button></td>
      </tr>`).join("")}</tbody></table></div>` : emptyState("transactions", "No matching transactions", "Try clearing filters, or add a new transaction.", `<button class="btn btn-primary" data-action="addTransaction">${icon("plus")} Add transaction</button>`)}
    <div class="pagination">
      <span>Showing ${data.total ? state.txOffset + 1 : 0}–${Math.min(state.txOffset + data.items.length, data.total)} of ${num(data.total)}</span>
      <div style="display:flex;gap:7px">
        <button class="btn btn-sm" data-action="txPage" data-offset="${Math.max(0, state.txOffset - state.txLimit)}" ${state.txOffset === 0 ? "disabled" : ""}>${icon("chevronLeft")} Previous</button>
        <button class="btn btn-sm" data-action="txPage" data-offset="${state.txOffset + state.txLimit}" ${state.txOffset + state.txLimit >= data.total ? "disabled" : ""}>Next ${icon("chevronRight")}</button>
      </div>
    </div>
  </section>`;
}

export async function pageAccounts() {
  const [accounts, cards] = await Promise.all([api(`/accounts${personQuery()}`), api(`/cards${personQuery()}`)]);
  state.pageData.accountsRef = accounts;
  state.pageData.cardsRef = cards;
  const total = accounts.reduce((sum, account) => sum + Number(account.balance_base || 0), 0);
  const active = accounts.filter((account) => account.is_active);
  const typeIcons = { savings: "wallet", current: "bank", fixed: "shield", cash: "wallet", wallet: "wallet", investment: "income", other: "bank" };

  return `${pageHead({
    eyebrow: "Money",
    title: "Bank accounts",
    subtitle: "Savings, current accounts, cash and wallets — with live balances.",
    actions: `<button class="btn" data-action="transfer">${icon("repeat")} Transfer</button>
      <button class="btn btn-primary" data-action="addAccount">${icon("plus")} Add account</button>`,
  })}
  <div class="stat-grid">
    ${statCard({ label: "Total bank balance", value: money(total), foot: `${active.length} active account${active.length === 1 ? "" : "s"}`, iconName: "bank", tone: "cyan" })}
    ${statCard({ label: "Liquid cash", value: money(accounts.filter((a) => ["savings", "current", "cash", "wallet"].includes(a.type)).reduce((sum, a) => sum + Number(a.balance_base || 0), 0)), foot: "Savings, current, cash & wallets", iconName: "wallet", tone: "green" })}
    ${statCard({ label: "Fixed / investments", value: money(accounts.filter((a) => ["fixed", "investment"].includes(a.type)).reduce((sum, a) => sum + Number(a.balance_base || 0), 0)), foot: "Locked or invested funds", iconName: "shield" })}
    ${statCard({ label: "Accounts", value: num(accounts.length), foot: "Across all selected people", iconName: "accounts" })}
  </div>

  ${accounts.length ? `<div class="cards-grid">${accounts.map((account) => `
    <section class="panel" style="display:flex;flex-direction:column;gap:14px">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:10px">
        <div style="display:flex;gap:11px;align-items:center">
          <div class="list-icon">${icon(typeIcons[account.type] || "bank")}</div>
          <div><div class="row-title">${esc(account.name)}</div><div class="row-sub">${esc(account.institution || "—")} · ${esc(account.type)}</div></div>
        </div>
        ${account.is_active ? `<span class="tag success">Active</span>` : `<span class="tag neutral">Inactive</span>`}
      </div>
      <div>
        <div class="hero-label">Balance</div>
        <div style="font-size:26px;font-weight:730;letter-spacing:-.04em;margin-top:3px">${money(account.balance, account.currency)}</div>
        <div class="small-note">${account.currency !== "LKR" ? `${money(account.balance_base)} in LKR` : (account.account_number ? `A/C ${esc(account.account_number)}` : "—")}</div>
      </div>
      <div style="display:flex;gap:7px;margin-top:auto;flex-wrap:wrap">
        <button class="btn btn-sm" data-action="editAccount" data-id="${account.id}">${icon("edit")} Edit</button>
        <button class="btn btn-sm" data-action="transferFrom" data-id="${account.id}">${icon("repeat")} Transfer</button>
        <button class="icon-btn small danger" data-action="deleteAccount" data-id="${account.id}" title="Delete">${icon("trash")}</button>
      </div>
    </section>`).join("")}</div>` : emptyState("bank", "No bank accounts", "Add your savings, current accounts or cash wallet to see your real liquidity.", `<button class="btn btn-primary" data-action="addAccount">${icon("plus")} Add account</button>`)}`;
}
