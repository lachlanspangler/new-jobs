# ADR 0003 — Job categories, four more job-board adapters, parallel fetching with per-host lanes

**Status:** accepted (2026-11-10)

## Context
The owner wants real estate, real estate development and finance analyst roles (entry and mid level only) next to
the software and quant roles, with a filter per category. Many of those employers (banks, REITs, brokerages,
corporates) don't use Greenhouse, Ashby or Lever.

## Decisions
1. **One category per job**, computed in `fetch_jobs.py` from the title plus the company's `tags`
   (`category_of`), shipped in `jobs.json` as `category`. Precedence: development (needs a real estate context and an
   analyst/associate-level role) → real estate (same, with a real estate field word) → quant → software for clearly
   engineering titles → finance analyst → other software. The real estate context is the company tag `realestate` or
   real estate words in the title, so one title can land differently by employer ("Acquisitions Analyst": real estate
   at JLL, finance at a bank). The three new categories are entry and mid level only: senior/staff/lead/principal/
   director/VP/MD titles, and agents, brokers and back-office titles, are dropped at fetch time. Software and quant
   keep every level (the site's toggles cover those). The page code classifies nothing; it reads `category`.
2. **Adapters only on public, unauthenticated job-board endpoints**, the ones each employer's own careers site uses:
   Oracle Cloud HCM's Candidate Experience REST API, SmartRecruiters' Posting API, iCIMS's server-rendered search
   page and SuccessFactors RMK's `/search/` page. robots.txt is honoured: iCIMS tenants that disallow `/` and
   SuccessFactors' `/services/` feeds (RSS, Unify JSON) are never used; JavaScript-only sites and anything behind
   Cloudflare are skipped. Every adapter is tested against real saved responses (`tests/fixtures/`).
3. **Big boards are searched, not read whole**: `terms` per company (or the `"finance"` preset: analyst, associate,
   software engineer, quant), with page caps (Workday 5 × 20, Oracle 4 × 25, SmartRecruiters 10 × 100, iCIMS and
   SuccessFactors 10 pages).
4. **Parallel fetching with per-host lanes**: 12 workers; at most 3 requests in flight to each shared public API
   (Greenhouse, Ashby, Lever, SmartRecruiters) and one at a time to an employer's own host (a Workday tenant, an Oracle
   pod, an iCIMS or SuccessFactors site), with the usual pacing between boards in each lane. 454 boards now take
   ~2¾ minutes, against ~7 minutes for 290 boards before, and no single host sees more load than it did.
5. **The 15,000-row export cap applies to software only**, so older analyst roles can't be crowded out by newer
   software postings.

## Consequences
- `jobs.json` grows to ~6.8 MB uncompressed (Pages serves it gzipped); job `key` formats and the tracker's storage keys
  are unchanged, so the Applications page and existing applications keep working.
- Some employers stay out of reach on purpose (custom sites, other systems, Cloudflare, robots disallows); see the
  diary for the list.
