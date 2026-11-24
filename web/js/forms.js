/* FinVault forms: every modal, import flow and mutation action. */
import {
  api, download, state, openModal, closeModal, confirmAction, toast, formToObject,
  options, categoryOptions, cardOptions, money, dateText, esc, attr, icon, refresh,
  navigate, currentPersonId, CONFIG,
} from "./core.js";

/* -------------------------------------------------------------------------- */
/* Small helpers                                                              */
/* -------------------------------------------------------------------------- */
const CURRENCIES = ["LKR", "USD", "EUR", "GBP", "INR", "AUD", "CAD", "AED", "SGD", "JPY", "CNY"];

const EXPENSE_TYPES = ["purchase", "expense", "fee", "interest", "cash_advance", "installment", "adjustment"];
const IN_TYPES = new Set(["payment", "refund", "income_deposit"]);

export function todayISO() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60000).toISOString().slice(0, 10);
}

function baseCurrency() {
  return state.settings?.base_currency || "LKR";
}

function personOptions(selected) {
  return options(state.persons, selected ?? currentPersonId() ?? "", { label: "name" });
}

function currencyOptions(selected) {
  return options(CURRENCIES, selected || baseCurrency());
}

function defaultPersonNote() {
  const id = currentPersonId();
  const person = state.persons.find((row) => Number(row.id) === Number(id));
  return person ? `Saved under <strong>${esc(person.name)}</strong>.` : "";
}

export async function ensureRefs() {
  const jobs = [];
  if (!Array.isArray(state.pageData.cardsRef)) jobs.push(api("/cards").then((rows) => { state.pageData.cardsRef = rows; }));
  if (!Array.isArray(state.pageData.accountsRef)) jobs.push(api("/accounts").then((rows) => { state.pageData.accountsRef = rows; }));
  if (jobs.length) await Promise.all(jobs);
}

function splitSource(value) {
  const [kind, id] = String(value || "").split(":");
  if (!id) return { card_id: null, account_id: null };
  return kind === "card" ? { card_id: Number(id), account_id: null } : { card_id: null, account_id: Number(id) };
}

function directionFor(type) {
  return IN_TYPES.has(type) ? "in" : "out";
}

function typeOptions(selected) {
  const labels = [
    ["purchase", "Purchase"], ["payment", "Payment"], ["refund", "Refund"],
    ["expense", "Expense"], ["installment", "Installment"], ["fee", "Fee"],
    ["interest", "Interest"], ["cash_advance", "Cash advance"], ["adjustment", "Adjustment"],
    ["income_deposit", "Income deposit"], ["card_payment", "Card payment (from bank)"],
  ];
  return options(labels.map(([id, name]) => ({ id, name })), selected || "purchase");
}

function accountOptions(selected, personId = null, placeholder = "No bank account") {
  const accounts = (state.pageData.accountsRef || [])
    .filter((row) => !personId || Number(row.person_id) === Number(personId));
  return options(accounts, selected || "", { placeholder });
}

function transferOptions(selected) {
  const accounts = state.pageData.accountsRef || [];
  const cards = state.pageData.cardsRef || [];
  let html = `<option value="">Select…</option>`;
  if (accounts.length) {
    html += `<optgroup label="Bank accounts">` + accounts.map((row) =>
      `<option value="account:${row.id}"${String(selected) === `account:${row.id}` ? " selected" : ""}>${esc(row.name)} · ${money(row.balance, row.currency)}</option>`
    ).join("") + `</optgroup>`;
  }
  if (cards.length) {
    html += `<optgroup label="Credit cards">` + cards.map((row) =>
      `<option value="card:${row.id}"${String(selected) === `card:${row.id}` ? " selected" : ""}>${esc(row.name)}${row.last4 ? ` ••${row.last4}` : ""} · ${money(row.outstanding, row.currency)} owed</option>`
    ).join("") + `</optgroup>`;
  }
  return html;
}

function checkRow(name, label, checked, hint = "") {
  return `<label class="check-row"><input type="checkbox" name="${name}" ${checked ? "checked" : ""}>
    <span><span style="display:block">${esc(label)}</span>${hint ? `<span class="hint muted">${esc(hint)}</span>` : ""}</span></label>`;
}

function boolValue(values, name) {
  return values[name] ? 1 : 0;
}

function cleanNumber(value) {
  return value === "" || value === undefined || value === null ? "" : value;
}

/* -------------------------------------------------------------------------- */
/* Transactions                                                               */
/* -------------------------------------------------------------------------- */
export async function addTransaction(dataset = {}) {
  await ensureRefs();
  const editing = dataset.id ? await api(`/transactions/${dataset.id}`) : null;
  const tx = editing || {};
  const selectedSource = tx.card_id
    ? `card:${tx.card_id}`
    : tx.account_id
      ? `account:${tx.account_id}`
      : dataset.cardId
        ? `card:${dataset.cardId}`
        : "";
  const type = tx.type || "purchase";

  const body = `<div class="form-grid">
    <div class="field span-2"><label>Card or bank account <span class="required">*</span></label>
      <select class="select" name="source" required>${cardOptions(selectedSource, { includeAccounts: true })}</select>
      <span class="hint">Purchases normally sit on a card. Bank payments and transfers use an account.</span>
    </div>
    <div class="field"><label>Type</label><select class="select" name="type">${typeOptions(type)}</select></div>
    <div class="field"><label>Date <span class="required">*</span></label>
      <input class="input" type="date" name="date" value="${attr(tx.date || todayISO())}" required></div>
    <div class="field span-2"><label>Description</label>
      <input class="input" name="description" maxlength="300" placeholder="What was this for?" value="${attr(tx.description || "")}"></div>
    <div class="field"><label>Amount <span class="required">*</span></label>
      <input class="input" type="number" name="amount" step="0.01" min="0" required placeholder="0.00" value="${attr(tx.amount ?? "")}"></div>
    <div class="field"><label>Direction</label>
      <select class="select" name="direction">
        <option value="out"${(tx.direction || directionFor(type)) === "out" ? " selected" : ""}>Money out</option>
        <option value="in"${(tx.direction || directionFor(type)) === "in" ? " selected" : ""}>Money in</option>
      </select></div>
    <div class="field span-2"><label>Category</label>
      <select class="select" name="category_id">${categoryOptions(tx.category_id || "")}</select></div>
    <div class="field span-2"><label>Notes</label>
      <textarea class="textarea" name="notes" maxlength="1000" placeholder="Optional notes">${esc(tx.notes || "")}</textarea></div>
    <div class="field span-2"><label>Tags</label>
      <input class="input" name="tags" maxlength="300" placeholder="comma, separated, tags" value="${attr(tx.tags || "")}"></div>
  </div>
  <div class="form-section">
    <div class="form-section-title">Business &amp; tax</div>
    <div class="form-grid">
      ${checkRow("is_business", "Business purchase", !!tx.is_business, "Excluded from personal spending and included in business totals.")}
      ${checkRow("tax_deductible", "Tax deductible", !!tx.tax_deductible, "Used against business income in your Sri Lankan tax estimate.")}
    </div>
  </div>`;

  openModal({
    title: editing ? "Edit transaction" : "Add transaction",
    subtitle: editing ? "Update the details and save." : "Log a purchase, payment or expense.",
    size: "lg",
    body,
    submitLabel: editing ? "Save changes" : "Add transaction",
    onMount: (form) => {
      const typeSelect = form.querySelector('[name="type"]');
      const direction = form.querySelector('[name="direction"]');
      typeSelect.addEventListener("change", () => {
        direction.value = directionFor(typeSelect.value);
      });
    },
    onSubmit: async (values) => {
      const { card_id, account_id } = splitSource(values.source);
      if (!card_id && !account_id) throw new Error("Choose a card or bank account");
      const payload = {
        card_id, account_id,
        type: values.type,
        date: values.date,
        description: values.description,
        amount: values.amount,
        direction: values.direction,
        category_id: values.category_id || null,
        notes: values.notes,
        tags: values.tags,
        is_business: boolValue(values, "is_business"),
        tax_deductible: boolValue(values, "tax_deductible"),
      };
      if (editing) await api(`/transactions/${editing.id}`, { method: "PUT", body: payload });
      else await api("/transactions", { method: "POST", body: payload });
      toast(editing ? "Transaction updated" : "Transaction added");
      refresh();
    },
  });
}

export function deleteTransaction(dataset) {
  const id = dataset.id;
  confirmAction({
    title: "Delete transaction?",
    message: "This removes the transaction permanently. Transfers are removed as a pair.",
    confirmLabel: "Delete",
    onConfirm: async () => {
      await api(`/transactions/${id}`, { method: "DELETE" });
      toast("Transaction deleted");
      refresh();
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Cards                                                                      */
/* -------------------------------------------------------------------------- */
export async function addCard(dataset = {}) {
  const editing = dataset.id ? await api(`/cards/${dataset.id}`) : null;
  const card = editing || {};
  const body = `<div class="form-grid">
    <div class="field"><label>Owner</label><select class="select" name="person_id">${personOptions(card.person_id)}</select></div>
    <div class="field"><label>Nickname <span class="required">*</span></label>
      <input class="input" name="name" required maxlength="80" placeholder="e.g. HNB Platinum" value="${attr(card.name || "")}"></div>
    <div class="field"><label>Issuer / bank</label>
      <input class="input" name="issuer" maxlength="80" placeholder="e.g. HNB" value="${attr(card.issuer || "")}"></div>
    <div class="field"><label>Network</label>
      <select class="select" name="network">${options(["Visa", "Mastercard", "Amex", "UnionPay", "Other"], card.network || "Visa", { placeholder: "Select…" })}</select></div>
    <div class="field"><label>Last 4 digits</label>
      <input class="input" name="last4" maxlength="4" inputmode="numeric" placeholder="1234" value="${attr(card.last4 || "")}"></div>
    <div class="field"><label>Currency</label><select class="select" name="currency">${currencyOptions(card.currency)}</select></div>
    <div class="field"><label>Credit limit</label>
      <input class="input" type="number" name="credit_limit" step="0.01" min="0" value="${attr(card.credit_limit ?? 0)}"></div>
    <div class="field"><label>Opening balance owed</label>
      <input class="input" type="number" name="opening_balance" step="0.01" value="${attr(card.opening_balance ?? 0)}">
      <span class="hint">Current debt before any transactions you log here.</span></div>
    <div class="field"><label>APR %</label>
      <input class="input" type="number" name="apr" step="0.01" min="0" value="${attr(card.apr ?? 0)}"></div>
    <div class="field"><label>Annual fee</label>
      <input class="input" type="number" name="annual_fee" step="0.01" min="0" value="${attr(card.annual_fee ?? 0)}"></div>
    <div class="field"><label>Statement day</label>
      <input class="input" type="number" name="statement_day" min="0" max="31" value="${attr(card.statement_day ?? 0)}"></div>
    <div class="field"><label>Payment due day</label>
      <input class="input" type="number" name="due_day" min="0" max="31" value="${attr(card.due_day ?? 0)}"></div>
    <div class="field"><label>Purpose</label>
      <select class="select" name="purpose">${options([{ id: "personal", name: "Personal" }, { id: "business", name: "Business" }, { id: "mixed", name: "Mixed" }], card.purpose || "personal")}</select></div>
    <div class="field"><label>Status</label>
      <select class="select" name="status">${options([{ id: "active", name: "Active" }, { id: "closed", name: "Closed" }], card.status || "active")}</select></div>
    <div class="field"><label>Card colour — from</label>
      <input class="input" type="color" name="color_from" value="${attr(card.color_from || "#4f46e5")}" style="padding:3px;height:38px"></div>
    <div class="field"><label>Card colour — to</label>
      <input class="input" type="color" name="color_to" value="${attr(card.color_to || "#0ea5e9")}" style="padding:3px;height:38px"></div>
    <div class="field span-2"><label>Notes</label>
      <textarea class="textarea" name="notes" maxlength="1000">${esc(card.notes || "")}</textarea></div>
  </div>`;

  openModal({
    title: editing ? "Edit card" : "Add credit card",
    subtitle: "Balances are calculated from the opening balance plus transactions.",
    size: "lg",
    body,
    submitLabel: editing ? "Save changes" : "Add card",
    onSubmit: async (values) => {
      const payload = {
        person_id: values.person_id, name: values.name, issuer: values.issuer,
        network: values.network, last4: values.last4, currency: values.currency,
        credit_limit: values.credit_limit, opening_balance: values.opening_balance,
        apr: values.apr, annual_fee: values.annual_fee, statement_day: values.statement_day,
        due_day: values.due_day, purpose: values.purpose, status: values.status,
        color_from: values.color_from, color_to: values.color_to, notes: values.notes,
      };
      if (editing) await api(`/cards/${editing.id}`, { method: "PUT", body: payload });
      else await api("/cards", { method: "POST", body: payload });
      toast(editing ? "Card updated" : "Card added");
      refresh();
    },
  });
}

export function deleteCard(dataset) {
  confirmAction({
    title: "Delete this card?",
    message: "The card and every transaction attached to it will be removed permanently. Close the card instead if you want to keep the history.",
    confirmLabel: "Delete card",
    onConfirm: async () => {
      await api(`/cards/${dataset.id}?force=1`, { method: "DELETE" });
      toast("Card deleted");
      navigate("#/cards");
      refresh();
    },
  });
}

export async function payCard(dataset) {
  const card = await api(`/cards/${dataset.id}`);
  await ensureRefs();
  const accounts = (state.pageData.accountsRef || []).filter((row) => Number(row.person_id) === Number(card.person_id));
  const openStatements = (card.statements || []).filter((row) => Number(row.closing_balance) - Number(row.amount_paid) > 0);
  const firstDue = openStatements[0];
  const remaining = firstDue ? Number(firstDue.closing_balance) - Number(firstDue.amount_paid) : Number(card.outstanding || 0);
  const accountHtml = accounts.length
    ? `<div class="field"><label>Pay from</label><select class="select" name="account_id">${options(accounts, accounts[0].id, { placeholder: "No bank account (card only)" })}</select>
        <span class="hint">Creates a matching bank payment so cash flow stays correct.</span></div>`
    : `<div class="field span-2"><div class="inline-note">${icon("info")}<div>No bank account recorded yet. This will reduce the card balance only — add a bank account to track the cash leaving.</div></div></div>`;
  const statementHtml = openStatements.length
    ? `<div class="field"><label>Apply to statement</label><select class="select" name="statement_id">
        <option value="">Card balance only</option>
        ${openStatements.map((row) => `<option value="${row.id}"${row.id === firstDue.id ? " selected" : ""}>${esc(dateText(row.statement_date))} · ${money(Number(row.closing_balance) - Number(row.amount_paid), card.currency)} remaining</option>`).join("")}
      </select></div>`
    : "";

  openModal({
    title: `Pay ${card.name}`,
    subtitle: `Outstanding ${money(card.outstanding, card.currency)} · available ${money(card.available, card.currency)}`,
    body: `<div class="form-grid">
      <div class="field"><label>Amount <span class="required">*</span></label>
        <input class="input" type="number" name="amount" step="0.01" min="0.01" required value="${attr(remaining || "")}"></div>
      <div class="field"><label>Date</label><input class="input" type="date" name="date" value="${todayISO()}"></div>
      ${accountHtml}
      ${statementHtml}
      <div class="field span-2"><label>Description</label>
        <input class="input" name="description" maxlength="300" value="${attr(`Payment to ${card.name}`)}"></div>
    </div>`,
    submitLabel: "Record payment",
    onMount: (form) => {
      const statement = form.querySelector('[name="statement_id"]');
      if (statement) {
        statement.addEventListener("change", () => {
          const row = openStatements.find((item) => String(item.id) === statement.value);
          if (row) form.querySelector('[name="amount"]').value = (Number(row.closing_balance) - Number(row.amount_paid)).toFixed(2);
        });
      }
    },
    onSubmit: async (values) => {
      await api(`/cards/${card.id}/payments`, {
        method: "POST",
        body: {
          amount: values.amount,
          date: values.date,
          account_id: values.account_id || null,
          statement_id: values.statement_id || null,
          description: values.description,
        },
      });
      toast("Payment recorded");
      refresh();
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Statements                                                                 */
/* -------------------------------------------------------------------------- */
export async function addStatement(dataset = {}) {
  await ensureRefs();
  let row = {};
  if (dataset.id) {
    const all = await api("/statements");
    row = all.find((item) => Number(item.id) === Number(dataset.id)) || {};
  }
  const selectedCard = row.card_id || dataset.cardId || (state.pageData.cardsRef || [])[0]?.id || "";
  const body = `<div class="form-grid">
    <div class="field span-2"><label>Card <span class="required">*</span></label>
      <select class="select" name="card_id" required>${cardOptions(`card:${selectedCard}`)}</select></div>
    <div class="field"><label>Period start</label><input class="input" type="date" name="period_start" value="${attr(row.period_start || "")}"></div>
    <div class="field"><label>Period end</label><input class="input" type="date" name="period_end" value="${attr(row.period_end || "")}"></div>
    <div class="field"><label>Statement date <span class="required">*</span></label>
      <input class="input" type="date" name="statement_date" required value="${attr(row.statement_date || todayISO())}"></div>
    <div class="field"><label>Payment due date</label><input class="input" type="date" name="due_date" value="${attr(row.due_date || "")}"></div>
    <div class="field"><label>Opening balance</label>
      <input class="input" type="number" name="opening_balance" step="0.01" value="${attr(row.opening_balance ?? 0)}"></div>
    <div class="field"><label>Closing balance <span class="required">*</span></label>
      <input class="input" type="number" name="closing_balance" step="0.01" required value="${attr(row.closing_balance ?? "")}"></div>
    <div class="field"><label>Minimum due</label>
      <input class="input" type="number" name="minimum_due" step="0.01" min="0" value="${attr(row.minimum_due ?? 0)}"></div>
    <div class="field"><label>Amount already paid</label>
      <input class="input" type="number" name="amount_paid" step="0.01" min="0" value="${attr(row.amount_paid ?? 0)}"></div>
    <div class="field"><label>Paid date</label><input class="input" type="date" name="paid_date" value="${attr(row.paid_date || "")}"></div>
    <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="1000">${esc(row.notes || "")}</textarea></div>
  </div>`;

  openModal({
    title: row.id ? "Edit statement" : "Add statement",
    subtitle: "Keep the official closing balance and due date from your statement.",
    size: "lg",
    body,
    submitLabel: row.id ? "Save changes" : "Add statement",
    onSubmit: async (values) => {
      const { card_id } = splitSource(values.card_id);
      const payload = {
        card_id, period_start: values.period_start, period_end: values.period_end,
        statement_date: values.statement_date, due_date: values.due_date,
        opening_balance: values.opening_balance, closing_balance: values.closing_balance,
        minimum_due: values.minimum_due, amount_paid: values.amount_paid,
        paid_date: values.paid_date, notes: values.notes,
      };
      if (row.id) await api(`/statements/${row.id}`, { method: "PUT", body: payload });
      else await api("/statements", { method: "POST", body: payload });
      toast(row.id ? "Statement updated" : "Statement added");
      refresh();
    },
  });
}

export function deleteStatement(dataset) {
  confirmAction({
    title: "Delete statement?",
    message: "The statement record is removed. Its transactions stay on the card.",
    onConfirm: async () => {
      await api(`/statements/${dataset.id}`, { method: "DELETE" });
      toast("Statement deleted");
      refresh();
    },
  });
}

export async function payStatement(dataset) {
  const all = await api("/statements");
  const row = all.find((item) => Number(item.id) === Number(dataset.id));
  if (!row) { toast("Statement not found", "error"); return; }
  await ensureRefs();
  const card = (state.pageData.cardsRef || []).find((item) => Number(item.id) === Number(row.card_id)) || {};
  const accounts = (state.pageData.accountsRef || []).filter((item) => Number(item.person_id) === Number(card.person_id));
  const remaining = Math.max(0, Number(row.closing_balance) - Number(row.amount_paid));
  openModal({
    title: "Pay statement",
    subtitle: `${esc(row.card_name)} · due ${dateText(row.due_date)} · ${money(remaining, row.currency)} remaining`,
    body: `<div class="form-grid">
      <div class="field"><label>Amount <span class="required">*</span></label>
        <input class="input" type="number" name="amount" step="0.01" min="0.01" required value="${attr(remaining.toFixed(2))}"></div>
      <div class="field"><label>Date</label><input class="input" type="date" name="date" value="${todayISO()}"></div>
      <div class="field span-2"><label>Pay from</label>
        <select class="select" name="account_id">${options(accounts, "", { placeholder: "No bank account (card balance only)" })}</select>
        <span class="hint">Selecting an account records the cash leaving your bank too.</span></div>
    </div>`,
    submitLabel: "Record payment",
    onSubmit: async (values) => {
      await api(`/statements/${row.id}/pay`, {
        method: "POST",
        body: { amount: values.amount, date: values.date, account_id: values.account_id || null },
      });
      toast("Statement payment recorded");
      refresh();
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Installments                                                               */
/* -------------------------------------------------------------------------- */
export async function addInstallment(dataset = {}) {
  await ensureRefs();
  const editing = dataset.id ? await api(`/installments/${dataset.id}`) : null;
  const plan = editing || {};
  const selectedCard = plan.card_id || dataset.cardId || (state.pageData.cardsRef || [])[0]?.id || "";
  const body = `<div class="form-grid">
    <div class="field span-2"><label>Card <span class="required">*</span></label>
      <select class="select" name="card_id" required>${cardOptions(`card:${selectedCard}`)}</select></div>
    <div class="field span-2"><label>Description <span class="required">*</span></label>
      <input class="input" name="description" required maxlength="120" placeholder="e.g. iPhone 15 — 24 months" value="${attr(plan.description || "")}"></div>
    <div class="field"><label>Total principal</label>
      <input class="input" type="number" name="principal" step="0.01" min="0" value="${attr(plan.principal ?? "")}"></div>
    <div class="field"><label>Monthly amount</label>
      <input class="input" type="number" name="monthly_amount" step="0.01" min="0" value="${attr(plan.monthly_amount ?? "")}"></div>
    <div class="field"><label>Number of months <span class="required">*</span></label>
      <input class="input" type="number" name="months" min="1" max="360" required value="${attr(plan.months ?? 12)}"></div>
    ${editing ? `<div class="field"><label>Remaining months</label>
      <input class="input" type="number" name="remaining_months" min="0" max="360" value="${attr(plan.remaining_months ?? 0)}"></div>` : ""}
    <div class="field"><label>Interest rate %</label>
      <input class="input" type="number" name="interest_rate" step="0.01" min="0" value="${attr(plan.interest_rate ?? 0)}"></div>
    <div class="field"><label>Start date</label>
      <input class="input" type="date" name="start_date" value="${attr(plan.start_date || todayISO())}"></div>
    <div class="field"><label>First due date</label>
      <input class="input" type="date" name="first_due_date" value="${attr(plan.first_due_date || plan.start_date || todayISO())}"></div>
    <div class="field"><label>Status</label>
      <select class="select" name="status">${options([{ id: "active", name: "Active" }, { id: "completed", name: "Completed" }, { id: "cancelled", name: "Cancelled" }], plan.status || "active")}</select></div>
    <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="1000">${esc(plan.notes || "")}</textarea></div>
  </div>
  <div class="inline-note" style="margin-top:14px">${icon("info")}<div>Each month, use <strong>Log charge</strong> to add that month's installment to the card. The plan tracks how many months remain.</div></div>`;

  openModal({
    title: editing ? "Edit installment plan" : "Add installment plan",
    subtitle: "Track the real monthly commitment of a card installment.",
    size: "lg",
    body,
    submitLabel: editing ? "Save changes" : "Add plan",
    onSubmit: async (values) => {
      const { card_id } = splitSource(values.card_id);
      const payload = {
        card_id, description: values.description, principal: values.principal,
        months: values.months, monthly_amount: values.monthly_amount,
        interest_rate: values.interest_rate, start_date: values.start_date,
        first_due_date: values.first_due_date,
        status: values.status, notes: values.notes,
      };
      if (editing) {
        payload.remaining_months = values.remaining_months;
        await api(`/installments/${editing.id}`, { method: "PUT", body: payload });
      } else {
        await api("/installments", { method: "POST", body: payload });
      }
      toast(editing ? "Plan updated" : "Installment plan added");
      refresh();
    },
  });
}

export function postInstallment(dataset) {
  const plan = (state.pageData.installments || []).find((row) => Number(row.id) === Number(dataset.id)) || {};
  confirmAction({
    title: "Log this month's installment",
    message: `${plan.description || "Installment"} · ${money(plan.monthly_amount, plan.currency)} will be added to ${plan.card_name || "the card"} and one month marked complete.`,
    confirmLabel: "Log charge",
    danger: false,
    onConfirm: async () => {
      await api(`/installments/${dataset.id}/post`, { method: "POST", body: {} });
      toast("Installment charge logged");
      refresh();
    },
  });
}

export function deleteInstallment(dataset) {
  confirmAction({
    title: "Delete installment plan?",
    message: "The plan is removed. Installment charges already posted to the card remain.",
    onConfirm: async () => {
      await api(`/installments/${dataset.id}`, { method: "DELETE" });
      toast("Plan deleted");
      refresh();
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Loans                                                                      */
/* -------------------------------------------------------------------------- */
export async function addLoan(dataset = {}) {
  const editing = dataset.id ? await api(`/loans/${dataset.id}`) : null;
  const loan = editing || {};
  const body = `<div class="form-grid">
    <div class="field"><label>Owner</label><select class="select" name="person_id">${personOptions(loan.person_id)}</select></div>
    <div class="field"><label>Loan name <span class="required">*</span></label>
      <input class="input" name="name" required maxlength="80" placeholder="e.g. Commercial Bank personal loan" value="${attr(loan.name || "")}"></div>
    <div class="field"><label>Lender</label>
      <input class="input" name="lender" maxlength="80" value="${attr(loan.lender || "")}"></div>
    <div class="field"><label>Type</label>
      <select class="select" name="type">${options([
        { id: "personal", name: "Personal" }, { id: "vehicle", name: "Vehicle" }, { id: "housing", name: "Housing" },
        { id: "lease", name: "Lease" }, { id: "education", name: "Education" }, { id: "business", name: "Business" }, { id: "other", name: "Other" },
      ], loan.type || "personal")}</select></div>
    <div class="field"><label>Original principal</label>
      <input class="input" type="number" name="principal" step="0.01" min="0" value="${attr(loan.principal ?? "")}"></div>
    <div class="field"><label>Outstanding balance</label>
      <input class="input" type="number" name="outstanding" step="0.01" min="0" value="${attr(loan.outstanding ?? "")}"></div>
    <div class="field"><label>Currency</label><select class="select" name="currency">${currencyOptions(loan.currency)}</select></div>
    <div class="field"><label>Annual interest rate %</label>
      <input class="input" type="number" name="annual_rate" step="0.01" min="0" value="${attr(loan.annual_rate ?? 0)}"></div>
    <div class="field"><label>Monthly payment</label>
      <input class="input" type="number" name="monthly_payment" step="0.01" min="0" value="${attr(loan.monthly_payment ?? 0)}"></div>
    <div class="field"><label>Term (months)</label>
      <input class="input" type="number" name="term_months" min="0" max="600" value="${attr(loan.term_months ?? 0)}"></div>
    <div class="field"><label>Start date</label>
      <input class="input" type="date" name="start_date" value="${attr(loan.start_date || "")}"></div>
    <div class="field"><label>Next due date</label>
      <input class="input" type="date" name="next_due_date" value="${attr(loan.next_due_date || "")}"></div>
    <div class="field"><label>Status</label>
      <select class="select" name="status">${options([{ id: "active", name: "Active" }, { id: "paid", name: "Paid" }, { id: "closed", name: "Closed" }], loan.status || "active")}</select></div>
    <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="1000">${esc(loan.notes || "")}</textarea></div>
  </div>
  <div class="inline-note" style="margin-top:14px">${icon("info")}<div>The payoff projection uses the outstanding balance, APR and monthly payment. Leave outstanding blank to use the principal.</div></div>`;

  openModal({
    title: editing ? "Edit loan" : "Add loan",
    subtitle: "Loans count towards net worth and cash flow.",
    size: "lg",
    body,
    submitLabel: editing ? "Save changes" : "Add loan",
    onSubmit: async (values) => {
      const payload = {
        person_id: values.person_id, name: values.name, lender: values.lender, type: values.type,
        principal: values.principal, outstanding: values.outstanding, currency: values.currency,
        annual_rate: values.annual_rate, monthly_payment: values.monthly_payment,
        start_date: values.start_date, term_months: values.term_months,
        next_due_date: values.next_due_date, status: values.status, notes: values.notes,
      };
      if (editing) await api(`/loans/${editing.id}`, { method: "PUT", body: payload });
      else await api("/loans", { method: "POST", body: payload });
      toast(editing ? "Loan updated" : "Loan added");
      refresh();
    },
  });
}

export function deleteLoan(dataset) {
  confirmAction({
    title: "Delete loan?",
    message: "The loan and its payment history are removed permanently.",
    onConfirm: async () => {
      await api(`/loans/${dataset.id}`, { method: "DELETE" });
      toast("Loan deleted");
      navigate("#/loans");
      refresh();
    },
  });
}

export async function addLoanPayment(dataset) {
  const loan = await api(`/loans/${dataset.id}`);
  await ensureRefs();
  const accounts = (state.pageData.accountsRef || []).filter((row) => Number(row.person_id) === Number(loan.person_id));
  const monthlyRate = Number(loan.annual_rate || 0) / 100 / 12;
  const expectedInterest = Number(loan.outstanding || 0) * monthlyRate;
  openModal({
    title: `Record payment — ${loan.name}`,
    subtitle: `Outstanding ${money(loan.outstanding, loan.currency)} · ${loan.annual_rate}% APR`,
    body: `<div class="form-grid">
      <div class="field"><label>Amount paid <span class="required">*</span></label>
        <input class="input" type="number" name="amount" step="0.01" min="0.01" required value="${attr(loan.monthly_payment || "")}"></div>
      <div class="field"><label>Date</label><input class="input" type="date" name="date" value="${todayISO()}"></div>
      <div class="field"><label>Interest component</label>
        <input class="input" type="number" name="interest_component" step="0.01" min="0" placeholder="Auto: ${expectedInterest.toFixed(2)}"></div>
      <div class="field"><label>Principal component</label>
        <input class="input" type="number" name="principal_component" step="0.01" min="0" placeholder="Auto: amount − interest"></div>
      <div class="field span-2"><label>Paid from bank account</label>
        <select class="select" name="account_id">${options(accounts, "", { placeholder: "Do not record a bank transaction" })}</select></div>
      <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="1000"></textarea></div>
    </div>
    <div class="inline-note" style="margin-top:14px">${icon("info")}<div>Leave the components blank and FinVault will split the payment using the loan's interest rate.</div></div>`,
    submitLabel: "Record payment",
    onSubmit: async (values) => {
      await api(`/loans/${loan.id}/payments`, {
        method: "POST",
        body: {
          amount: values.amount,
          date: values.date,
          interest_component: cleanNumber(values.interest_component),
          principal_component: cleanNumber(values.principal_component),
          account_id: values.account_id || null,
          notes: values.notes,
        },
      });
      toast("Loan payment recorded");
      refresh();
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Accounts and transfers                                                     */
/* -------------------------------------------------------------------------- */
export async function addAccount(dataset = {}) {
  const editing = dataset.id ? await api(`/accounts/${dataset.id}`) : null;
  const account = editing || {};
  const body = `<div class="form-grid">
    <div class="field"><label>Owner</label><select class="select" name="person_id">${personOptions(account.person_id)}</select></div>
    <div class="field"><label>Account name <span class="required">*</span></label>
      <input class="input" name="name" required maxlength="80" placeholder="e.g. Sampath Savings" value="${attr(account.name || "")}"></div>
    <div class="field"><label>Bank / institution</label>
      <input class="input" name="institution" maxlength="80" value="${attr(account.institution || "")}"></div>
    <div class="field"><label>Type</label>
      <select class="select" name="type">${options([
        { id: "savings", name: "Savings" }, { id: "current", name: "Current" }, { id: "fixed", name: "Fixed deposit" },
        { id: "cash", name: "Cash" }, { id: "wallet", name: "Wallet" }, { id: "investment", name: "Investment" }, { id: "other", name: "Other" },
      ], account.type || "savings")}</select></div>
    <div class="field"><label>Account number</label>
      <input class="input" name="account_number" maxlength="60" value="${attr(account.account_number || "")}"></div>
    <div class="field"><label>Currency</label><select class="select" name="currency">${currencyOptions(account.currency)}</select></div>
    <div class="field"><label>Opening balance</label>
      <input class="input" type="number" name="opening_balance" step="0.01" value="${attr(account.opening_balance ?? 0)}"></div>
    <div class="field"><label>Status</label>
      <select class="select" name="is_active">${options([{ id: "1", name: "Active" }, { id: "0", name: "Inactive" }], account.is_active === 0 ? "0" : "1")}</select></div>
    <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="1000">${esc(account.notes || "")}</textarea></div>
  </div>`;

  openModal({
    title: editing ? "Edit account" : "Add bank account",
    subtitle: "Savings, current accounts, cash and wallets.",
    size: "lg",
    body,
    submitLabel: editing ? "Save changes" : "Add account",
    onSubmit: async (values) => {
      const payload = {
        person_id: values.person_id, name: values.name, institution: values.institution,
        type: values.type, account_number: values.account_number, currency: values.currency,
        opening_balance: values.opening_balance, is_active: values.is_active === "1" ? 1 : 0,
        notes: values.notes,
      };
      if (editing) await api(`/accounts/${editing.id}`, { method: "PUT", body: payload });
      else await api("/accounts", { method: "POST", body: payload });
      toast(editing ? "Account updated" : "Account added");
      refresh();
    },
  });
}

export function deleteAccount(dataset) {
  confirmAction({
    title: "Delete bank account?",
    message: "The account and every transaction attached to it will be removed permanently.",
    confirmLabel: "Delete account",
    onConfirm: async () => {
      await api(`/accounts/${dataset.id}?force=1`, { method: "DELETE" });
      toast("Account deleted");
      refresh();
    },
  });
}

export async function transfer(dataset = {}) {
  await ensureRefs();
  const from = dataset.id ? `account:${dataset.id}` : "";
  openModal({
    title: "Transfer money",
    subtitle: "Move money between your bank accounts or pay a card from an account.",
    body: `<div class="form-grid">
      <div class="field"><label>From <span class="required">*</span></label>
        <select class="select" name="from" required>${transferOptions(from)}</select></div>
      <div class="field"><label>To <span class="required">*</span></label>
        <select class="select" name="to" required>${transferOptions("")}</select></div>
      <div class="field"><label>Amount <span class="required">*</span></label>
        <input class="input" type="number" name="amount" step="0.01" min="0.01" required placeholder="0.00"></div>
      <div class="field"><label>Date</label><input class="input" type="date" name="date" value="${todayISO()}"></div>
      <div class="field span-2"><label>Description</label>
        <input class="input" name="description" maxlength="300" placeholder="Optional — generated automatically"></div>
      <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="1000"></textarea></div>
    </div>
    <div class="inline-note" style="margin-top:14px">${icon("info")}<div>Transfers between two different people are not allowed. Account → card becomes a card payment; card → account becomes a cash advance.</div></div>`,
    submitLabel: "Transfer",
    onSubmit: async (values) => {
      const source = splitSource(values.from);
      const target = splitSource(values.to);
      if (!values.from || !values.to) throw new Error("Choose both a source and a destination");
      if (values.from === values.to) throw new Error("Source and destination are the same");
      await api("/transfers", {
        method: "POST",
        body: {
          from_account_id: source.account_id, from_card_id: source.card_id,
          to_account_id: target.account_id, to_card_id: target.card_id,
          amount: values.amount, date: values.date, description: values.description, notes: values.notes,
        },
      });
      toast("Transfer recorded");
      refresh();
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Assets and liabilities                                                     */
/* -------------------------------------------------------------------------- */
export async function addAsset(dataset = {}) {
  const editing = dataset.id ? await api(`/assets/${dataset.id}`) : null;
  const asset = editing || {};
  openModal({
    title: editing ? "Edit asset" : "Add asset",
    subtitle: defaultPersonNote(),
    body: `<div class="form-grid">
      <div class="field"><label>Owner</label><select class="select" name="person_id">${personOptions(asset.person_id)}</select></div>
      <div class="field"><label>Name <span class="required">*</span></label>
        <input class="input" name="name" required maxlength="80" placeholder="e.g. Apartment in Colombo" value="${attr(asset.name || "")}"></div>
      <div class="field"><label>Category</label>
        <select class="select" name="category">${options([
          { id: "property", name: "Property" }, { id: "vehicle", name: "Vehicle" }, { id: "investment", name: "Investment" },
          { id: "jewellery", name: "Jewellery" }, { id: "electronics", name: "Electronics" }, { id: "business", name: "Business" }, { id: "other", name: "Other" },
        ], asset.category || "property")}</select></div>
      <div class="field"><label>Value</label>
        <input class="input" type="number" name="value" step="0.01" min="0" value="${attr(asset.value ?? "")}"></div>
      <div class="field"><label>Currency</label><select class="select" name="currency">${currencyOptions(asset.currency)}</select></div>
      <div class="field"><label>Acquired date</label><input class="input" type="date" name="acquired_date" value="${attr(asset.acquired_date || "")}"></div>
      <div class="field span-2">${checkRow("is_liquid", "Counts as liquid", !!asset.is_liquid, "Liquid assets are included in your quick-access net worth.")}</div>
      <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="1000">${esc(asset.notes || "")}</textarea></div>
    </div>`,
    submitLabel: editing ? "Save changes" : "Add asset",
    onSubmit: async (values) => {
      const payload = {
        person_id: values.person_id, name: values.name, category: values.category,
        value: values.value, currency: values.currency, acquired_date: values.acquired_date,
        is_liquid: boolValue(values, "is_liquid"), notes: values.notes,
      };
      if (editing) await api(`/assets/${editing.id}`, { method: "PUT", body: payload });
      else await api("/assets", { method: "POST", body: payload });
      toast(editing ? "Asset updated" : "Asset added");
      refresh();
    },
  });
}

export function deleteAsset(dataset) {
  confirmAction({
    title: "Delete asset?",
    message: "This asset will be removed from your net worth.",
    onConfirm: async () => {
      await api(`/assets/${dataset.id}`, { method: "DELETE" });
      toast("Asset deleted");
      refresh();
    },
  });
}

export async function addLiability(dataset = {}) {
  const editing = dataset.id ? await api(`/liabilities/${dataset.id}`) : null;
  const item = editing || {};
  openModal({
    title: editing ? "Edit liability" : "Add liability",
    subtitle: defaultPersonNote(),
    body: `<div class="form-grid">
      <div class="field"><label>Owner</label><select class="select" name="person_id">${personOptions(item.person_id)}</select></div>
      <div class="field"><label>Name <span class="required">*</span></label>
        <input class="input" name="name" required maxlength="80" placeholder="e.g. Friend loan" value="${attr(item.name || "")}"></div>
      <div class="field"><label>Category</label>
        <select class="select" name="category">${options([
          { id: "personal_loan", name: "Personal loan" }, { id: "credit_line", name: "Credit line" },
          { id: "tax", name: "Tax payable" }, { id: "mortgage", name: "Mortgage" }, { id: "other", name: "Other" },
        ], item.category || "other")}</select></div>
      <div class="field"><label>Balance owed</label>
        <input class="input" type="number" name="balance" step="0.01" min="0" value="${attr(item.balance ?? "")}"></div>
      <div class="field"><label>Currency</label><select class="select" name="currency">${currencyOptions(item.currency)}</select></div>
      <div class="field"><label>Annual rate %</label>
        <input class="input" type="number" name="annual_rate" step="0.01" min="0" value="${attr(item.annual_rate ?? 0)}"></div>
      <div class="field"><label>Monthly payment</label>
        <input class="input" type="number" name="monthly_payment" step="0.01" min="0" value="${attr(item.monthly_payment ?? 0)}"></div>
      <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="1000">${esc(item.notes || "")}</textarea></div>
    </div>`,
    submitLabel: editing ? "Save changes" : "Add liability",
    onSubmit: async (values) => {
      const payload = {
        person_id: values.person_id, name: values.name, category: values.category,
        balance: values.balance, currency: values.currency, annual_rate: values.annual_rate,
        monthly_payment: values.monthly_payment, notes: values.notes,
      };
      if (editing) await api(`/liabilities/${editing.id}`, { method: "PUT", body: payload });
      else await api("/liabilities", { method: "POST", body: payload });
      toast(editing ? "Liability updated" : "Liability added");
      refresh();
    },
  });
}

export function deleteLiability(dataset) {
  confirmAction({
    title: "Delete liability?",
    message: "This liability will be removed from your net worth.",
    onConfirm: async () => {
      await api(`/liabilities/${dataset.id}`, { method: "DELETE" });
      toast("Liability deleted");
      refresh();
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Income                                                                     */
/* -------------------------------------------------------------------------- */
export async function addIncome(dataset = {}) {
  await ensureRefs();
  const editing = dataset.id ? await api(`/incomes/${dataset.id}`) : null;
  const income = editing || {};
  const personId = income.person_id || currentPersonId();
  const accounts = (state.pageData.accountsRef || []).filter((row) => Number(row.person_id) === Number(personId));
  openModal({
    title: editing ? "Edit income" : "Add income",
    subtitle: "Salary, business income, rent and investments.",
    size: "lg",
    body: `<div class="form-grid">
      <div class="field"><label>Owner</label><select class="select" name="person_id" id="incomePerson">${personOptions(personId)}</select></div>
      <div class="field"><label>Date</label><input class="input" type="date" name="date" value="${attr(income.date || todayISO())}"></div>
      <div class="field span-2"><label>Source <span class="required">*</span></label>
        <input class="input" name="source" required maxlength="120" placeholder="e.g. Monthly salary — Dialog Axiata" value="${attr(income.source || "")}"></div>
      <div class="field"><label>Amount <span class="required">*</span></label>
        <input class="input" type="number" name="amount" step="0.01" min="0" required value="${attr(income.amount ?? "")}"></div>
      <div class="field"><label>Currency</label><select class="select" name="currency">${currencyOptions(income.currency)}</select></div>
      <div class="field"><label>Frequency</label>
        <select class="select" name="frequency">${options([
          { id: "one_time", name: "One time" }, { id: "monthly", name: "Monthly" },
          { id: "quarterly", name: "Quarterly" }, { id: "annual", name: "Annual" },
        ], income.frequency || "monthly")}</select></div>
      <div class="field"><label>Tax head</label>
        <select class="select" name="tax_head">${options([
          { id: "employment", name: "Employment" }, { id: "business", name: "Business" },
          { id: "investment", name: "Investment" }, { id: "rental", name: "Rental" }, { id: "other", name: "Other" },
        ], income.tax_head || "employment")}</select></div>
      <div class="field"><label>Category</label><select class="select" name="category_id">${categoryOptions(income.category_id || "")}</select></div>
      <div class="field"><label>Deposit into account</label>
        <select class="select" name="account_id">${options(accounts, income.account_id || "", { placeholder: "No deposit" })}</select></div>
      <div class="field span-2">${checkRow("is_taxable", "Taxable income", income.is_taxable !== 0, "Include this in your Sri Lankan income tax estimate.")}</div>
      <div class="field span-2">${checkRow("deposit", "Create a matching bank deposit", !editing, "When an account is selected, add the cash inflow to that account.")}</div>
      <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="1000">${esc(income.notes || "")}</textarea></div>
    </div>`,
    submitLabel: editing ? "Save changes" : "Add income",
    onMount: (form) => {
      const personSelect = form.querySelector('[name="person_id"]');
      const accountSelect = form.querySelector('[name="account_id"]');
      personSelect.addEventListener("change", () => {
        const filtered = (state.pageData.accountsRef || []).filter((row) => Number(row.person_id) === Number(personSelect.value));
        accountSelect.innerHTML = options(filtered, "", { placeholder: "No deposit" });
      });
    },
    onSubmit: async (values) => {
      const payload = {
        person_id: values.person_id, date: values.date, source: values.source,
        amount: values.amount, currency: values.currency, frequency: values.frequency,
        tax_head: values.tax_head, category_id: values.category_id || null,
        account_id: values.account_id || null, is_taxable: boolValue(values, "is_taxable"),
        deposit: boolValue(values, "deposit"), notes: values.notes,
      };
      if (editing) await api(`/incomes/${editing.id}`, { method: "PUT", body: payload });
      else await api("/incomes", { method: "POST", body: payload });
      toast(editing ? "Income updated" : "Income added");
      refresh();
    },
  });
}

export function repeatIncome(dataset) {
  openModal({
    title: "Repeat income",
    subtitle: "Create future entries from this income — useful for salary or rent.",
    size: "sm",
    body: `<div class="form-grid">
      <div class="field span-2"><label>Number of future entries</label>
        <input class="input" type="number" name="months" min="1" max="120" value="11"></div>
      <div class="field span-2">${checkRow("deposit", "Also create matching bank deposits", true)}</div>
    </div>`,
    submitLabel: "Create entries",
    onSubmit: async (values) => {
      const result = await api(`/incomes/${dataset.id}/repeat`, {
        method: "POST",
        body: { months: values.months, deposit: boolValue(values, "deposit") },
      });
      toast(`${result.count} income entr${result.count === 1 ? "y" : "ies"} created`);
      refresh();
    },
  });
}

export function deleteIncome(dataset) {
  confirmAction({
    title: "Delete income?",
    message: "This income entry and any matching bank deposit will be removed.",
    onConfirm: async () => {
      await api(`/incomes/${dataset.id}`, { method: "DELETE" });
      toast("Income deleted");
      refresh();
    },
  });
}

/* -------------------------------------------------------------------------- */
/* People                                                                     */
/* -------------------------------------------------------------------------- */
const PERSON_COLORS = ["#6366f1", "#06b6d4", "#f59e0b", "#ec4899", "#10b981", "#a78bfa"];

export async function addPerson(dataset = {}) {
  const editing = dataset.id ? (state.persons.find((row) => Number(row.id) === Number(dataset.id)) || await api("/persons").then((rows) => rows.find((row) => Number(row.id) === Number(dataset.id)))) : null;
  const person = editing || {};
  openModal({
    title: editing ? "Edit person" : "Add person",
    subtitle: "Track your own finances or a partner's, separately or together.",
    body: `<div class="form-grid">
      <div class="field"><label>Name <span class="required">*</span></label>
        <input class="input" name="name" required maxlength="80" value="${attr(person.name || "")}"></div>
      <div class="field"><label>Relationship</label>
        <input class="input" name="relationship" maxlength="40" placeholder="self, spouse, parent…" value="${attr(person.relationship || "")}"></div>
      <div class="field"><label>Colour</label>
        <select class="select" name="color">${options(PERSON_COLORS.map((hex) => ({ id: hex, name: hex })), person.color || PERSON_COLORS[0])}</select></div>
      <div class="field"><label>Sort order</label>
        <input class="input" type="number" name="sort_order" value="${attr(person.sort_order ?? 0)}"></div>
      <div class="field"><label>Email</label><input class="input" type="email" name="email" maxlength="120" value="${attr(person.email || "")}"></div>
      <div class="field"><label>Phone</label><input class="input" name="phone" maxlength="40" value="${attr(person.phone || "")}"></div>
      <div class="field"><label>TIN</label><input class="input" name="tin" maxlength="40" placeholder="Taxpayer identification number" value="${attr(person.tin || "")}"></div>
      <div class="field"><label>Date of birth</label><input class="input" type="date" name="date_of_birth" value="${attr(person.date_of_birth || "")}"></div>
      <div class="field span-2">${checkRow("is_primary", "Primary person", !!person.is_primary, "The default owner for new records and tax estimates.")}</div>
    </div>`,
    submitLabel: editing ? "Save changes" : "Add person",
    onSubmit: async (values) => {
      const payload = {
        name: values.name, relationship: values.relationship, color: values.color,
        sort_order: values.sort_order, email: values.email, phone: values.phone,
        tin: values.tin, date_of_birth: values.date_of_birth,
        is_primary: boolValue(values, "is_primary"),
      };
      if (editing) {
        await api(`/persons/${editing.id}`, { method: "PUT", body: payload });
        toast("Person updated");
      } else {
        const created = await api("/persons", { method: "POST", body: payload });
        toast("Person added");
        if (!editing && state.personId !== "all") {
          state.personId = String(created.id);
          localStorage.setItem("fv_person", state.personId);
        }
      }
      refresh();
    },
  });
}

export function deletePerson(dataset) {
  confirmAction({
    title: "Delete person?",
    message: "This person and everything attached to them — cards, accounts, transactions, loans — will be removed permanently.",
    confirmLabel: "Delete person",
    onConfirm: async () => {
      await api(`/persons/${dataset.id}`, { method: "DELETE" });
      toast("Person deleted");
      refresh();
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Tax                                                                        */
/* -------------------------------------------------------------------------- */
export async function addTaxRelief(dataset = {}) {
  const year = dataset.year || state.taxYear || (await api("/tax/years")).current;
  let editing = null;
  if (dataset.id) {
    const rows = await api(`/tax/reliefs?person_id=${currentPersonId()}&year_label=${encodeURIComponent(year)}`);
    editing = rows.find((row) => Number(row.id) === Number(dataset.id));
  }
  const row = editing || {};
  openModal({
    title: editing ? "Edit tax relief" : "Add tax relief",
    subtitle: `Year of assessment ${esc(year)} · ${esc(personLabel())}`,
    body: `<div class="form-grid">
      <div class="field span-2"><label>Relief name <span class="required">*</span></label>
        <input class="input" name="name" required maxlength="120" placeholder="e.g. Qualifying payment to approved fund" value="${attr(row.name || "")}"></div>
      <div class="field"><label>Amount</label>
        <input class="input" type="number" name="amount" step="0.01" min="0" value="${attr(row.amount ?? "")}"></div>
      <div class="field"><label>Kind</label>
        <select class="select" name="kind">${options([
          { id: "qualifying", name: "Qualifying relief" }, { id: "donation", name: "Donation" },
          { id: "rent", name: "Rent related" }, { id: "other", name: "Other" },
        ], row.kind || "qualifying")}</select></div>
      <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="500">${esc(row.notes || "")}</textarea></div>
    </div>`,
    submitLabel: editing ? "Save changes" : "Add relief",
    onSubmit: async (values) => {
      const payload = {
        person_id: currentPersonId(), year_label: year, name: values.name,
        amount: values.amount, kind: values.kind, notes: values.notes,
      };
      if (editing) await api(`/tax/reliefs/${editing.id}`, { method: "PUT", body: payload });
      else await api("/tax/reliefs", { method: "POST", body: payload });
      toast(editing ? "Relief updated" : "Relief added");
      refresh();
    },
  });
}

export function deleteTaxRelief(dataset) {
  confirmAction({
    title: "Delete tax relief?",
    message: "This relief will no longer reduce your taxable income.",
    onConfirm: async () => {
      await api(`/tax/reliefs/${dataset.id}`, { method: "DELETE" });
      toast("Relief deleted");
      refresh();
    },
  });
}

export async function addTaxCredit(dataset = {}) {
  const year = dataset.year || state.taxYear || (await api("/tax/years")).current;
  let editing = null;
  if (dataset.id) {
    const rows = await api(`/tax/credits?person_id=${currentPersonId()}&year_label=${encodeURIComponent(year)}`);
    editing = rows.find((row) => Number(row.id) === Number(dataset.id));
  }
  const row = editing || {};
  openModal({
    title: editing ? "Edit tax credit" : "Add tax credit",
    subtitle: `APIT, WHT and payments already made · ${esc(year)}`,
    body: `<div class="form-grid">
      <div class="field span-2"><label>Credit name <span class="required">*</span></label>
        <input class="input" name="name" required maxlength="120" placeholder="e.g. APIT deducted by employer" value="${attr(row.name || "")}"></div>
      <div class="field"><label>Amount</label>
        <input class="input" type="number" name="amount" step="0.01" min="0" value="${attr(row.amount ?? "")}"></div>
      <div class="field"><label>Kind</label>
        <select class="select" name="kind">${options([
          { id: "apit", name: "APIT (employment tax)" }, { id: "wht", name: "WHT" }, { id: "other", name: "Other credit" },
        ], row.kind || "apit")}</select></div>
      <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="500">${esc(row.notes || "")}</textarea></div>
    </div>`,
    submitLabel: editing ? "Save changes" : "Add credit",
    onSubmit: async (values) => {
      const payload = {
        person_id: currentPersonId(), year_label: year, name: values.name,
        amount: values.amount, kind: values.kind, notes: values.notes,
      };
      if (editing) await api(`/tax/credits/${editing.id}`, { method: "PUT", body: payload });
      else await api("/tax/credits", { method: "POST", body: payload });
      toast(editing ? "Credit updated" : "Credit added");
      refresh();
    },
  });
}

export function deleteTaxCredit(dataset) {
  confirmAction({
    title: "Delete tax credit?",
    message: "This payment will no longer be offset against your tax bill.",
    onConfirm: async () => {
      await api(`/tax/credits/${dataset.id}`, { method: "DELETE" });
      toast("Credit deleted");
      refresh();
    },
  });
}

function personLabel() {
  const id = currentPersonId();
  return state.persons.find((row) => Number(row.id) === Number(id))?.name || "Primary person";
}

export async function editTaxRules(dataset = {}) {
  const years = await api("/tax/years");
  const year = dataset.year || state.taxYear || years.current;
  const rule = (years.years || []).find((row) => row.year_label === year);
  if (!rule) { toast("Tax year not found", "error"); return; }
  const slabs = (rule.slabs || []).slice();
  while (slabs.length < 8) slabs.push({ upto: null, rate: null });
  const slabRows = slabs.map((slab, index) => `<tr>
    <td style="color:var(--muted);font-size:11px">${index + 1}</td>
    <td><input class="input" type="number" step="0.01" min="0" name="slab_upto_${index}" placeholder="Above" value="${slab.upto == null ? "" : attr(slab.upto)}" style="height:32px"></td>
    <td><input class="input" type="number" step="0.001" min="0" name="slab_rate_${index}" placeholder="0" value="${slab.rate == null ? "" : attr((Number(slab.rate) * 100).toFixed(3).replace(/\.?0+$/, ""))}" style="height:32px"></td>
  </tr>`).join("");

  openModal({
    title: `Tax rules — ${year}`,
    subtitle: "Edit the slabs to match your official Sri Lankan tax sheet exactly.",
    size: "lg",
    body: `<div class="form-grid">
      <div class="field span-2"><label>Year label</label>
        <input class="input" name="label" maxlength="120" value="${attr(rule.label || "")}"></div>
      <div class="field"><label>Personal relief</label>
        <input class="input" type="number" name="personal_relief" step="0.01" min="0" value="${attr(rule.personal_relief ?? 0)}"></div>
      <div class="field"><label>Rent relief %</label>
        <input class="input" type="number" name="rent_relief_pct" step="0.01" min="0" max="100" value="${attr(rule.rent_relief_pct ?? 0)}"></div>
      <div class="field"><label>Rent relief cap</label>
        <input class="input" type="number" name="rent_relief_cap" step="0.01" min="0" value="${attr(rule.rent_relief_cap ?? 0)}"></div>
      <div class="field"><label>WHT treatment</label>
        <select class="select" name="wht_is_final">${options([{ id: "0", name: "Creditable" }, { id: "1", name: "Final tax" }], String(rule.wht_is_final || 0))}</select></div>
    </div>
    <div class="form-section">
      <div class="form-section-title">Progressive slabs</div>
      <div class="table-wrap"><table class="table table-compact">
        <thead><tr><th style="width:34px">#</th><th>Income up to</th><th>Rate %</th></tr></thead>
        <tbody>${slabRows}</tbody>
      </table></div>
      <div class="small-note" style="margin-top:8px">Leave the last “Income up to” blank for the top (no-limit) slab. Rates are percentages, e.g. 6 for 6%.</div>
    </div>
    <div class="field" style="margin-top:14px"><label>Notes</label>
      <textarea class="textarea" name="notes" maxlength="2000">${esc(rule.notes || "")}</textarea></div>`,
    submitLabel: "Save tax rules",
    onSubmit: async (values) => {
      const cleaned = [];
      for (let index = 0; index < 8; index += 1) {
        const upto = values[`slab_upto_${index}`];
        const rate = values[`slab_rate_${index}`];
        if ((upto === "" || upto === undefined) && (rate === "" || rate === undefined)) continue;
        cleaned.push({ upto: upto === "" || upto === undefined ? null : upto, rate: Number(rate || 0) / 100 });
      }
      if (!cleaned.length) throw new Error("Add at least one tax slab");
      await api(`/tax/rules/${encodeURIComponent(year)}`, {
        method: "PUT",
        body: {
          label: values.label,
          personal_relief: values.personal_relief,
          rent_relief_pct: values.rent_relief_pct,
          rent_relief_cap: values.rent_relief_cap,
          wht_is_final: values.wht_is_final === "1" ? 1 : 0,
          notes: values.notes,
          slabs: cleaned,
        },
      });
      toast("Tax rules updated");
      refresh();
    },
  });
}

/* -------------------------------------------------------------------------- */
/* CSV import                                                                 */
/* -------------------------------------------------------------------------- */
function detectDelimiter(text) {
  const sample = text.slice(0, 4000);
  if (sample.includes("\t")) return "\t";
  if (sample.includes(";")) return ";";
  return ",";
}

function parseHeader(text) {
  const firstLine = String(text || "").split(/\r?\n/)[0] || "";
  if (!firstLine.trim()) return [];
  const delimiter = detectDelimiter(text);
  return firstLine.split(delimiter).map((value) => value.trim().replace(/^"|"$/g, ""));
}

function guessColumn(headers, patterns) {
  const match = headers.find((header) => patterns.some((pattern) => pattern.test(header)));
  return match || "";
}

function mappingSelect(name, headers, selected) {
  return `<select class="select" name="${name}">
    <option value="">—</option>
    ${headers.map((header) => `<option value="${attr(header)}"${header === selected ? " selected" : ""}>${esc(header)}</option>`).join("")}
  </select>`;
}

function applyHeaders(form, text) {
  const headers = parseHeader(text);
  const targets = [
    ["map_date", [/date/i, /^date/i]],
    ["map_description", [/description/i, /details/i, /narrative/i, /particular/i, /merchant/i]],
    ["map_amount", [/amount/i, /value/i, /^amt/i]],
    ["map_debit", [/debit/i, /withdrawal/i, /^dr/i]],
    ["map_credit", [/credit/i, /deposit/i, /^cr/i]],
  ];
  targets.forEach(([name, patterns]) => {
    const select = form.querySelector(`[name="${name}"]`);
    if (!select) return;
    const previous = select.value;
    const guess = guessColumn(headers, patterns);
    select.innerHTML = `<option value="">—</option>` + headers.map((header) =>
      `<option value="${attr(header)}"${(previous || guess) === header ? " selected" : ""}>${esc(header)}</option>`
    ).join("");
  });
  const out = form.querySelector("#csvColumns");
  if (out) out.textContent = headers.length ? `Detected columns: ${headers.join(" · ")}` : "Paste a CSV or choose a file to detect columns.";
}

function csvResultHtml(result) {
  const errors = result.errors || [];
  return `<div class="small-note" style="margin-top:10px">
    <strong>${result.dry_run ? "Preview" : "Import complete"}</strong> · parsed ${result.parsed || 0} ·
    ${result.dry_run ? "ready" : `inserted ${result.inserted || 0}`} ·
    skipped ${result.skipped || 0} · errors ${errors.length}
  </div>
  ${(result.preview || []).length ? `<div class="table-wrap" style="margin-top:8px;max-height:220px;overflow:auto"><table class="table table-compact">
    <thead><tr><th>Date</th><th>Description</th><th class="num">Amount</th><th>Dir</th></tr></thead>
    <tbody>${result.preview.map((row) => `<tr>
      <td>${esc(row.date || "")}</td><td>${esc(row.description || "")}</td>
      <td class="num">${money(row.amount || 0)}</td><td>${esc(row.direction || "")}</td>
    </tr>`).join("")}</tbody>
  </table></div>` : ""}
  ${errors.length ? `<div class="inline-note warning" style="margin-top:8px">${icon("alert")}<div>${errors.slice(0, 5).map((row) => `Line ${row.line ?? row.index ?? "?"}: ${esc(row.error)}`).join("<br>")}</div></div>` : ""}`;
}

export async function importCsv() {
  await ensureRefs();
  const body = `<div class="form-grid">
    <div class="field"><label>Import into <span class="required">*</span></label>
      <select class="select" name="source" required>${cardOptions("", { includeAccounts: true })}</select></div>
    <div class="field"><label>Default category</label><select class="select" name="category_id">${categoryOptions("")}</select></div>
    <div class="field span-2"><label>CSV file</label><input class="input" type="file" accept=".csv,text/csv,text/plain" id="csvFile"></div>
    <div class="field span-2"><label>Or paste CSV</label>
      <textarea class="textarea" name="csv_text" style="min-height:110px;font-family:var(--mono);font-size:10.5px" placeholder="Date,Description,Amount&#10;2026-11-01,Groceries,12500"></textarea>
      <span class="hint" id="csvColumns">Paste a CSV or choose a file to detect columns.</span></div>
  </div>
  <div class="form-section">
    <div class="form-section-title">Column mapping</div>
    <div class="form-grid">
      <div class="field"><label>Date column <span class="required">*</span></label><span id="mapDateWrap">${mappingSelect("map_date", [], "")}</span></div>
      <div class="field"><label>Description column</label><span id="mapDescWrap">${mappingSelect("map_description", [], "")}</span></div>
      <div class="field"><label>Amount column</label><span id="mapAmountWrap">${mappingSelect("map_amount", [], "")}</span></div>
      <div class="field"><label>Debit (money out)</label><span id="mapDebitWrap">${mappingSelect("map_debit", [], "")}</span></div>
      <div class="field"><label>Credit (money in)</label><span id="mapCreditWrap">${mappingSelect("map_credit", [], "")}</span></div>
      <div class="field"><label>Default type</label>
        <select class="select" name="default_type">${options([
          { id: "", name: "Automatic" }, { id: "purchase", name: "Purchase" }, { id: "expense", name: "Expense" },
          { id: "payment", name: "Payment" }, { id: "fee", name: "Fee" }, { id: "interest", name: "Interest" },
        ], "")}</select></div>
    </div>
    <div class="form-grid" style="margin-top:12px">
      ${checkRow("day_first", "Dates are day first", true, "e.g. 25/12/2026 = 25 December.")}
      ${checkRow("signed_amount", "Negative amounts are money in", true)}
      ${checkRow("skip_duplicates", "Skip duplicate rows", true)}
      ${checkRow("is_business", "Mark all rows as business", false)}
      ${checkRow("tax_deductible", "Mark all rows tax deductible", false)}
    </div>
    <div id="csvPreviewOut"></div>
  </div>`;

  openModal({
    title: "Import a statement",
    subtitle: "Works with most bank and credit-card CSV exports.",
    size: "xl",
    body,
    submitLabel: "Import transactions",
    footerExtra: `<button type="button" class="btn btn-ghost" id="csvPreview">Preview</button>`,
    onMount: (form, wrap) => {
      const textarea = form.querySelector('[name="csv_text"]');
      const file = form.querySelector("#csvFile");
      file.addEventListener("change", () => {
        const chosen = file.files && file.files[0];
        if (!chosen) return;
        const reader = new FileReader();
        reader.onload = () => { textarea.value = String(reader.result || ""); applyHeaders(form, textarea.value); };
        reader.readAsText(chosen);
      });
      textarea.addEventListener("input", () => applyHeaders(form, textarea.value));
      if (textarea.value.trim()) applyHeaders(form, textarea.value);

      const preview = form.querySelector("#csvPreview");
      preview.addEventListener("click", async () => {
        const out = form.querySelector("#csvPreviewOut");
        preview.disabled = true;
        try {
          const values = formToObject(form);
          const { card_id, account_id } = splitSource(values.source);
          if (!card_id && !account_id) throw new Error("Choose a card or account first");
          const result = await api("/import/csv", { method: "POST", body: buildCsvPayload(values, card_id, account_id, true) });
          out.innerHTML = csvResultHtml(result);
        } catch (error) {
          toast(error.message || "Could not preview", "error");
        } finally {
          preview.disabled = false;
        }
      });
    },
    onSubmit: async (values) => {
      const { card_id, account_id } = splitSource(values.source);
      if (!card_id && !account_id) throw new Error("Choose a card or account first");
      if (!values.csv_text || !values.csv_text.trim()) throw new Error("Paste a CSV or choose a file");
      if (!values.map_date) throw new Error("Choose the date column");
      const result = await api("/import/csv", { method: "POST", body: buildCsvPayload(values, card_id, account_id, false) });
      if (!result.inserted && result.errors && result.errors.length) {
        throw new Error(`No rows imported — ${result.errors[0].error || "check the column mapping"}`);
      }
      toast(`${result.inserted} transaction${result.inserted === 1 ? "" : "s"} imported${result.skipped ? `, ${result.skipped} skipped` : ""}`);
      refresh();
    },
  });
}

function buildCsvPayload(values, card_id, account_id, dryRun) {
  return {
    csv_text: values.csv_text,
    card_id, account_id,
    mapping: {
      date: values.map_date,
      description: values.map_description || undefined,
      amount: values.map_amount || undefined,
      debit: values.map_debit || undefined,
      credit: values.map_credit || undefined,
    },
    category_id: values.category_id || null,
    default_type: values.default_type || "",
    day_first: boolValue(values, "day_first"),
    signed_amount: boolValue(values, "signed_amount"),
    skip_duplicates: boolValue(values, "skip_duplicates"),
    is_business: boolValue(values, "is_business"),
    tax_deductible: boolValue(values, "tax_deductible"),
    dry_run: dryRun ? 1 : 0,
  };
}

/* -------------------------------------------------------------------------- */
/* Quick add and global search                                                */
/* -------------------------------------------------------------------------- */
const QUICK_CHOICES = [
  ["transaction", "plus", "Transaction", "Purchase or expense", "addTransaction"],
  ["payment", "wallet", "Card payment", "Pay a card from your bank", "quickPay"],
  ["income", "income", "Income", "Salary, business or rent", "addIncome"],
  ["transfer", "repeat", "Transfer", "Move money between accounts", "transfer"],
  ["statement", "receipt", "Statement", "Card closing balance", "addStatement"],
  ["installment", "installments", "Installment", "Monthly plan on a card", "addInstallment"],
  ["card", "cards", "Credit card", "Add a new card", "addCard"],
  ["account", "bank", "Bank account", "Savings or current account", "addAccount"],
  ["asset", "wallet", "Asset", "Property, vehicle, investment", "addAsset"],
  ["liability", "loans", "Liability", "Anything else you owe", "addLiability"],
  ["loan", "loans", "Loan", "Personal, vehicle or housing", "addLoan"],
];

export function quickAdd() {
  openModal({
    title: "Quick add",
    subtitle: "What would you like to record?",
    hideSubmit: true,
    cancelLabel: "Close",
    body: `<div class="quick-grid">${QUICK_CHOICES.map(([key, iconName, title, hint, action]) => `
      <button type="button" class="quick-choice" data-quick="${action}">
        <span class="q-icon">${icon(iconName)}</span>
        <span><strong>${esc(title)}</strong><small>${esc(hint)}</small></span>
      </button>`).join("")}</div>`,
    onMount: (form, wrap) => {
      wrap.querySelectorAll("[data-quick]").forEach((button) => {
        button.addEventListener("click", async () => {
          const action = button.dataset.quick;
          closeModal();
          if (action === "quickPay") {
            await ensureRefs();
            const cards = state.pageData.cardsRef || [];
            if (!cards.length) { toast("Add a credit card first", "warning"); addCard(); return; }
            if (cards.length === 1) { payCard({ id: cards[0].id }); return; }
            openModal({
              title: "Pay a card",
              subtitle: "Choose which card to pay.",
              size: "sm",
              hideSubmit: true,
              cancelLabel: "Close",
              body: `<div class="quick-grid">${cards.map((card) => `<button type="button" class="quick-choice" data-pay="${card.id}">
                <span class="q-icon">${icon("cards")}</span><span><strong>${esc(card.name)}</strong><small>${money(card.outstanding, card.currency)} owed</small></span>
              </button>`).join("")}</div>`,
              onMount: (inner) => {
                inner.querySelectorAll("[data-pay]").forEach((choice) => {
                  choice.addEventListener("click", () => { closeModal(); payCard({ id: choice.dataset.pay }); });
                });
              },
            });
            return;
          }
          const handler = FORM_ACTIONS[action];
          if (handler) handler({});
        });
      });
    },
  });
}

export function openSearch() {
  const { form, wrap } = openModal({
    title: "Search FinVault",
    subtitle: "Find transactions, cards, accounts, income, assets and loans.",
    size: "lg",
    hideSubmit: true,
    cancelLabel: "Close",
    body: `<div class="search-box">
      <span class="search-icon" data-icon="search"></span>
      <input class="input" type="search" name="q" placeholder="Type at least two characters…" autocomplete="off">
    </div>
    <div class="search-results" id="searchResults">
      <div class="empty" style="padding:26px"><p class="muted" style="margin:0">Start typing to search across everything.</p></div>
    </div>`,
  });
  const input = form.querySelector('[name="q"]');
  const results = wrap.querySelector("#searchResults");
  let timer = null;
  let requestId = 0;
  const run = async () => {
    const term = input.value.trim();
    if (term.length < 2) {
      results.innerHTML = `<div class="empty" style="padding:26px"><p class="muted" style="margin:0">Start typing to search across everything.</p></div>`;
      return;
    }
    const ticket = ++requestId;
    try {
      const data = await api(`/search?q=${encodeURIComponent(term)}`);
      if (ticket !== requestId) return;
      const groups = data.groups || [];
      if (!groups.length) {
        results.innerHTML = `<div class="empty" style="padding:26px"><p class="muted" style="margin:0">No matches for “${esc(term)}”.</p></div>`;
        return;
      }
      results.innerHTML = groups.map((group) => `<div>
        <div class="search-group-label">${esc(group.label)}</div>
        ${group.items.map((item) => `<button type="button" class="search-result" data-search-type="${attr(item.type)}" data-search-id="${attr(item.id)}">
          <span class="list-icon">${icon(item.type === "card" ? "cards" : item.type === "account" ? "bank" : item.type === "income" ? "income" : item.type === "loan" ? "loans" : item.type === "asset" ? "wallet" : "transactions")}</span>
          <span class="list-main"><span class="list-title">${esc(item.title)}</span><span class="list-sub">${esc(item.subtitle || "")}</span></span>
          ${item.amount ? `<span class="list-end"><span class="list-amount">${money(item.amount)}</span></span>` : ""}
        </button>`).join("")}
      </div>`).join("");
      results.querySelectorAll("[data-search-type]").forEach((button) => {
        button.addEventListener("click", () => {
          const type = button.dataset.searchType;
          const id = button.dataset.searchId;
          closeModal();
          if (type === "card") navigate(`#/cards/${id}`);
          else if (type === "account") navigate("#/accounts");
          else if (type === "income") navigate("#/income");
          else if (type === "asset") navigate("#/networth");
          else if (type === "loan") navigate(`#/loans/${id}`);
          else navigate("#/transactions");
        });
      });
    } catch (error) {
      if (ticket === requestId) results.innerHTML = `<div class="inline-note danger">${icon("alert")}<div>${esc(error.message)}</div></div>`;
    }
  };
  input.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(run, 260);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") { event.preventDefault(); clearTimeout(timer); run(); }
  });
  setTimeout(() => input.focus(), 60);
}

/* -------------------------------------------------------------------------- */
/* Settings, exports and misc actions                                         */
/* -------------------------------------------------------------------------- */
export async function saveGeneral() {
  const payload = {
    base_currency: document.getElementById("setBaseCurrency")?.value || baseCurrency(),
    theme: document.getElementById("setTheme")?.value || state.theme,
    backup_interval_hours: document.getElementById("setBackupHours")?.value || "12",
    idle_quit_minutes: document.getElementById("setIdleQuit")?.value || "30",
    fiscal_year_start_month: document.getElementById("setFiscalMonth")?.value || "4",
  };
  await api("/settings", { method: "PUT", body: { settings: payload } });
  state.settings = { ...state.settings, ...payload };
  toast("Settings saved");
  refresh();
}

export async function saveFx() {
  const rates = {};
  document.querySelectorAll("[data-fx]").forEach((input) => {
    rates[input.dataset.fx] = input.value;
  });
  await api("/fx", { method: "PUT", body: { rates } });
  toast("Exchange rates saved");
  refresh();
}

export async function backupNow() {
  const result = await api("/admin/backup", { method: "POST", body: {} });
  toast(`Backup created · ${result.file}`);
  refresh();
}

export function restoreBackup(dataset) {
  confirmAction({
    title: "Restore this backup?",
    message: `This replaces the live database with ${dataset.name}. A pre-restore backup is created automatically.`,
    confirmLabel: "Restore",
    danger: true,
    onConfirm: async () => {
      await api("/admin/restore", { method: "POST", body: { name: dataset.name } });
      toast("Backup restored");
      refresh();
    },
  });
}

export async function exportJson() {
  await download("/export?format=json", "FinVault-export.json");
  toast("Export downloaded");
}

export async function exportCsv() {
  await download("/export?format=csv&table=transactions", "FinVault-transactions.csv");
  toast("Transactions exported");
}

export async function exportTax(dataset) {
  const year = dataset.year || state.taxYear;
  const person = dataset.person || currentPersonId();
  await download(`/export?format=csv&table=tax&person_id=${person}&year_label=${encodeURIComponent(year)}`, `FinVault-tax-${String(year).replace("/", "-")}.csv`);
  toast("Tax summary exported");
}

export async function exportTaxCurrent() {
  const years = await api("/tax/years");
  const year = state.taxYear || years.current;
  await download(`/export?format=csv&table=tax&person_id=${currentPersonId()}&year_label=${encodeURIComponent(year)}`, `FinVault-tax-${String(year).replace("/", "-")}.csv`);
  toast("Tax summary exported");
}

export function rotateKey() {
  confirmAction({
    title: "Rotate API key?",
    message: "The current key stops working immediately. Any other app using FinVault must be updated with the new key.",
    confirmLabel: "Rotate key",
    danger: true,
    onConfirm: async () => {
      const result = await api("/settings/rotate-key", { method: "POST", body: {} });
      state.settings = { ...state.settings, api_key: result.api_key };
      CONFIG.apiKey = result.api_key;
      state.showKey = true;
      toast("API key rotated");
      refresh();
    },
  });
}

export function quitApp() {
  confirmAction({
    title: "Quit FinVault?",
    message: "The local server will stop. You can close this browser tab afterwards. Your data stays safe in FinVault.db.",
    confirmLabel: "Quit app",
    danger: true,
    onConfirm: async () => {
      await api("/admin/shutdown", { method: "POST", body: {} });
      const view = document.getElementById("view");
      if (view) {
        view.innerHTML = `<div class="loading-screen" style="min-height:60vh">
          <div class="brand-mark" style="width:54px;height:54px">${icon("shield")}</div>
          <h2 style="margin:0;font-size:18px;color:var(--text)">FinVault has stopped</h2>
          <p style="max-width:420px;text-align:center;margin:0">Your data is safe in <span class="mono">FinVault.db</span> next to the app. You can close this tab, or launch FinVault.exe again any time.</p>
        </div>`;
      }
    },
  });
}

/* -------------------------------------------------------------------------- */
/* Registry                                                                   */
/* -------------------------------------------------------------------------- */
/* -------------------------------------------------------------------------- */
/* Scheduled reminders                                                        */
/* -------------------------------------------------------------------------- */
const REMINDER_TYPES = [
  { id: "expense", name: "Bill / expense" },
  { id: "income", name: "Expected income" },
  { id: "card_payment", name: "Card payment" },
  { id: "loan_payment", name: "Loan instalment" },
  { id: "transfer", name: "Transfer" },
];

const REMINDER_FREQUENCIES = [
  { id: "once", name: "One-off" }, { id: "weekly", name: "Weekly" },
  { id: "monthly", name: "Monthly" }, { id: "quarterly", name: "Quarterly" },
  { id: "yearly", name: "Yearly" },
];

export async function addReminder(dataset = {}) {
  const editing = dataset.id ? await api(`/scheduled/${dataset.id}`) : null;
  const item = editing || {};
  const cards = state.pageData.cardsRef || [];
  const accounts = state.pageData.accountsRef || [];
  openModal({
    title: editing ? "Edit reminder" : "Add reminder",
    subtitle: "Get nudged before the payment is due.",
    body: `<div class="form-grid">
      <div class="field"><label>Owner</label><select class="select" name="person_id">${personOptions(item.person_id)}</select></div>
      <div class="field"><label>Name <span class="required">*</span></label>
        <input class="input" name="name" required maxlength="120" placeholder="e.g. Vehicle insurance" value="${attr(item.name || "")}"></div>
      <div class="field"><label>Amount</label>
        <input class="input" type="number" name="amount" step="0.01" min="0" value="${attr(item.amount ?? "")}"></div>
      <div class="field"><label>Currency</label><select class="select" name="currency">${currencyOptions(item.currency)}</select></div>
      <div class="field"><label>What is it?</label><select class="select" name="type">${options(REMINDER_TYPES, item.type || "expense")}</select></div>
      <div class="field"><label>Repeats</label><select class="select" name="frequency">${options(REMINDER_FREQUENCIES, item.frequency || "monthly")}</select></div>
      <div class="field"><label>Next due date <span class="required">*</span></label>
        <input class="input" type="date" name="next_due_date" required value="${attr(item.next_due_date || todayISO())}"></div>
      <div class="field"><label>Instalments left</label>
        <input class="input" type="number" name="installments_left" min="0" max="600" value="${attr(item.installments_left ?? 0)}"></div>
      <div class="field"><label>Charge to card</label>
        <select class="select" name="card_id">${options(cards, item.card_id || "", { placeholder: "None" })}</select></div>
      <div class="field"><label>or pay from account</label>
        <select class="select" name="account_id">${options(accounts, item.account_id || "", { placeholder: "None" })}</select></div>
      <div class="field"><label>Category</label><select class="select" name="category_id">${categoryOptions(item.category_id || "")}</select></div>
      <div class="field"><label>Status</label>
        <select class="select" name="is_active">${options([{ id: "1", name: "Active" }, { id: "0", name: "Paused" }], item.is_active ? "1" : (editing ? "0" : "1"))}</select></div>
      <div class="field span-2"><label>Notes</label><textarea class="textarea" name="notes" maxlength="1000">${esc(item.notes || "")}</textarea></div>
    </div>`,
    submitLabel: editing ? "Save changes" : "Add reminder",
    onSubmit: async (values) => {
      if (values.card_id && values.account_id) {
        toast("Pick either a card or an account, not both");
        return;
      }
      const payload = {
        person_id: values.person_id, name: values.name, amount: values.amount,
        currency: values.currency, type: values.type, frequency: values.frequency,
        next_due_date: values.next_due_date,
        installments_left: values.installments_left || 0,
        card_id: values.card_id || null, account_id: values.account_id || null,
        category_id: values.category_id || null,
        is_active: String(values.is_active) === "1", notes: values.notes,
      };
      if (editing) await api(`/scheduled/${editing.id}`, { method: "PUT", body: payload });
      else await api("/scheduled", { method: "POST", body: payload });
      toast(editing ? "Reminder updated" : "Reminder added");
      refresh();
    },
  });
}

export function deleteReminder(dataset) {
  confirmAction({
    title: "Delete reminder?",
    message: "The reminder will be removed. Transactions already recorded stay untouched.",
    onConfirm: async () => {
      await api(`/scheduled/${dataset.id}`, { method: "DELETE" });
      toast("Reminder deleted");
      refresh();
    },
  });
}

export function settleReminder(dataset) {
  const item = (state.pageData.scheduled || []).find((row) => String(row.id) === String(dataset.id)) || {};
  const linked = item.card_id || item.account_id;
  confirmAction({
    title: `Mark ${item.name ? `“${item.name}”` : "this reminder"} paid?`,
    message: linked
      ? "Records the payment as a transaction and moves the next due date forward."
      : "Moves the next due date forward. Link a card or account next time to record the payment too.",
    confirmLabel: "Mark paid",
    danger: false,
    onConfirm: async () => {
      const result = await api(`/scheduled/${dataset.id}/settle`, { method: "POST", body: { post: true } });
      toast(result.posted ? "Paid and recorded" : "Marked paid");
      refresh();
    },
  });
}

export const FORM_ACTIONS = {
  addReminder,
  editReminder: addReminder,
  deleteReminder,
  settleReminder,
  addTransaction,
  editTransaction: addTransaction,
  deleteTransaction,
  addCard,
  editCard: addCard,
  deleteCard,
  payCard,
  addStatement,
  editStatement: addStatement,
  deleteStatement,
  payStatement,
  addInstallment,
  editInstallment: addInstallment,
  deleteInstallment,
  postInstallment,
  addLoan,
  editLoan: addLoan,
  deleteLoan,
  addLoanPayment,
  addAccount,
  editAccount: addAccount,
  deleteAccount,
  transfer,
  transferFrom: transfer,
  addAsset,
  editAsset: addAsset,
  deleteAsset,
  addLiability,
  editLiability: addLiability,
  deleteLiability,
  addIncome,
  editIncome: addIncome,
  deleteIncome,
  repeatIncome,
  addPerson,
  editPerson: addPerson,
  deletePerson,
  addTaxRelief,
  editTaxRelief: addTaxRelief,
  deleteTaxRelief,
  addTaxCredit,
  editTaxCredit: addTaxCredit,
  deleteTaxCredit,
  editTaxRules,
  importCsv,
  quickAdd,
  openSearch,
  saveGeneral,
  saveFx,
  backupNow,
  restoreBackup,
  exportJson,
  exportCsv,
  exportTax,
  exportTaxCurrent,
  rotateKey,
  quitApp,
};
