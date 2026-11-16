/* FinVault pages: installments, loans, net worth, income. */
import {
  api, state, money, shortMoney, pct, num, dateText, monthText, daysLabel, icon, donut,
  ring, lineChart, emptyState, options, progress, statusTag, esc, attr, personQuery,
  pageHead, statCard, panelHead, errorPanel,
} from "./core.js";

export async function pageInstallments() {
  const [plans, cards] = await Promise.all([api(`/installments${personQuery()}`), api(`/cards${personQuery()}`)]);
  state.pageData.cardsRef = cards;
  state.pageData.installments = plans;
  const active = plans.filter((plan) => plan.status === "active");
  const monthly = active.reduce((sum, plan) => sum + Number(plan.monthly_amount || 0), 0);
  const remaining = active.reduce((sum, plan) => sum + Number(plan.remaining_amount || 0), 0);
  const months = active.reduce((sum, plan) => sum + Number(plan.remaining_months || 0), 0);

  return `${pageHead({
    eyebrow: "Plan",
    title: "Installment plans",
    subtitle: "See the true monthly commitment of every installment purchase.",
    actions: `<button class="btn btn-primary" data-action="addInstallment">${icon("plus")} Add plan</button>`,
  })}
  <div class="stat-grid">
    ${statCard({ label: "Monthly commitment", value: money(monthly), foot: `${active.length} active plan${active.length === 1 ? "" : "s"}`, iconName: "calendar", tone: "amber" })}
    ${statCard({ label: "Remaining balance", value: money(remaining), foot: "Future installment charges", iconName: "receipt", tone: "red" })}
    ${statCard({ label: "Monthly plans", value: num(active.length), foot: "Across all selected cards", iconName: "installments" })}
    ${statCard({ label: "Months remaining", value: num(months), foot: "Combined plan duration", iconName: "clock" })}
  </div>

  <section class="panel">
    ${panelHead("All plans", "Installment charges are added to the card when you log a month", `<button class="btn btn-sm" data-action="refreshPage">${icon("refresh")} Refresh</button>`, "installments")}
    ${plans.length ? `<div class="table-wrap"><table class="table">
      <thead><tr><th>Plan</th><th>Card</th><th class="num">Monthly</th><th>Remaining</th><th class="num">Balance</th><th>Status</th><th class="actions-cell"></th></tr></thead>
      <tbody>${plans.map((plan) => `<tr>
        <td class="main-cell"><div class="row-title">${esc(plan.description)}</div><div class="row-sub">${esc(dateText(plan.start_date))} · ${plan.months} months</div></td>
        <td>${esc(plan.card_name)}</td>
        <td class="num">${money(plan.monthly_amount, plan.currency)}</td>
        <td style="min-width:140px">
          <div class="progress-row">${progress(((plan.months - plan.remaining_months) / Math.max(1, plan.months)) * 100, plan.remaining_months === 0 ? "green" : "")}<span>${plan.remaining_months}/${plan.months}</span></div>
          <div class="row-sub">${plan.remaining_months} month${plan.remaining_months === 1 ? "" : "s"} left</div>
        </td>
        <td class="num">${money(plan.remaining_amount, plan.currency)}</td>
        <td>${statusTag(plan.status)}</td>
        <td class="actions-cell">
          ${plan.status === "active" && plan.remaining_months > 0 ? `<button class="btn btn-sm" data-action="postInstallment" data-id="${plan.id}">Log charge</button>` : ""}
          <button class="icon-btn small" data-action="editInstallment" data-id="${plan.id}" title="Edit">${icon("edit")}</button>
          <button class="icon-btn small danger" data-action="deleteInstallment" data-id="${plan.id}" title="Delete">${icon("trash")}</button>
        </td>
      </tr>`).join("")}</tbody></table></div>` : emptyState("installments", "No installment plans", "Add a plan for a purchase you are paying off monthly.", `<button class="btn btn-primary" data-action="addInstallment">${icon("plus")} Add plan</button>`)}
  </section>`;
}

export async function pageLoans() {
  const loans = await api(`/loans${personQuery()}`);
  state.pageData.loans = loans;
  const active = loans.filter((loan) => loan.status === "active");
  const outstanding = active.reduce((sum, loan) => sum + Number(loan.outstanding || 0), 0);
  const monthly = active.reduce((sum, loan) => sum + Number(loan.monthly_payment || 0), 0);
  const interest = active.reduce((sum, loan) => sum + Number(loan.projection_interest || 0), 0);
  const typeIcons = { personal: "wallet", vehicle: "cards", housing: "bank", lease: "repeat", education: "tax", business: "income", other: "loans" };

  return `${pageHead({
    eyebrow: "Plan",
    title: "Loans",
    subtitle: "Personal loans, vehicle leases, housing loans and payoff projections.",
    actions: `<button class="btn btn-primary" data-action="addLoan">${icon("plus")} Add loan</button>`,
  })}
  <div class="stat-grid">
    ${statCard({ label: "Outstanding loans", value: money(outstanding), foot: `${active.length} active loan${active.length === 1 ? "" : "s"}`, iconName: "loans", tone: "red" })}
    ${statCard({ label: "Monthly payments", value: money(monthly), foot: "Scheduled loan repayments", iconName: "calendar", tone: "amber" })}
    ${statCard({ label: "Projected interest", value: money(interest), foot: "If you keep paying as scheduled", iconName: "percent", tone: "amber" })}
    ${statCard({ label: "Total paid", value: money(loans.reduce((sum, loan) => sum + Number(loan.total_paid || 0), 0)), foot: "Across all loan payments", iconName: "check", tone: "green" })}
  </div>

  ${loans.length ? `<div class="dash-grid equal">${loans.map((loan) => {
    const paidRatio = Number(loan.principal) ? Math.max(0, Math.min(100, (1 - Number(loan.outstanding) / Number(loan.principal)) * 100)) : 0;
    return `<section class="panel" style="cursor:pointer" data-action="openLoan" data-id="${loan.id}">
      <div class="panel-head">
        <div style="display:flex;gap:11px;align-items:center">
          <div class="list-icon">${icon(typeIcons[loan.type] || "loans")}</div>
          <div><div class="panel-title">${esc(loan.name)}</div><div class="panel-sub">${esc(loan.lender || loan.type)} · ${esc(loan.person_name || "")}</div></div>
        </div>
        ${statusTag(loan.status)}
      </div>
      <div style="display:flex;align-items:flex-end;justify-content:space-between;gap:10px;margin-bottom:12px">
        <div><div class="hero-label">Outstanding</div><div style="font-size:25px;font-weight:730;letter-spacing:-.04em;margin-top:3px">${money(loan.outstanding, loan.currency)}</div></div>
        <div class="right"><div class="small-note">Monthly</div><div style="font-weight:650">${money(loan.monthly_payment, loan.currency)}</div></div>
      </div>
      <div class="progress-row">${progress(paidRatio, paidRatio >= 100 ? "green" : "")}<span>${paidRatio.toFixed(0)}%</span></div>
      <div class="small-note" style="margin-top:8px">${loan.annual_rate}% APR · ${loan.projection_months ? `${loan.projection_months} months to clear` : "payment too low to clear"} · ${loan.next_due_date ? `next due ${dateText(loan.next_due_date, "short")}` : "no due date"}</div>
    </section>`;
  }).join("")}</div>` : emptyState("loans", "No loans", "Add a personal loan or lease to include it in your net worth and cash flow.", `<button class="btn btn-primary" data-action="addLoan">${icon("plus")} Add loan</button>`)}`;
}

export async function pageLoanDetail(id) {
  const loan = await api(`/loans/${id}`);
  state.pageData.loan = loan;
  const paidRatio = Number(loan.principal) ? Math.max(0, Math.min(100, (1 - Number(loan.outstanding) / Number(loan.principal)) * 100)) : 0;
  const schedule = loan.amortization?.schedule || [];
  const payments = loan.payments || [];

  return `<div class="back-link" data-action="goto" data-page="loans">${icon("arrowLeft")} Back to loans</div>
  ${pageHead({
    eyebrow: `${esc(loan.person_name || "")} · ${esc(loan.type)}`,
    title: loan.name,
    subtitle: `${esc(loan.lender || "Lender")} · ${loan.annual_rate}% APR · ${money(loan.monthly_payment, loan.currency)} monthly`,
    actions: `<button class="btn btn-success" data-action="addLoanPayment" data-id="${loan.id}">${icon("wallet")} Record payment</button>
      <button class="icon-btn" data-action="editLoan" data-id="${loan.id}" title="Edit">${icon("edit")}</button>
      <button class="icon-btn danger" data-action="deleteLoan" data-id="${loan.id}" title="Delete">${icon("trash")}</button>`,
  })}

  <div class="stat-grid">
    ${statCard({ label: "Outstanding", value: money(loan.outstanding, loan.currency), foot: `of ${money(loan.principal, loan.currency)} original`, iconName: "loans", tone: "red" })}
    ${statCard({ label: "Monthly payment", value: money(loan.monthly_payment, loan.currency), foot: loan.next_due_date ? `Next due ${dateText(loan.next_due_date)}` : "No next due date", iconName: "calendar" })}
    ${statCard({ label: "Months to clear", value: loan.amortization?.months ? num(loan.amortization.months) : "—", foot: loan.projection_warning || "Based on current payment", iconName: "clock", tone: loan.projection_warning ? "amber" : "" })}
    ${statCard({ label: "Projected interest", value: money(loan.amortization?.total_interest || 0, loan.currency), foot: `${paidRatio.toFixed(0)}% of principal repaid`, iconName: "percent", tone: "amber" })}
  </div>

  <div class="dash-grid equal">
    <section class="panel">
      ${panelHead("Payoff projection", "Interest and principal by month", `<button class="btn btn-sm" data-action="addLoanPayment" data-id="${loan.id}">${icon("plus")} Payment</button>`, "insights")}
      ${schedule.length ? `<div class="table-wrap" style="max-height:390px;overflow:auto"><table class="table table-compact">
        <thead><tr><th>#</th><th class="num">Payment</th><th class="num">Interest</th><th class="num">Principal</th><th class="num">Balance</th></tr></thead>
        <tbody>${schedule.slice(0, 60).map((row) => `<tr><td>${row.month}</td><td class="num">${money(row.payment, loan.currency)}</td><td class="num neg">${money(row.interest, loan.currency)}</td><td class="num pos">${money(row.principal, loan.currency)}</td><td class="num">${money(row.balance, loan.currency)}</td></tr>`).join("")}</tbody>
      </table></div>${schedule.length > 60 ? `<div class="small-note" style="margin-top:8px">Showing first 60 of ${schedule.length} months.</div>` : ""}` : `<div class="empty" style="padding:24px"><p>Add a monthly payment to see the payoff schedule.</p></div>`}
    </section>

    <section class="panel">
      ${panelHead("Payment history", `${payments.length} payment${payments.length === 1 ? "" : "s"} recorded`, "", "receipt")}
      ${payments.length ? `<div class="table-wrap"><table class="table table-compact">
        <thead><tr><th>Date</th><th class="num">Amount</th><th class="num">Principal</th><th class="num">Interest</th></tr></thead>
        <tbody>${payments.map((payment) => `<tr>
          <td>${esc(dateText(payment.date))}</td><td class="num">${money(payment.amount, loan.currency)}</td>
          <td class="num pos">${money(payment.principal_component, loan.currency)}</td>
          <td class="num neg">${money(payment.interest_component, loan.currency)}</td>
        </tr>`).join("")}</tbody></table></div>` : emptyState("receipt", "No payments yet", "Record a payment to update the outstanding balance.", `<button class="btn btn-primary" data-action="addLoanPayment" data-id="${loan.id}">${icon("plus")} Record payment</button>`)}
      ${loan.notes ? `<div class="inline-note" style="margin-top:14px">${icon("info")}<div>${esc(loan.notes)}</div></div>` : ""}
    </section>
  </div>`;
}

export async function pageNetworth() {
  const networth = await api(`/networth${personQuery()}`);
  state.pageData.networth = networth;
  const s = networth.summary;
  const history = networth.history || [];
  const debtItems = [
    { name: "Card debt", amount: s.card_debt, color: "#f43f5e" },
    { name: "Loans", amount: s.loans, color: "#f59e0b" },
    { name: "Other liabilities", amount: s.liabilities, color: "#a78bfa" },
  ].filter((item) => item.amount > 0);

  return `${pageHead({
    eyebrow: "Plan",
    title: "Net worth",
    subtitle: "Everything you own minus everything you owe — bank accounts, assets, cards, loans and liabilities.",
    actions: `<button class="btn" data-action="addLiability">${icon("plus")} Liability</button>
      <button class="btn btn-primary" data-action="addAsset">${icon("plus")} Asset</button>`,
  })}
  <div class="dash-hero" style="grid-template-columns:1.6fr 1fr">
    <section class="hero-card">
      <div class="hero-label">Net worth</div>
      <div class="hero-value">${money(s.net_worth)}</div>
      <div class="hero-delta">${icon("shield")} ${money(s.total_debt)} total debt · ${pct(s.net_worth > 0 ? (s.total_debt / Math.max(1, s.assets + s.cash)) * 100 : 0)} debt-to-assets</div>
      <div class="hero-meta">
        <div class="hero-meta-item"><span>Cash</span><strong>${money(s.cash)}</strong></div>
        <div class="hero-meta-item"><span>Assets</span><strong>${money(s.assets)}</strong></div>
        <div class="hero-meta-item"><span>Debts</span><strong class="neg">${money(s.total_debt)}</strong></div>
      </div>
    </section>
    <section class="panel">
      ${panelHead("Debt composition", "Where your liabilities sit")}
      ${debtItems.length ? `<div class="donut-wrap">${donut(debtItems, { size: 130, thickness: 14, centerLabel: "total", centerValue: shortMoney(s.total_debt) })}
        <div class="legend" style="flex:1">${debtItems.map((item) => `<div class="legend-row"><span class="swatch" style="background:${item.color}"></span><span class="name">${esc(item.name)}</span><span class="val">${money(item.amount)}</span></div>`).join("")}</div></div>` : `<div class="empty" style="padding:24px"><p>No debt recorded. Nice.</p></div>`}
    </section>
  </div>

  <section class="panel" style="margin-bottom:16px">
    ${panelHead("Net worth trend", "Daily snapshots, last 24 entries", `<span class="small-note">${history.length} snapshot${history.length === 1 ? "" : "s"}</span>`, "insights")}
    ${lineChart(history, { height: 200 })}
  </section>

  <div class="stat-grid">
    ${statCard({ label: "Cash & bank", value: money(s.cash), foot: `${networth.accounts.length} account${networth.accounts.length === 1 ? "" : "s"}`, iconName: "bank", tone: "cyan" })}
    ${statCard({ label: "Assets", value: money(s.assets), foot: `${networth.assets.length} asset${networth.assets.length === 1 ? "" : "s"}`, iconName: "wallet", tone: "green" })}
    ${statCard({ label: "Card debt", value: money(s.card_debt), foot: `${networth.cards.filter((card) => Number(card.outstanding) > 0).length} card(s) with balance`, iconName: "cards", tone: "red" })}
    ${statCard({ label: "Loans & liabilities", value: money(s.loans + s.liabilities), foot: `${networth.loans.length} loan(s), ${networth.liabilities.length} other`, iconName: "loans", tone: "amber" })}
  </div>

  <div class="dash-grid equal">
    <section class="panel">
      ${panelHead("Assets", `${networth.assets.length} item${networth.assets.length === 1 ? "" : "s"}`, `<button class="btn btn-sm btn-primary" data-action="addAsset">${icon("plus")} Add</button>`, "wallet")}
      ${networth.assets.length ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>Asset</th><th>Category</th><th class="num">Value</th><th class="actions-cell"></th></tr></thead>
        <tbody>${networth.assets.map((asset) => `<tr>
          <td><div class="row-title">${esc(asset.name)}</div><div class="row-sub">${asset.is_liquid ? "Liquid" : "Illiquid"}${asset.acquired_date ? ` · ${esc(dateText(asset.acquired_date))}` : ""}</div></td>
          <td><span class="tag">${esc(asset.category)}</span></td>
          <td class="num">${money(asset.value, asset.currency)}</td>
          <td class="actions-cell"><button class="icon-btn small" data-action="editAsset" data-id="${asset.id}">${icon("edit")}</button><button class="icon-btn small danger" data-action="deleteAsset" data-id="${asset.id}">${icon("trash")}</button></td>
        </tr>`).join("")}</tbody></table></div>` : emptyState("wallet", "No assets yet", "Add property, vehicles, investments, jewellery or other assets.", `<button class="btn btn-primary" data-action="addAsset">${icon("plus")} Add asset</button>`)}
    </section>

    <section class="panel">
      ${panelHead("Liabilities", `${networth.liabilities.length} item${networth.liabilities.length === 1 ? "" : "s"}`, `<button class="btn btn-sm" data-action="addLiability">${icon("plus")} Add</button>`, "loans")}
      ${networth.liabilities.length ? `<div class="table-wrap"><table class="table">
        <thead><tr><th>Liability</th><th>Rate</th><th class="num">Balance</th><th class="actions-cell"></th></tr></thead>
        <tbody>${networth.liabilities.map((item) => `<tr>
          <td><div class="row-title">${esc(item.name)}</div><div class="row-sub">${esc(item.category)} · ${money(item.monthly_payment, item.currency)}/mo</div></td>
          <td>${pct(item.annual_rate)}</td>
          <td class="num">${money(item.balance, item.currency)}</td>
          <td class="actions-cell"><button class="icon-btn small" data-action="editLiability" data-id="${item.id}">${icon("edit")}</button><button class="icon-btn small danger" data-action="deleteLiability" data-id="${item.id}">${icon("trash")}</button></td>
        </tr>`).join("")}</tbody></table></div>` : emptyState("loans", "No other liabilities", "Credit cards and loans are already included. Add anything else here.", `<button class="btn btn-primary" data-action="addLiability">${icon("plus")} Add liability</button>`)}
    </section>
  </div>`;
}

export async function pageIncome() {
  const incomes = await api(`/incomes${personQuery()}`);
  state.pageData.incomes = incomes;
  const currentMonth = state.month;
  const monthRows = incomes.filter((row) => (row.date || "").slice(0, 7) === currentMonth);
  const monthTotal = monthRows.reduce((sum, row) => sum + Number(row.amount || 0), 0);
  const year = new Date().getFullYear();
  const ytdRows = incomes.filter((row) => (row.date || "").startsWith(String(year)));
  const ytdTotal = ytdRows.reduce((sum, row) => sum + Number(row.amount || 0), 0);
  const taxable = incomes.filter((row) => row.is_taxable).reduce((sum, row) => sum + Number(row.amount || 0), 0);
  const recurring = incomes.filter((row) => row.frequency !== "one_time")
    .reduce((sum, row) => sum + Number(row.amount || 0), 0);
  const headLabels = { employment: "Employment", business: "Business", investment: "Investment", rental: "Rental", other: "Other" };

  return `${pageHead({
    eyebrow: "Money",
    title: "Income",
    subtitle: "Salary, business income, rent and investments — the source of your cash flow and tax picture.",
    actions: `<input class="input" type="month" value="${esc(state.month)}" style="width:155px" data-change="dashboardMonth" aria-label="Income month">
      <button class="btn btn-primary" data-action="addIncome">${icon("plus")} Add income</button>`,
  })}
  <div class="stat-grid">
    ${statCard({ label: `Income · ${monthText(currentMonth)}`, value: money(monthTotal), foot: `${monthRows.length} entr${monthRows.length === 1 ? "y" : "ies"} this month`, iconName: "income", tone: "green" })}
    ${statCard({ label: `YTD income · ${year}`, value: money(ytdTotal), foot: `${ytdRows.length} entries this year`, iconName: "insights" })}
    ${statCard({ label: "Taxable income", value: money(taxable), foot: "All recorded taxable income", iconName: "tax", tone: "amber" })}
    ${statCard({ label: "Recurring income", value: money(recurring), foot: "Monthly / quarterly / annual entries", iconName: "repeat", tone: "cyan" })}
  </div>

  <section class="panel">
    ${panelHead("Income ledger", "Each entry is an actual receipt; use repeat to create future months", `<button class="btn btn-sm" data-action="addIncome">${icon("plus")} Add</button>`, "receipt")}
    ${incomes.length ? `<div class="table-wrap"><table class="table">
      <thead><tr><th>Date</th><th>Source</th><th>Tax head</th><th>Frequency</th><th>Account</th><th class="num">Amount</th><th class="actions-cell"></th></tr></thead>
      <tbody>${incomes.map((row) => `<tr>
        <td class="nowrap">${esc(dateText(row.date))}</td>
        <td class="main-cell"><div class="row-title">${esc(row.source)}</div><div class="row-sub">${esc(row.category_name || "Uncategorized")}</div></td>
        <td><span class="tag ${row.is_taxable ? "accent" : "neutral"}">${esc(headLabels[row.tax_head] || row.tax_head)}</span></td>
        <td><span class="tag">${esc(row.frequency.replace("_", " "))}</span></td>
        <td>${esc(row.account_name || "—")}</td>
        <td class="num pos">+${money(row.amount, row.currency)}</td>
        <td class="actions-cell">
          <button class="btn btn-sm" data-action="repeatIncome" data-id="${row.id}" title="Create future entries">Repeat</button>
          <button class="icon-btn small" data-action="editIncome" data-id="${row.id}">${icon("edit")}</button>
          <button class="icon-btn small danger" data-action="deleteIncome" data-id="${row.id}">${icon("trash")}</button>
        </td>
      </tr>`).join("")}</tbody></table></div>` : emptyState("income", "No income recorded", "Add your salary or business income to unlock cash-flow, savings rate and tax estimates.", `<button class="btn btn-primary" data-action="addIncome">${icon("plus")} Add income</button>`)}
  </section>`;
}
