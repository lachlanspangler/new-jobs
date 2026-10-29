"use strict";

const TAG_COLORS = { ai: "#b08cff", quant: "#43e08a", hedge: "#ffa94d", tech: "#34d3ee" };
const STORE = "nj-apps";
const DSTORE = "nj-dismissed";
const state = { jobs: [], q: "", city: "", role: "", newonly: false, hideapplied: false, hidestaff: false, hidesenior: false, hideintern: false, showdismissed: false, tags: new Set(), shown: 60 };

const IS_STAFF = /\bstaff\b|\bprincipal\b|\bdistinguished\b|\bfellow\b/i;
const IS_SENIOR = /\bsenior\b|\bsr\.?\b/i;
const IS_INTERN = /\bintern(ship)?s?\b|\bco-?op\b|\bapprentice\b/i;

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function loadApps() { try { return JSON.parse(localStorage.getItem(STORE)) || []; } catch { return []; } }
function saveApps(a) { localStorage.setItem(STORE, JSON.stringify(a)); }
function appliedSet() { return new Set(loadApps().map((r) => r.key)); }
function loadDismissed() { try { return new Set(JSON.parse(localStorage.getItem(DSTORE)) || []); } catch { return new Set(); } }
function saveDismissed(s) { localStorage.setItem(DSTORE, JSON.stringify([...s])); }
let DISMISSED = new Set();

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
  if (days < 1 / 24) return `${Math.max(1, Math.floor(days * 1440))}m ago`;
  if (days < 1) return `${Math.floor(days * 24)}h ago`;
  if (days < 30) return `${Math.floor(days)}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}
const edge = (tags) => { for (const t of tags || []) if (TAG_COLORS[t]) return TAG_COLORS[t]; return "#7c8cff"; };
// One local calendar day per posting, used for sorting, grouping AND labelling (they used to disagree: the group came
// from the raw string's first 10 chars, the label from local time, so late-evening UTC timestamps made two
// "Yesterday" groups). A date-only "YYYY-MM-DD" (Workday, Built In) is already a local day, not UTC midnight.
const pad = (n) => String(n).padStart(2, "0");
const localKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
function dayKey(iso) {
  const s = (iso || "").trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const d = new Date(s.replace(" ", "T"));
  return isNaN(d) ? "undated" : localKey(d);
}
const postedAt = (iso) => { const t = new Date((iso || "").replace(" ", "T")).getTime(); return isNaN(t) ? 0 : t; };
function dayLabel(key) {
  if (key === "undated") return "Undated";
  const today = new Date(), y = new Date();
  y.setDate(y.getDate() - 1);
  if (key === localKey(today)) return "Today";
  if (key === localKey(y)) return "Yesterday";
  const [yy, mm, dd] = key.split("-").map(Number);
  return new Date(yy, mm - 1, dd).toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" });
}

function filtered() {
  const q = state.q.trim().toLowerCase();
  return state.jobs.filter((j) => {
    if (!state.showdismissed && DISMISSED.has(j.key)) return false;
    if (state.tags.size && !(j.tags || []).some((t) => state.tags.has(t))) return false;
    if (state.newonly && !j.isNew) return false;
    if (state.role && roleOf(j.title) !== state.role) return false;
    const loc = (j.location || "").toLowerCase();
    if (state.city === "priority" && !j.priority) return false;
    else if (state.city && state.city !== "priority" && !loc.includes(state.city)) return false;
    if (state.hideapplied && APPLIED.has(j.key)) return false;
    if (state.hidestaff && IS_STAFF.test(j.title)) return false;
    if (state.hidesenior && IS_SENIOR.test(j.title)) return false;
    if (state.hideintern && IS_INTERN.test(j.title)) return false;
    if (!q) return true;
    return j.title.toLowerCase().includes(q) || j.company.toLowerCase().includes(q) || loc.includes(q);
  });
}

let APPLIED = new Set();

function render() {
  const list = $("list");
  const all = filtered().map((j) => ({ j, day: dayKey(j.posted), at: postedAt(j.posted) })).sort((a, b) => {
    if (a.day !== b.day) return a.day === "undated" ? 1 : b.day === "undated" ? -1 : b.day.localeCompare(a.day); // newest day first
    if (a.j.priority !== b.j.priority) return a.j.priority ? -1 : 1;                                              // then SF/CHI/NYC
    return b.at - a.at;                                                                                             // then newest
  });
  const rows = all.slice(0, state.shown).map((x) => x.j);
  if (!rows.length) { list.innerHTML = `<div class="empty">No matching roles.</div>`; }
  else {
    let html = '<div class="list-inner">', lastKey = null;
    rows.forEach((j) => {
      const key = dayKey(j.posted);
      if (key !== lastKey) { html += `<div class="day-divider">${dayLabel(key)}</div>`; lastKey = key; }
      const done = APPLIED.has(j.key), gone = DISMISSED.has(j.key);
      html += `<a class="row ${done ? "applied" : ""} ${gone ? "dismissed" : ""}" style="--edge:${edge(j.tags)}" href="${esc(j.url)}" target="_blank" rel="noreferrer" data-key="${esc(j.key)}">
          <span class="r-dot"></span>
          <span class="r-title">${esc(j.title)}</span>
          <span class="r-co">${esc(j.company)}</span>
          <span class="r-loc">${j.priority ? "★ " : ""}${esc(j.location || "—")}</span>
          ${j.salary ? `<span class="r-sal">${esc(j.salary)}</span>` : ""}
          ${j.isNew ? '<span class="r-new">new</span>' : ""}
          <span class="r-src">${esc(j.source)}</span>
          <span class="r-go">${done ? "✓ applied" : "Apply ↗"}</span>
          <button class="r-trash" data-trash="${esc(j.key)}" title="${gone ? "Restore" : "Not interested"}">${gone ? "↺" : "✕"}</button>
        </a>`;
    });
    list.innerHTML = html + "</div>";
  }
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
  DISMISSED = loadDismissed();
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
["newonly", "hideapplied", "hidestaff", "hidesenior", "hideintern", "showdismissed"].forEach((id) => $(id).addEventListener("change", (e) => { state[id] = e.target.checked; state.shown = 60; render(); }));
$("more").addEventListener("click", () => { state.shown += 60; render(); });
$("list").addEventListener("click", (e) => {
  const trash = e.target.closest(".r-trash");
  if (trash) {
    e.preventDefault(); e.stopPropagation();
    const k = trash.dataset.trash;
    DISMISSED.has(k) ? DISMISSED.delete(k) : DISMISSED.add(k);
    saveDismissed(DISMISSED); render();
    return;
  }
  const row = e.target.closest(".row");
  if (!row) return;
  const job = state.jobs.find((j) => j.key === row.dataset.key);
  if (job) { recordApply(job); render(); }  // row is a link; still opens in a new tab
});

load();
