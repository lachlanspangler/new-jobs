"use strict";
/*
 * The only code on the site that touches browser storage. Load it first on every page.
 *
 * Normal mode: localStorage, the owner's real tracker (keys below).
 * Guest mode (any page opened with ?guest): sessionStorage instead, so a guest's applications, dismissals and
 * pipeline statuses can never reach the real data. Guest data disappears when the tab closes. Guest-ness comes only
 * from the URL: internal links carry ?guest along, and the plain link always shows the real data.
 */
(function () {
  const KEYS = {
    apps: "nj-apps", // applications: [{ key, company, title, role, tags, url, ts }]
    dismissed: "nj-dismissed", // dismissed job keys: [key]
    status: "nj-status", // pipeline status per application: { key: status }
  };
  const PREFIX = "nj-"; // every store this site owns starts with this, now and in future

  const guest = new URLSearchParams(location.search).has("guest");
  const backend = guest ? window.sessionStorage : window.localStorage;

  function get(key, fallback) {
    try {
      const v = JSON.parse(backend.getItem(key));
      return v === null || v === undefined ? fallback : v;
    } catch {
      return fallback;
    }
  }
  const set = (key, value) => backend.setItem(key, JSON.stringify(value));
  const ownKeys = () => Object.keys(backend).filter((k) => k.startsWith(PREFIX));

  /** Every store in the current mode, for export/reset: { "nj-apps": [...], ... }. */
  function snapshot() {
    const out = {};
    for (const k of new Set([...Object.values(KEYS), ...ownKeys()])) out[k] = get(k, null);
    return out;
  }
  /** Clear every store in the current mode (guest reset never touches the real data, and vice versa). */
  function resetAll() {
    for (const k of ownKeys()) backend.removeItem(k);
  }

  window.NJ = { KEYS, guest, get, set, snapshot, resetAll };

  if (!guest) return;
  // stay in guest mode across pages: carry ?guest on every internal link
  const carry = (a) => {
    const href = a.getAttribute("href");
    if (!href || /^(https?:|mailto:|#)/i.test(href)) return;
    const u = new URL(href, location.href);
    if (u.origin !== location.origin || u.searchParams.has("guest")) return;
    u.searchParams.set("guest", "");
    a.setAttribute("href", u.pathname + u.search.replace("guest=", "guest") + u.hash);
  };
  const mark = () => {
    document.querySelectorAll("a[href]").forEach((a) => {
      a.dataset.nj = "1";
      carry(a);
    });
    const brand = document.querySelector(".brand");
    if (brand && !document.querySelector(".guest-pill")) {
      const pill = document.createElement("a");
      pill.className = "guest-pill";
      pill.dataset.nj = "1"; // the way out: never gets ?guest added
      pill.href = location.pathname;
      pill.title = "Guest mode: nothing here is saved to the owner's tracker. Click to leave guest mode.";
      pill.textContent = "guest";
      brand.after(pill);
    }
  };
  mark();
  // links rendered later by page scripts (e.g. a job's company link) get the same treatment
  new MutationObserver(() => document.querySelectorAll("a[href]:not([data-nj])").forEach((a) => {
    a.dataset.nj = "1";
    carry(a);
  })).observe(document.body, { childList: true, subtree: true });
})();
