/* FinVault pages: scheduled transactions and reminders. */
import {
  api, state, money, dateText, daysLabel, icon, emptyState, options, esc, personQuery,
  pageHead, statCard, panelHead,
} from "./core.js";

const FREQUENCY_LABEL = {
  once: "One-off", weekly: "Weekly", monthly: "Monthly", quarterly: "Quarterly", yearly: "Yearly",
};

const STATUS_TAG = {
  overdue: ["danger", "Overdue"],
  today: ["warning", "Today"],
  soon: ["warning", "Due soon"],
  upcoming: ["neutral", "Upcoming"],
  paused: ["neutral", "Paused"],
  done: ["success", "Done"],
};

function statusChip(status) {
  const [cls, label] = STATUS_TAG[status] || ["neutral", status || "—"];
  return `<span class="tag ${cls}">${esc(label)}</span>`;
}

function monthlyEquivalent(item) {
  const amount = Number(item.amount || 0);
  switch (item.frequency) {
    case "weekly": return amount * 52 / 12;
    case "monthly": return amount;
    case "quarterly": return amount / 3;
    case "yearly": return amount / 12;
    default: return 0;
  }
}

export async function pageScheduled() {
  const [items, cards, accounts] = await Promise.all([
    api(`/scheduled${personQuery()}`),
    api(`/cards${personQuery()}`),
    api(`/accounts${personQuery()}`),
  ]);
  state.pageData.cardsRef = cards;
  state.pageData.accountsRef = accounts;
  state.pageData.scheduled = items;

  const active = items.filter((item) => item.is_active);
  const overdue = active.filter((item) => item.status === "overdue");
  const soon = active.filter((item) => item.status === "today" || item.status === "soon");
  const monthly = active.reduce((sum, item) => sum + monthlyEquivalent(item), 0);
  const next = active
    .filter((item) => item.next_due_date)
    .sort((a, b) => String(a.next_due_date).localeCompare(String(b.next_due_date)))[0];

  return `${pageHead({
    eyebrow: "Plan",
    title: "Scheduled & reminders",
    subtitle: "Bills, premiums and instalments you want to be reminded about.",
    actions: `<button class="btn" data-action="refreshPage">${icon("refresh")} Refresh</button>
      <button class="btn btn-primary" data-action="addReminder">${icon("plus")} Add reminder</button>`,
  })}
  <div class="stat-grid">
    ${statCard({ label: "Overdue", value: String(overdue.length), foot: overdue.length ? money(overdue.reduce((s, i) => s + Number(i.amount || 0), 0)) + " to settle" : "Nothing overdue", iconName: "alert", tone: overdue.length ? "red" : "green" })}
    ${statCard({ label: "Due within 3 days", value: String(soon.length), foot: soon.length ? "Act in the next few days" : "Nothing imminent", iconName: "clock", tone: soon.length ? "amber" : "" })}
    ${statCard({ label: "Monthly commitment", value: money(monthly), foot: `${active.length} active reminder${active.length === 1 ? "" : "s"}`, iconName: "calendar" })}
    ${statCard({ label: "Next due", value: next ? dateText(next.next_due_date, "short") : "—", foot: next ? `${esc(next.name)} · ${daysLabel(next.next_due_date)}` : "Nothing scheduled", iconName: "bell" })}
  </div>

  <section class="panel">
    ${panelHead("All reminders", "Mark paid records the payment and moves the date forward", "", "bell")}
    ${items.length ? `<div class="table-wrap"><table class="table">
      <thead><tr><th>Reminder</th><th>Next due</th><th class="num">Amount</th><th>Repeats</th><th>Linked to</th><th>Status</th><th class="actions-cell"></th></tr></thead>
      <tbody>${items.map((item) => `<tr>
        <td class="main-cell"><div class="row-title">${esc(item.name)}</div>
          <div class="row-sub">${esc(item.category_name || item.notes || "")}</div></td>
        <td><div class="row-title">${esc(dateText(item.next_due_date, "short") || "—")}</div>
          <div class="row-sub">${esc(daysLabel(item.next_due_date))}</div></td>
        <td class="num">${money(item.amount, item.currency)}</td>
        <td>${esc(FREQUENCY_LABEL[item.frequency] || item.frequency)}${item.installments_left ? `<div class="row-sub">${item.installments_left} left</div>` : ""}</td>
        <td>${esc(item.card_name || item.account_name || "—")}</td>
        <td>${statusChip(item.status)}</td>
        <td class="actions-cell">
          ${item.is_active ? `<button class="btn btn-sm" data-action="settleReminder" data-id="${item.id}">Mark paid</button>` : ""}
          <button class="icon-btn small" data-action="editReminder" data-id="${item.id}" title="Edit">${icon("edit")}</button>
          <button class="icon-btn small danger" data-action="deleteReminder" data-id="${item.id}" title="Delete">${icon("trash")}</button>
        </td>
      </tr>`).join("")}</tbody></table></div>`
      : emptyState("bell", "No reminders yet", "Add rent, insurance premiums, card instalments or any bill you want to be nudged about.", `<button class="btn btn-primary" data-action="addReminder">${icon("plus")} Add reminder</button>`)}
  </section>`;
}
