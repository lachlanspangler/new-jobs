"use strict";

const TAG_COLORS = { ai: "#b08cff", quant: "#43e08a", hedge: "#ffa94d", tech: "#34d3ee" };
const STORE = "nj-apps";
const state = { jobs: [], q: "", city: "", role: "", newonly: false, hideapplied: false, tags: new Set(), shown: 60 };

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function loadApps() { try { return JSON.parse(localStorage.getItem(STORE)) || []; } catch { return []; } }
function saveApps(a) { localStorage.setItem(STORE, JSON.stringify(a)); }
function appliedSet() { return new Set(loadApps().map((r) => r.key)); }

function roleOf(title) {
  const t = title.toLowerCase();
  if (/c\+\+/.test(t)) return "C++ Engineer";
  if (/python/.test(t)) return "Python Engineer";
  if (/(quant|quantitative)[^.]*research|research[^.]*(quant)/.test(t)) return "Quant Researcher";
  if (/(quant|quantitative)[^.]*(develop|engineer|software)/.test(t)) return "Quant Developer";
  if (/quant/.test(t)) return "Quant";
  if (/trade\s*desk|desk\s*operations|trading operations/.test(t)) return "Trade Desk Ops";
  if (/software|\bswe\b|\bsde\b|developer|engineer|back[\s-]?end|front[\s-]?end|full[\s-]?stack|platform|infrastructure|systems?|sre|devops/.test(t))
    return "Software Engineer";
  return "Other";
}

function agoFrom(iso) {
  const t = new Date((iso || "").replace(" ", "T")).getTime();
  if (Number.isNaN(t)) return "";
  const days = (Date.now() - t) / 86400000;
  if (days < 1) return `${Math.max(1, Math.floor(days * 24))}h ago`;
  if (days < 30) return `${Math.floor(days)}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}
const edge = (tags) => { for (const t of tags || []) if (TAG_COLORS[t]) return TAG_COLORS[t]; return "#7c8cff"; };

function filtered() {
  const q = state.q.trim().toLowerCase();
  return state.jobs.filter((j) => {
    if (state.tags.size && !(j.tags || []).some((t) => state.tags.has(t))) return false;
    if (state.newonly && !j.isNew) return false;
    if (state.role && roleOf(j.title) !== state.role) return false;
    const loc = (j.location || "").toLowerCase();
    if (state.city === "priority" && !j.priority) return false;
    else if (state.city && state.city !== "priority" && !loc.includes(state.city)) return false;
    if (state.hideapplied && APPLIED.has(j.key)) return false;
    if (!q) return true;
    return j.title.toLowerCase().includes(q) || j.company.toLowerCase().includes(q) || loc.includes(q);
  });
}

let APPLIED = new Set();

function render() {
  const list = $("list");
  const all = filtered();
  const rows = all.slice(0, state.shown);
  list.innerHTML = rows.length
    ? '<div class="list-inner">' + rows.map((j) => {
        const done = APPLIED.has(j.key);
        return `<a class="row ${done ? "applied" : ""}" style="--edge:${edge(j.tags)}" href="${esc(j.url)}" target="_blank" rel="noreferrer" data-key="${esc(j.key)}">
          <span class="r-dot"></span>
          <span class="r-title">${esc(j.title)}</span>
          <span class="r-co">${esc(j.company)}</span>
          <span class="r-loc">${j.priority ? "★ " : ""}${esc(j.location || "—")}</span>
          ${j.salary ? `<span class="r-sal">${esc(j.salary)}</span>` : ""}
          ${j.isNew ? '<span class="r-new">new</span>' : ""}
          <span class="r-src">${esc(j.source)}</span>
          <span class="r-go">${done ? "✓ applied" : "Apply ↗"}</span>
        </a>`;
      }).join("") + "</div>"
    : `<div class="empty">No matching roles.</div>`;
  $("more").classList.toggle("hidden", all.length <= state.shown);
  $("s-apps").textContent = loadApps().length;
  $("nav-count").textContent = loadApps().length;
}

function recordApply(job) {
  const apps = loadApps();
  if (apps.some((r) => r.key === job.key)) return;
  apps.push({ key: job.key, company: job.company, title: job.title, role: roleOf(job.title),
              tags: job.tags || [], url: job.url, ts: new Date().toISOString() });
  saveApps(apps);
  APPLIED = appliedSet();
}

function renderTags() {
  const box = $("tags");
  const all = [...new Set(state.jobs.flatMap((j) => j.tags || []))].sort();
  box.innerHTML = "";
  all.forEach((tag) => {
    const el = document.createElement("span");
    el.className = "tag"; el.dataset.t = tag; el.textContent = tag;
    el.onclick = () => { state.tags.has(tag) ? state.tags.delete(tag) : state.tags.add(tag); el.classList.toggle("on"); state.shown = 60; render(); };
    box.appendChild(el);
  });
}

async function load() {
  APPLIED = appliedSet();
  try {
    const d = await (await fetch("./jobs.json", { cache: "no-store" })).json();
    state.jobs = d.jobs || [];
    $("s-count").textContent = d.count ?? state.jobs.length;
    $("s-new").textContent = d.new_today ?? 0;
    $("s-co").textContent = d.companies ?? 0;
    $("updated").textContent = d.generated_at ? "updated " + agoFrom(d.generated_at) : "";
    renderTags(); render();
  } catch {
    $("updated").textContent = "couldn't load jobs.json";
  }
}

["q", "city", "role"].forEach((id) => $(id).addEventListener("input", (e) => { state[id] = e.target.value; state.shown = 60; render(); }));
["newonly", "hideapplied"].forEach((id) => $(id).addEventListener("change", (e) => { state[id] = e.target.checked; render(); }));
$("more").addEventListener("click", () => { state.shown += 60; render(); });
$("list").addEventListener("click", (e) => {
  const row = e.target.closest(".row");
  if (!row) return;
  const job = state.jobs.find((j) => j.key === row.dataset.key);
  if (job) { recordApply(job); render(); }  // row is a link; still opens in a new tab
});

load();
