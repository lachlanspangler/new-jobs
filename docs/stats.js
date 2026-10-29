"use strict";

const STORE = NJ.KEYS.apps;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const load = () => NJ.get(STORE, []);
const save = (a) => NJ.set(STORE, a);

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

// Reset everything: every store this site keeps (applications, dismissed jobs, pipeline statuses, and any future
// nj-* store), in the current mode only. A guest reset clears the guest session and never the real tracker.
function download(name, data) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}
function describeStores() {
  const n = (v) => (Array.isArray(v) ? v.length : v && typeof v === "object" ? Object.keys(v).length : v ? 1 : 0);
  const snap = NJ.snapshot();
  const count = (k, one, many) => { const c = n(snap[k]); return `${c} ${c === 1 ? one : many}`; };
  const parts = [count(NJ.KEYS.apps, "application", "applications"), count(NJ.KEYS.dismissed, "dismissed job", "dismissed jobs"),
    count(NJ.KEYS.status, "pipeline status", "pipeline statuses")];
  const other = Object.keys(snap).filter((k) => !Object.values(NJ.KEYS).includes(k) && snap[k] !== null);
  if (other.length) parts.push(`${other.length} other saved ${other.length === 1 ? "setting" : "settings"}`);
  return (NJ.guest ? "Clears this guest session: " : "Deletes everything this browser has saved for new-jobs: ") +
    parts.join(", ") + ".";
}
const box = $("reset-box");
const showReset = (open) => { box.hidden = !open; $("reset").setAttribute("aria-expanded", String(open)); };
$("reset").addEventListener("click", () => {
  $("reset-what").textContent = describeStores();
  showReset(true);
  $("reset-export").focus();
});
$("reset-cancel").addEventListener("click", () => { showReset(false); $("reset").focus(); });
$("reset-export").addEventListener("click", () =>
  download(`new-jobs-backup-${new Date().toISOString().slice(0, 10)}.json`, NJ.snapshot()));
$("reset-confirm").addEventListener("click", () => {
  NJ.resetAll();
  showReset(false);
  render();
  $("reset").focus();
});
$("export").addEventListener("click", () => download("applications.json", load()));

render();
