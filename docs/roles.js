"use strict";
/* Role categories and seniority checks shared by every page (one copy, so pages can't disagree).
 * The finance patterns mirror fetch_jobs.py's FIN_FIELD_RE / FIN_ROLE_RE: a finance field AND an entry-type role. */
(function () {
  const FIN_FIELD = /\b(financ(e|ial)|fp\s*&\s*a|investment|investing|banking|equity\s+research|private\s+(equity|credit|markets)|venture|capital\s+markets|corporate\s+(development|finance)|corp\s*dev|treasury|valuations?|credit|m\s*&\s*a|mergers|acquisitions|asset\s+management|wealth|portfolio|fund\s+(accounting|administration|operations)|underwriting|restructuring|leveraged\s+finance|real\s+estate|market\s+risk|risk\s+management|accounting|econom(ic|ics|ist)|fixed\s+income|equities|securities|sales\s*(&|and)\s*trading)\b/i;
  const FIN_ROLE = /\b(analysts?|associates?|summer\s+analyst|analyst\s+program|rotational|rotation\s+program|new\s+grad|graduate|junior|jr\.?|entry[\s-]+level|early\s+career|campus|interns?|internship|economist)\b/i;
  const isFinance = (t) => FIN_FIELD.test(t) && FIN_ROLE.test(t);

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
    if (isFinance(t)) return "Finance";
    return "Other";
  }

  // "Entry level": the title itself says so (analyst/associate programs, new grad, junior, level I, intern...) and
  // carries no seniority marker. A plain "Software Engineer" isn't shown: it doesn't say which level it is.
  const ENTRY = /\b(new\s+grad(uate)?|graduate|university|campus|early\s+career|entry[\s-]*level|junior|jr\.?|associate|analysts?|analyst\s+program|rotational|apprentice(ship)?|interns?|internship|co-?op|summer)\b|\b(engineer|developer|analyst|scientist)\s+(i|1)\b|\b(level\s*1|l1)\b/i;
  const SENIORITY = /\b(senior|sr\.?|staff|principal|lead|manager|director|head|chief|vp|vice\s+president|president|managing|distinguished|fellow|partner|ii|iii|iv|2|3|4)\b/i;
  const isEntry = (title) => ENTRY.test(title) && !SENIORITY.test(title);

  // the role an application is filed under on the Applications page: real estate and development jobs by their
  // category (their titles, e.g. "Acquisitions Analyst", would otherwise read as finance), everything else by title
  const roleFor = (job) => ({ realestate: "Real Estate", development: "Development" })[job.category] || roleOf(job.title);

  window.ROLES = { roleOf, roleFor, isFinance, isEntry };
})();
