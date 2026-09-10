"use strict";

const TAG_COLORS = { ai: "#b08cff", quant: "#43e08a", hedge: "#ffa94d", tech: "#34d3ee" };
const STORE = "nj-apps";
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const loadApps = () => { try { return JSON.parse(localStorage.getItem(STORE)) || []; } catch { return []; } };
const saveApps = (a) => localStorage.setItem(STORE, JSON.stringify(a));
let APPLIED = new Set();

const state = { jobs: [], byCo: [], q: "", tags: new Set() };

function roleOf(title) {
  const t = title.toLowerCase();
  if (/c\+\+/.test(t)) return "C++ Engineer";
  if (/python/.test(t)) return "Python Engineer";
  if (/(quant|quantitative)[^.]*research|research[^.]*(quant)/.test(t)) return "Quant Researcher";
  if (/(quant|quantitative)[^.]*(develop|engineer|software)/.test(t)) return "Quant Developer";
  if (/quant/.test(t)) return "Quant";
  if (/trade\s*desk|desk\s*operations|trading operations/.test(t)) return "Trade Desk Ops";
  return "Software Engineer";
}
function recordApply(job) {
  const apps = loadApps();
  if (apps.some((r) => r.key === job.key)) return;
  apps.push({ key: job.key, company: job.company, title: job.title, role: roleOf(job.title),
              tags: job.tags || [], url: job.url, ts: new Date().toISOString() });
  saveApps(apps); APPLIED = new Set(apps.map((r) => r.key));
}
const edge = (tags) => { for (const t of tags || []) if (TAG_COLORS[t]) return TAG_COLORS[t]; return "#7c8cff"; };

function group() {
  const m = new Map();
  state.jobs.forEach((j) => { if (!m.has(j.company)) m.set(j.company, { name: j.company, tags: j.tags || [], jobs: [] }); m.get(j.company).jobs.push(j); });
  state.byCo = [...m.values()].sort((a, b) => b.jobs.length - a.jobs.length);
}

function render() {
  const q = state.q.trim().toLowerCase();
  const cos = state.byCo.filter((c) =>
    (!state.tags.size || (c.tags || []).some((t) => state.tags.has(t))) &&
    (!q || c.name.toLowerCase().includes(q)));
  const box = $("companies");
  box.innerHTML = cos.length ? cos.map((c) => {
    const appliedN = c.jobs.filter((j) => APPLIED.has(j.key)).length;
    const rows = c.jobs.map((j) => {
      const done = APPLIED.has(j.key);
      return `<a class="row ${done ? "applied" : ""}" style="--edge:${edge(c.tags)}" href="${esc(j.url)}" target="_blank" rel="noreferrer" data-key="${esc(j.key)}">
        <span class="r-dot"></span>
        <span class="r-title">${esc(j.title)}</span>
        <span class="r-loc">${j.priority ? "★ " : ""}${esc(j.location || "—")}</span>
        ${j.salary ? `<span class="r-sal">${esc(j.salary)}</span>` : ""}
        ${j.isNew ? '<span class="r-new">new</span>' : ""}
        <span class="r-go">${done ? "✓ applied" : "Apply ↗"}</span>
      </a>`;
    }).join("");
    return `<div class="co-item" data-co="${esc(c.name)}">
      <button class="co-head" aria-expanded="false">
        <span class="cdot" style="background:${edge(c.tags)}"></span>
        <b>${esc(c.name)}</b>
        <span class="co-tags">${(c.tags || []).map((t) => `<span class="pill">${esc(t)}</span>`).join("")}</span>
        <span class="co-count">${appliedN ? `<span class="co-applied">${appliedN} applied</span> · ` : ""}${c.jobs.length} roles</span>
        <span class="co-caret">▸</span>
      </button>
      <div class="co-body"><div class="list-inner">${rows}</div></div>
    </div>`;
  }).join("") : `<div class="empty">No companies match.</div>`;
  $("nav-count").textContent = loadApps().length;
}

function renderTags() {
  const all = [...new Set(state.jobs.flatMap((j) => j.tags || []))].sort();
  $("tags").innerHTML = "";
  all.forEach((tag) => {
    const el = document.createElement("span");
    el.className = "tag"; el.dataset.t = tag; el.textContent = tag;
    el.onclick = () => { state.tags.has(tag) ? state.tags.delete(tag) : state.tags.add(tag); el.classList.toggle("on"); render(); };
    $("tags").appendChild(el);
  });
}

$("companies").addEventListener("click", (e) => {
  const row = e.target.closest(".row");
  if (row) { const job = state.jobs.find((j) => j.key === row.dataset.key); if (job) { recordApply(job); render(); } return; }
  const head = e.target.closest(".co-head");
  if (head) { const item = head.parentElement; const open = item.classList.toggle("open"); head.setAttribute("aria-expanded", open); }
});
$("q").addEventListener("input", (e) => { state.q = e.target.value; render(); });

(async function () {
  APPLIED = new Set(loadApps().map((r) => r.key));
  try {
    const d = await (await fetch("./jobs.json", { cache: "no-store" })).json();
    state.jobs = d.jobs || [];
    $("updated").textContent = `${state.byCo.length || d.companies || ""} companies`;
    group(); renderTags(); render();
    $("updated").textContent = `${state.byCo.length} companies · ${d.count} roles`;
  } catch { $("updated").textContent = "couldn't load jobs.json"; }
})();
