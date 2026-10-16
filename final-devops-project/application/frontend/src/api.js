// All calls use relative URLs. Whoever serves the page (Vite in dev, nginx in
// the container, the Ingress in Kubernetes) routes /api to the backend, so the
// frontend never needs to know where the backend lives.

async function request(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (resp.status === 204) return null;
  const body = await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail = body?.detail;
    const message = Array.isArray(detail)
      ? detail.map((d) => d.msg.replace(/^Value error, /, "")).join("; ")
      : detail || `Request failed (${resp.status})`;
    throw new Error(message);
  }
  return body;
}

export const api = {
  health: () => request("/health"),
  categories: () => request("/api/categories"),
  list: ({ month, category } = {}) => {
    const params = new URLSearchParams();
    if (month) params.set("month", month);
    if (category) params.set("category", category);
    return request(`/api/expenses?${params}`);
  },
  summary: (month) => request(`/api/expenses/summary?month=${month}`),
  create: (data) => request("/api/expenses", { method: "POST", body: JSON.stringify(data) }),
  update: (id, data) =>
    request(`/api/expenses/${id}`, { method: "PUT", body: JSON.stringify(data) }),
  remove: (id) => request(`/api/expenses/${id}`, { method: "DELETE" }),
};
