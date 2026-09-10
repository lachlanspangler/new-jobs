"use strict";

const STORE = "nj-apps";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const load = () => { try { return JSON.parse(localStorage.getItem(STORE)) || []; } catch { return []; } };
const save = (a) => localStorage.setItem(STORE, JSON.stringify(a));

function tally(apps, field) {
  const m = new Map();
  apps.forEach((r) => m.set(r[field], (m.get(r[field]) || 0) + 1));
  return [...m.entries()].sort((a, b) => b[1] - a[1]);
}

function render() {
  const apps = load();
  const today = new Date().toISOString().slice(0, 10);
  $("t-total").textContent = apps.length;
  $("t-co").textContent = new Set(apps.map((r) => r.company)).size;
  $("t-roles").textContent = new Set(apps.map((r) => r.role)).size;
  $("t-today").textContent = apps.filter((r) => (r.ts || "").slice(0, 10) === today).length;

  const rowsFor = (pairs) => pairs.map(([k, n]) => `<tr><td>${esc(k)}</td><td>${n}</td></tr>`).join("") || `<tr><td colspan="2" style="color:var(--muted)">No applications yet.</td></tr>`;
  $("by-company").querySelector("tbody").innerHTML = rowsFor(tally(apps, "company"));
  $("by-role").querySelector("tbody").innerHTML = rowsFor(tally(apps, "role"));

  $("log").innerHTML = apps.slice().reverse().map((r) => `
    <li>
      <span>${esc(r.company)} · <b>${esc(r.title)}</b></span>
      <span class="pill" style="margin-left:6px">${esc(r.role)}</span>
      <a class="pill" href="${esc(r.url)}" target="_blank" rel="noreferrer">open ↗</a>
      <span style="color:var(--muted);font-size:12px">${(r.ts || "").slice(0, 10)}</span>
      <button class="rm" data-key="${esc(r.key)}" title="Remove">×</button>
    </li>`).join("") || `<li style="color:var(--muted);border:0">Nothing logged yet — click Apply on the Jobs page.</li>`;
}

$("log").addEventListener("click", (e) => {
  const b = e.target.closest(".rm");
  if (!b) return;
  save(load().filter((r) => r.key !== b.dataset.key));
  render();
});
$("clear").addEventListener("click", () => { if (confirm("Clear all logged applications?")) { save([]); render(); } });
$("export").addEventListener("click", () => {
  const blob = new Blob([JSON.stringify(load(), null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "applications.json"; a.click();
});

render();
