#!/usr/bin/env python3
"""Verify + add companies to companies.json by probing which ATS actually hosts
their board. For each candidate name we try slug variants against Greenhouse,
Ashby, and Lever and keep the first board that resolves with live jobs. Only
verified boards are written — no dead entries. Standard library only.

  python3 discover_companies.py            # probe candidates, append verified
  python3 discover_companies.py --dry-run  # just report what resolves
"""
import argparse, json, re, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UA = "new-jobs/1.0 (personal job search)"

# name -> tag. The prober finds the ATS + token automatically.
CANDIDATES = {
    # --- AI / ML ---
    "Perplexity": "ai", "Mistral AI": "ai", "Cohere": "ai", "Hugging Face": "ai",
    "Glean": "ai", "Contextual AI": "ai", "Adept": "ai", "Magic": "ai",
    "Stability AI": "ai", "AssemblyAI": "ai", "Deepgram": "ai", "Groq": "ai",
    "Cerebras": "ai", "Modular": "ai", "Anyscale": "ai", "Replicate": "ai",
    "Predibase": "ai", "Arize AI": "ai", "Braintrust": "ai", "LangChain": "ai",
    "Weights & Biases": "ai", "Chroma": "ai", "Qdrant": "ai", "Twelve Labs": "ai",
    "Synthesia": "ai", "Descript": "ai", "Hippocratic AI": "ai", "Ambience Healthcare": "ai",
    "Sana": "ai", "Dust": "ai", "Lindy": "ai", "Tavus": "ai", "Sana Labs": "ai",
    "Codeium": "ai", "Augment": "ai", "Tenstorrent": "ai", "Etched": "ai",
    "Sierra AI": "ai", "Standard AI": "ai", "Mem0": "ai", "Baseten": "ai",
    # --- data / dev infra / SaaS ---
    "Confluent": "tech", "HashiCorp": "tech", "Grafana Labs": "tech", "Sentry": "tech",
    "LaunchDarkly": "tech", "PagerDuty": "tech", "Retool": "tech", "dbt Labs": "tech",
    "ClickHouse": "tech", "SingleStore": "tech", "Neon": "tech", "PlanetScale": "tech",
    "Redpanda": "tech", "Astronomer": "tech", "Prefect": "tech", "Dagster Labs": "tech",
    "Monte Carlo": "tech", "PostHog": "tech", "Mixpanel": "tech", "Sigma Computing": "tech",
    "Coda": "tech", "Miro": "tech", "Loom": "tech", "Framer": "tech", "Netlify": "tech",
    "Railway": "tech", "Clerk": "tech", "WorkOS": "tech", "Stytch": "tech", "Knock": "tech",
    "Resend": "tech", "Materialize": "tech", "Timescale": "tech", "Anyscale": "tech",
    "Census": "tech", "Airplane": "tech", "Deepnote": "tech", "Mode": "tech",
    "1Password": "tech", "Tailscale": "tech", "Fastly": "tech", "Box": "tech",
    "Atlassian": "tech", "Shopify": "tech", "Wix": "tech", "Zoom": "tech",
    # --- security ---
    "Wiz": "tech", "Snyk": "tech", "SentinelOne": "tech", "CrowdStrike": "tech",
    "Abnormal Security": "tech", "Material Security": "tech", "Chainguard": "tech",
    "Sysdig": "tech", "Aqua Security": "tech", "Semgrep": "tech", "Drata": "tech",
    "Secureframe": "tech", "Orca Security": "tech", "Aembit": "tech",
    # --- fintech / payments ---
    "Plaid": "tech", "Adyen": "tech", "Checkout.com": "tech", "Marqeta": "tech",
    "Unit": "tech", "Increase": "tech", "Highnote": "tech", "Mercury": "tech",
    "Rippling": "tech", "Deel": "tech", "Justworks": "tech", "Remote": "tech",
    "Wealthfront": "tech", "Nubank": "tech", "Revolut": "tech", "Stripe": "tech",
    "Bond": "tech", "Alloy": "tech", "Sardine": "tech", "Pipe": "tech",
    # --- consumer / marketplaces / big ---
    "DoorDash": "tech", "Uber": "tech", "Lyft": "tech", "Snap": "tech",
    "Shield AI": "tech", "Applied Intuition": "tech", "Waymo": "tech", "Zoox": "tech",
    "Wayve": "tech", "Cruise": "tech", "Rivian": "tech", "Lucid Motors": "tech",
    "Skydio": "tech", "Zipline": "tech", "Relativity Space": "tech",
    "Rocket Lab": "tech", "Astranis": "tech", "K2 Space": "tech", "Hadrian": "tech",
    # --- quant / hedge / trading (ATS-hosted only) ---
    "Optiver": "quant", "Susquehanna": "quant", "Belvedere Trading": "quant",
    "Wolverine Trading": "quant", "PEAK6": "quant", "Group One Trading": "quant",
    "Radix Trading": "quant", "Headlands Technologies": "quant", "The Voleon Group": "quant",
    "Balyasny": "hedge", "Verition": "hedge", "Walleye Capital": "hedge",
    "Marshall Wace": "hedge", "Millennium": "hedge", "Bridgewater Associates": "hedge",
    "Maven Securities": "quant", "XTX Markets": "quant", "Jane Street Capital": "quant",
    "Cboe": "quant", "Trexquant": "quant", "AlphaGrep": "quant", "Tibra": "quant",
    "Millennium Management": "hedge", "Citadel Securities": "quant",
}

# tricky slugs that don't match the name (verified before writing anyway)
OVERRIDES = {
    "Weights & Biases": [("greenhouse", "wandbai"), ("ashby", "wandb")],
    "Hugging Face": [("greenhouse", "huggingface")],
    "dbt Labs": [("greenhouse", "dbtlabs")],
    "Checkout.com": [("greenhouse", "checkout")],
    "The Voleon Group": [("greenhouse", "voleon"), ("lever", "voleon")],
    "PEAK6": [("greenhouse", "peak6")],
    "Susquehanna": [("greenhouse", "sig")],
}


def slugs(name):
    base = re.sub(r"[^a-z0-9 ]", "", name.lower())
    base = re.sub(r"\b(the|inc|llc|ltd|group|company|technologies|labs?|capital|management|securities|trading|associates)\b", "", base)
    words = base.split()
    joined = "".join(words)
    out = [joined, "-".join(words), re.sub(r"[^a-z0-9]", "", name.lower())]
    seen, uniq = set(), []
    for s in out:
        if s and s not in seen:
            seen.add(s); uniq.append(s)
    return uniq


def gh_ok(tok):
    return _count(f"https://boards-api.greenhouse.io/v1/boards/{tok}/jobs", "jobs")

def ashby_ok(tok):
    return _count(f"https://api.ashbyhq.com/posting-api/job-board/{tok}", "jobs")

def lever_ok(tok):
    return _count(f"https://api.lever.co/v0/postings/{tok}?mode=json", None)


def _count(url, key):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode())
        jobs = data if key is None else data.get(key, [])
        return len(jobs) if isinstance(jobs, list) else 0
    except Exception:
        return 0


PROBES = {"greenhouse": gh_ok, "ashby": ashby_ok, "lever": lever_ok}


# tokens that resolve but belong to a different/placeholder company
BLOCK_TOKENS = {"remote", "twelve", "snyk"}


def resolve(name, tag):
    trials = OVERRIDES.get(name, [])
    for ats in ("greenhouse", "ashby", "lever"):
        for s in slugs(name):
            trials.append((ats, s))
    seen = set()
    for ats, tok in trials:
        if (ats, tok) in seen:
            continue
        seen.add((ats, tok))
        if tok in BLOCK_TOKENS:
            continue
        n = PROBES[ats](tok)
        if n > 0:
            dom = re.sub(r"[^a-z0-9]", "", name.lower().split()[0]) + ".com"
            return {"name": name, "ats": ats, "token": tok, "tags": [tag],
                    "domain": dom, "_jobs": n}
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = json.loads((ROOT / "companies.json").read_text())
    existing = {c["name"].lower() for c in cfg["companies"]}
    existing_tokens = {(c["ats"], c["token"]) for c in cfg["companies"]}

    todo = {n: t for n, t in CANDIDATES.items() if n.lower() not in existing}
    print(f"probing {len(todo)} candidates…")

    found = []
    with ThreadPoolExecutor(max_workers=24) as ex:
        for res in ex.map(lambda kv: resolve(*kv), todo.items()):
            if res and (res["ats"], res["token"]) not in existing_tokens:
                found.append(res)
                existing_tokens.add((res["ats"], res["token"]))

    found.sort(key=lambda r: -r["_jobs"])
    for r in found:
        print(f"  ✓ {r['name']:26} {r['ats']:10} {r['token']:20} ({r['_jobs']} jobs)")
    print(f"\n{len(found)} resolved / {len(todo)} probed")

    if args.dry_run:
        return
    for r in found:
        r.pop("_jobs", None)
        cfg["companies"].append(r)
    (ROOT / "companies.json").write_text(json.dumps(cfg, indent=1))
    print(f"companies.json now {len(cfg['companies'])} companies")


if __name__ == "__main__":
    main()
