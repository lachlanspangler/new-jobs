"use strict";

const TAG_COLORS = { ai: "#b08cff", quant: "#43e08a", hedge: "#ffa94d", tech: "#34d3ee" };
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const edge = (tags) => { for (const t of tags || []) if (TAG_COLORS[t]) return TAG_COLORS[t]; return "#7c8cff"; };
const enc = encodeURIComponent;
const state = { companies: [], contacts: {}, q: "", tags: new Set(), loadApps: 0 };

function linkedinRecruiters(co) {
  return `https://www.linkedin.com/search/results/people/?keywords=${enc("recruiter OR \"talent acquisition\" " + co)}`;
}
function careers(co) { return `https://www.google.com/search?q=${enc(co + " careers software engineer")}`; }

function mailtoDraft(c, company) {
  const first = (c.name || "there").split(" ")[0];
  const subject = `Software / quant roles at ${company}`;
  const body = `Hi ${first},\n\nI'm Lachlan Spangler, a software engineer (Amazon) with a quant/low-latency background. I'm very interested in engineering and quantitative roles at ${company} and would love to connect about current openings.\n\nGitHub: https://github.com/lachlanspangler\nLinkedIn: https://linkedin.com/in/lachlan-spangler\n\nThanks for your time,\nLachlan`;
  return `mailto:${encodeURIComponent(c.email)}?subject=${enc(subject)}&body=${enc(body)}`;
}
function contactRow(c, company) {
  const conf = typeof c.confidence === "number"
    ? `<span class="pill" title="Hunter deliverability score">${c.confidence}%</span>` : "";
  const email = c.email && !c.locked
    ? `<a class="pill sal" href="${mailtoDraft(c, company)}">✉ ${esc(c.email)}</a>${conf}`
    : `<span class="pill">email locked (unlock in your data tool)</span>`;
  const li = c.linkedin ? `<a class="pill" href="${esc(c.linkedin)}" target="_blank" rel="noreferrer">LinkedIn ↗</a>` : "";
  return `<div class="rc"><b>${esc(c.name || "—")}</b><span class="rc-title">${esc(c.title || "")}</span>${email}${li}</div>`;
}

function render() {
  const q = state.q.trim().toLowerCase();
  const cos = state.companies.filter((c) =>
    (!state.tags.size || (c.tags || []).some((t) => state.tags.has(t))) &&
    (!q || c.name.toLowerCase().includes(q)));
  $("recruiters").innerHTML = cos.length ? cos.map((c) => {
    const contacts = state.contacts[c.name] || [];
    const body = contacts.length
      ? contacts.map((ct) => contactRow(ct, c.name)).join("")
      : `<div class="rc muted-note">No fetched contacts yet — use the links below (add an Apollo key to populate real contacts).</div>`;
    return `<div class="co-item">
      <button class="co-head" aria-expanded="false">
        <span class="cdot" style="background:${edge(c.tags)}"></span>
        <b>${esc(c.name)}</b>
        <span class="co-tags">${(c.tags || []).map((t) => `<span class="pill">${esc(t)}</span>`).join("")}</span>
        <span class="co-count">${contacts.length ? contacts.length + " contacts" : "search"}</span>
        <span class="co-caret">▸</span>
      </button>
      <div class="co-body"><div class="rc-body">
        ${body}
        <div class="rc-links">
          <a class="pill" href="${linkedinRecruiters(c.name)}" target="_blank" rel="noreferrer">LinkedIn recruiters ↗</a>
          <a class="pill" href="${careers(c.name)}" target="_blank" rel="noreferrer">Careers page ↗</a>
        </div>
      </div></div>
    </div>`;
  }).join("") : `<div class="empty">No companies match.</div>`;
  try { $("nav-count").textContent = (JSON.parse(localStorage.getItem("nj-apps")) || []).length; } catch {}
}

function renderTags() {
  const all = [...new Set(state.companies.flatMap((c) => c.tags || []))].sort();
  $("tags").innerHTML = "";
  all.forEach((tag) => {
    const el = document.createElement("span");
    el.className = "tag"; el.dataset.t = tag; el.textContent = tag;
    el.onclick = () => { state.tags.has(tag) ? state.tags.delete(tag) : state.tags.add(tag); el.classList.toggle("on"); render(); };
    $("tags").appendChild(el);
  });
}

$("recruiters").addEventListener("click", (e) => {
  const head = e.target.closest(".co-head");
  if (head) { const item = head.parentElement; const open = item.classList.toggle("open"); head.setAttribute("aria-expanded", open); }
});
$("q").addEventListener("input", (e) => { state.q = e.target.value; render(); });

(async function () {
  try {
    const d = await (await fetch("./jobs.json", { cache: "no-store" })).json();
    const m = new Map();
    (d.jobs || []).forEach((j) => { if (!m.has(j.company)) m.set(j.company, { name: j.company, tags: j.tags || [] }); });
    state.companies = [...m.values()].sort((a, b) => a.name.localeCompare(b.name));
  } catch {}
  try {
    const r = await fetch("./recruiters.json", { cache: "no-store" });
    if (r.ok) { const rj = await r.json(); state.contacts = rj.byCompany || {}; }
  } catch {}
  const n = Object.values(state.contacts).reduce((a, v) => a + v.length, 0);
  $("updated").textContent = n ? `${n} contacts loaded` : `${state.companies.length} companies · add Apollo key for contacts`;
  renderTags(); render();
})();
