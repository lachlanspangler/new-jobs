"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const STAGES = ["", "Applied", "Emailed", "Replied", "Interview", "Offer", "Rejected"];
const state = { rows: [], q: "" };

const loadApps = () => { try { return JSON.parse(localStorage.getItem("nj-apps")) || []; } catch { return []; } };
const loadStatus = () => { try { return JSON.parse(localStorage.getItem("nj-status")) || {}; } catch { return {}; } };
const saveStatus = (s) => localStorage.setItem("nj-status", JSON.stringify(s));

async function build() {
  const apps = loadApps();
  const status = loadStatus();
  const applied = {};
  apps.forEach((r) => { applied[r.company] = (applied[r.company] || 0) + 1; });

  let emailed = {};
  try {
    const o = await (await fetch("./outreach.json", { cache: "no-store" })).json();
    emailed = o.byCompany || {};
    $("updated").textContent = o.total ? `${o.total} emails logged` : "";
  } catch { /* no outreach yet */ }

  const companies = [...new Set([...Object.keys(applied), ...Object.keys(emailed)])].sort();
  state.rows = companies.map((c) => ({
    company: c,
    applied: applied[c] || 0,
    emailed: (emailed[c] || {}).emailed || 0,
    last: (emailed[c] || {}).last || "",
    // default status derived from activity if the user hasn't set one
    status: status[c] || ((emailed[c] || {}).emailed ? "Emailed" : (applied[c] ? "Applied" : "")),
  }));
  render();
}

function counts() {
  const s = loadStatus();
  const withStatus = (st) => state.rows.filter((r) => (s[r.company] || r.status) === st).length;
  $("p-applied").textContent = state.rows.filter((r) => r.applied).length;
  $("p-emailed").textContent = state.rows.filter((r) => r.emailed).length;
  $("p-replied").textContent = withStatus("Replied");
  $("p-interview").textContent = withStatus("Interview");
}

function render() {
  const q = state.q.trim().toLowerCase();
  const rows = state.rows.filter((r) => !q || r.company.toLowerCase().includes(q));
  $("pipe").innerHTML = rows.length ? rows.map((r) => `
    <tr>
      <td>${esc(r.company)}</td>
      <td>${r.applied || "·"}</td>
      <td>${r.emailed || "·"}</td>
      <td class="muted">${esc(r.last || "·")}</td>
      <td>
        <select class="pstatus" data-co="${esc(r.company)}">
          ${STAGES.map((s) => `<option value="${s}" ${s === r.status ? "selected" : ""}>${s || "—"}</option>`).join("")}
        </select>
      </td>
    </tr>`).join("") : `<tr><td colspan="5" class="muted" style="padding:20px">No activity yet — apply to roles or draft emails first.</td></tr>`;
  counts();
}

$("pipe").addEventListener("change", (e) => {
  const sel = e.target.closest(".pstatus");
  if (!sel) return;
  const status = loadStatus();
  status[sel.dataset.co] = sel.value;
  saveStatus(status);
  const row = state.rows.find((r) => r.company === sel.dataset.co);
  if (row) row.status = sel.value;
  counts();
});
$("q").addEventListener("input", (e) => { state.q = e.target.value; render(); });

build();
