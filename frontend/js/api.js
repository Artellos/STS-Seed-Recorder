/**
 * api.js — thin wrapper around fetch() for all backend calls.
 * All functions return parsed JSON (or throw on non-2xx).
 */

async function apiFetch(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (res.status === 204) return null;
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

// ── Seeds ─────────────────────────────────────────────────────────────────

const API = {
  seeds: {
    list: () => apiFetch("/api/seeds"),

    create: (seed_value, name) =>
      apiFetch("/api/seeds", {
        method: "POST",
        body: JSON.stringify({ seed_value, name }),
      }),

    get: (id) => apiFetch(`/api/seeds/${id}`),

    update: (id, seed_value, name) =>
      apiFetch(`/api/seeds/${id}`, {
        method: "PUT",
        body: JSON.stringify({ seed_value, name }),
      }),

    delete: (id) =>
      apiFetch(`/api/seeds/${id}`, { method: "DELETE" }),
  },

  // ── Nodes ───────────────────────────────────────────────────────────────

  nodes: {
    add: (seed_id, act, floor, col, node_type) =>
      apiFetch(`/api/seeds/${seed_id}/nodes`, {
        method: "POST",
        body: JSON.stringify({ act, floor, col, node_type }),
      }),

    update: (id, fields) =>
      apiFetch(`/api/nodes/${id}`, {
        method: "PUT",
        body: JSON.stringify(fields),
      }),

    delete: (id) =>
      apiFetch(`/api/nodes/${id}`, { method: "DELETE" }),
  },

  // ── Connections ──────────────────────────────────────────────────────────

  connections: {
    add: (seed_id, from_node_id, to_node_id) =>
      apiFetch(`/api/seeds/${seed_id}/connections`, {
        method: "POST",
        body: JSON.stringify({ from_node_id, to_node_id }),
      }),

    delete: (id) =>
      apiFetch(`/api/connections/${id}`, { method: "DELETE" }),
  },
};
