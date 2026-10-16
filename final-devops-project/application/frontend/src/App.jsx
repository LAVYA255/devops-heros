import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api.js";

const CATEGORY_META = {
  food: { label: "Food", color: "#f59e0b", icon: "🍛" },
  transport: { label: "Transport", color: "#3b82f6", icon: "🚇" },
  rent: { label: "Rent", color: "#8b5cf6", icon: "🏠" },
  utilities: { label: "Utilities", color: "#06b6d4", icon: "💡" },
  shopping: { label: "Shopping", color: "#ec4899", icon: "🛍️" },
  health: { label: "Health", color: "#10b981", icon: "💊" },
  entertainment: { label: "Entertainment", color: "#f43f5e", icon: "🎬" },
  education: { label: "Education", color: "#6366f1", icon: "📚" },
  other: { label: "Other", color: "#64748b", icon: "📦" },
};

const thisMonth = () => new Date().toISOString().slice(0, 7);
const today = () => new Date().toISOString().slice(0, 10);

// Days of `month` that have already happened: every day of a past month, up
// to today for the current one, none for a future one. Used for the daily pace.
function daysElapsed(month) {
  const current = thisMonth();
  if (month > current) return 0;
  if (month === current) return Number(today().slice(8, 10));
  const [y, m] = month.split("-").map(Number);
  return new Date(Date.UTC(y, m, 0)).getUTCDate(); // day 0 of next month = last day of this one
}

function money(value, currency = "INR") {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(Number(value || 0));
}

const emptyForm = () => ({
  title: "",
  amount: "",
  category: "food",
  spent_on: today(),
  note: "",
});

export default function App() {
  const [month, setMonth] = useState(thisMonth());
  const [filter, setFilter] = useState("");
  const [categories, setCategories] = useState(Object.keys(CATEGORY_META));
  const [expenses, setExpenses] = useState([]);
  const [summary, setSummary] = useState(null);
  const [version, setVersion] = useState("");
  const [form, setForm] = useState(emptyForm());
  const [editingId, setEditingId] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const [list, sum] = await Promise.all([
        api.list({ month, category: filter }),
        api.summary(month),
      ]);
      setExpenses(list);
      setSummary(sum);
      setError("");
    } catch (e) {
      setError(`Could not reach the API: ${e.message}`);
    } finally {
      setLoading(false);
    }
  }, [month, filter]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api.categories().then(setCategories).catch(() => {});
    api.health().then((h) => setVersion(h.version)).catch(() => setVersion("offline"));
  }, []);

  const currency = summary?.currency || "INR";
  const usedPct = Math.min(summary?.budget_used_pct ?? 0, 100);
  const overBudget = (summary?.budget_used_pct ?? 0) > 100;
  const biggest = useMemo(
    () => Math.max(1, ...(summary?.by_category || []).map((c) => Number(c.total))),
    [summary],
  );

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const payload = { ...form, amount: String(form.amount) };
      if (editingId) {
        await api.update(editingId, payload);
      } else {
        await api.create(payload);
      }
      setForm(emptyForm());
      setEditingId(null);
      setMonth(payload.spent_on.slice(0, 7));
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function startEdit(expense) {
    setEditingId(expense.id);
    setForm({
      title: expense.title,
      amount: expense.amount,
      category: expense.category,
      spent_on: expense.spent_on,
      note: expense.note || "",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function remove(expense) {
    if (!window.confirm(`Delete "${expense.title}"?`)) return;
    try {
      await api.remove(expense.id);
      await load();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo">₹</span>
          <div>
            <h1>Kharcha</h1>
            <p>Where did the money go?</p>
          </div>
        </div>
        <label className="month">
          <span>Month</span>
          <input type="month" value={month} onChange={(e) => setMonth(e.target.value)} />
        </label>
      </header>

      {error && (
        <div className="alert" role="alert">
          {error}
          <button onClick={() => setError("")} aria-label="dismiss">
            ×
          </button>
        </div>
      )}

      <section className="cards">
        <div className="card">
          <span className="card-label">Spent this month</span>
          <strong className="card-value">{money(summary?.total, currency)}</strong>
          <span className="card-sub">
            {summary?.count ?? 0} expenses
            {summary && daysElapsed(month) > 0 &&
              ` · ${money(Number(summary.total) / daysElapsed(month), currency)} per day so far`}
          </span>
        </div>
        <div className="card">
          <span className="card-label">Monthly budget</span>
          <strong className="card-value">{money(summary?.budget, currency)}</strong>
          <span className="card-sub">set in the ConfigMap</span>
        </div>
        <div className={`card ${overBudget ? "card-danger" : ""}`}>
          <span className="card-label">{overBudget ? "Over budget by" : "Remaining"}</span>
          <strong className="card-value">
            {money(Math.abs(Number(summary?.remaining ?? 0)), currency)}
          </strong>
          <div className="meter" aria-label="budget used">
            <div
              className={`meter-fill ${overBudget ? "over" : usedPct > 80 ? "warn" : ""}`}
              style={{ width: `${usedPct}%` }}
            />
          </div>
          <span className="card-sub">{summary?.budget_used_pct ?? 0}% of budget used</span>
        </div>
      </section>

      <div className="grid">
        <section className="panel">
          <h2>{editingId ? "Edit expense" : "Add an expense"}</h2>
          <form onSubmit={submit} className="form">
            <label>
              What was it?
              <input
                required
                maxLength={120}
                placeholder="e.g. Groceries at the market"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <div className="row">
              <label>
                Amount
                <input
                  required
                  type="number"
                  min="0.01"
                  step="0.01"
                  placeholder="0.00"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                />
              </label>
              <label>
                Date
                <input
                  required
                  type="date"
                  value={form.spent_on}
                  onChange={(e) => setForm({ ...form, spent_on: e.target.value })}
                />
              </label>
            </div>
            <label>
              Category
              <select
                value={form.category}
                onChange={(e) => setForm({ ...form, category: e.target.value })}
              >
                {categories.map((c) => (
                  <option key={c} value={c}>
                    {CATEGORY_META[c]?.icon} {CATEGORY_META[c]?.label || c}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Note <span className="muted">(optional)</span>
              <input
                maxLength={500}
                value={form.note}
                onChange={(e) => setForm({ ...form, note: e.target.value })}
              />
            </label>
            <div className="actions">
              <button className="primary" disabled={busy}>
                {busy ? "Saving..." : editingId ? "Save changes" : "Add expense"}
              </button>
              {editingId && (
                <button
                  type="button"
                  className="ghost"
                  onClick={() => {
                    setEditingId(null);
                    setForm(emptyForm());
                  }}
                >
                  Cancel
                </button>
              )}
            </div>
          </form>
        </section>

        <section className="panel">
          <h2>Where it went</h2>
          {summary?.by_category?.length ? (
            <ul className="bars">
              {summary.by_category.map((c) => {
                const meta = CATEGORY_META[c.category] || CATEGORY_META.other;
                return (
                  <li key={c.category}>
                    <div className="bar-head">
                      <span>
                        {meta.icon} {meta.label}
                      </span>
                      <span className="bar-amount">{money(c.total, currency)}</span>
                    </div>
                    <div className="bar-track">
                      <div
                        className="bar-fill"
                        style={{
                          width: `${(Number(c.total) / biggest) * 100}%`,
                          background: meta.color,
                        }}
                      />
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="empty">Nothing spent this month yet.</p>
          )}
        </section>
      </div>

      <section className="panel">
        <div className="list-head">
          <h2>Expenses</h2>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="">All categories</option>
            {categories.map((c) => (
              <option key={c} value={c}>
                {CATEGORY_META[c]?.label || c}
              </option>
            ))}
          </select>
        </div>
        {loading ? (
          <p className="empty">Loading...</p>
        ) : expenses.length === 0 ? (
          <p className="empty">No expenses for this month{filter ? " in this category" : ""}.</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>What</th>
                <th>Category</th>
                <th className="num">Amount</th>
                <th aria-label="actions" />
              </tr>
            </thead>
            <tbody>
              {expenses.map((e) => {
                const meta = CATEGORY_META[e.category] || CATEGORY_META.other;
                return (
                  <tr key={e.id}>
                    <td className="muted">{e.spent_on}</td>
                    <td>
                      {e.title}
                      {e.note && <div className="note">{e.note}</div>}
                    </td>
                    <td>
                      <span className="chip" style={{ "--chip": meta.color }}>
                        {meta.icon} {meta.label}
                      </span>
                    </td>
                    <td className="num">{money(e.amount, currency)}</td>
                    <td className="row-actions">
                      <button className="ghost small" onClick={() => startEdit(e)}>
                        Edit
                      </button>
                      <button className="ghost small danger" onClick={() => remove(e)}>
                        Delete
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <footer>
        Kharcha · API {version || "..."} · FastAPI, PostgreSQL, React
      </footer>
    </div>
  );
}
