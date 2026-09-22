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
    # --- AI / ML (models, tooling, apps) ---
    "Mistral AI": "ai", "Hugging Face": "ai", "Glean": "ai", "Contextual AI": "ai",
    "Groq": "ai", "Modular": "ai", "Replicate": "ai", "Predibase": "ai",
    "Weights & Biases": "ai", "Chroma": "ai", "Qdrant": "ai", "Sourcegraph": "ai",
    "Codeium": "ai", "Augment Code": "ai", "Reka AI": "ai", "AI21 Labs": "ai",
    "Hebbia": "ai", "Rogo": "ai", "EvenUp": "ai", "Sierra AI": "ai",
    "Suki AI": "ai", "Abridge AI": "ai", "Hume AI": "ai", "HeyGen": "ai",
    "Captions": "ai", "Ideogram": "ai", "Krea": "ai", "Black Forest Labs": "ai",
    "Factory AI": "ai", "Sourcegraph": "ai", "Gamma": "ai", "Lightning AI": "ai",
    "Fal": "ai", "LlamaIndex": "ai", "Galileo": "ai", "Zilliz": "ai",
    "Runpod": "ai", "Sana Labs": "ai", "Dust": "ai", "Norm AI": "ai",
    # --- data / dev infra / SaaS ---
    "HashiCorp": "tech", "Retool": "tech", "dbt Labs": "tech", "Redpanda": "tech",
    "Dagster Labs": "tech", "Monte Carlo": "tech", "Timescale": "tech", "Census": "tech",
    "Warp": "tech", "Raycast": "tech", "The Browser Company": "tech", "Coda": "tech",
    "Zapier": "tech", "Speakeasy": "tech", "Stainless": "tech", "Inngest": "tech",
    "LiveKit": "tech", "Mux": "tech", "Chronosphere": "tech", "Cribl": "tech",
    "Tigris Data": "tech", "Turso": "tech", "Val Town": "tech",
    # --- security ---
    "Wiz": "tech", "SentinelOne": "tech", "Aqua Security": "tech", "Cyera": "tech",
    "Island": "tech", "Descope": "tech", "Persona": "tech", "Oso": "tech",
    "Tines": "tech", "Panther": "tech",
    # --- fintech / payments ---
    "Rippling": "tech", "Deel": "tech", "Increase": "tech", "Marqeta": "tech",
    "Finch": "tech", "Middesk": "tech", "Rutter": "tech", "Method Financial": "tech",
    "Wealthfront": "tech", "Ramp Business": "tech",
    # --- quant / hedge / trading (ATS-hosted only) ---
    "Optiver": "quant", "Susquehanna": "quant", "Wolverine Trading": "quant",
    "PEAK6": "quant", "Group One Trading": "quant", "Radix Trading": "quant",
    "Headlands Technologies": "quant", "Balyasny": "hedge", "Verition": "hedge",
    "Walleye Capital": "hedge", "Maven Securities": "quant", "Quantlab": "quant",
    "AlphaGrep": "quant", "Marshall Wace": "hedge", "Millennium Management": "hedge",
    # --- supplementary: startups that reliably use clean Ashby/Greenhouse slugs ---
    "Clay": "ai", "Unify": "ai", "Regie AI": "ai", "Typeface": "ai", "Observe AI": "ai",
    "PolyAI": "ai", "Parloa": "ai", "Assembled": "tech", "Forethought": "ai",
    "Photoroom": "ai", "Genmo": "ai", "Higgsfield": "ai", "Udio": "ai", "Nebius": "ai",
    "Basis": "ai", "Martian": "ai", "Wispr Flow": "ai", "Mercor AI": "ai",
    "Graphite": "tech", "Aviator": "tech", "Depot": "tech", "Blacksmith": "tech",
    "WarpStream": "tech", "Conduktor": "tech", "Estuary": "tech", "RudderStack": "tech",
    "Metabase": "tech", "Preset": "tech", "MotherDuck": "tech", "Zed Industries": "tech",
    "Deno": "tech", "Height": "tech", "Graphite Software": "tech",
    "Socket": "tech", "Endor Labs": "tech", "Nudge Security": "tech", "Push Security": "tech",
    "Dropzone AI": "tech", "Prophet Security": "tech", "Reco": "tech", "Astrix Security": "tech",
    "Pave": "tech", "Parafin": "tech", "Rho": "tech", "Puzzle": "tech", "Settle": "tech",
}

# tricky slugs that don't match the name (verified before writing anyway)
OVERRIDES = {
    "Weights & Biases": [("greenhouse", "wandbai"), ("ashby", "wandb")],
    "Hugging Face": [("greenhouse", "huggingface")],
    "dbt Labs": [("greenhouse", "dbtlabsinc"), ("greenhouse", "dbtlabs")],
    "Mistral AI": [("ashby", "mistral"), ("greenhouse", "mistral")],
    "Glean": [("greenhouse", "glean"), ("ashby", "glean"), ("greenhouse", "gleanwork")],
    "Groq": [("greenhouse", "groq"), ("lever", "groq"), ("ashby", "groq")],
    "Wiz": [("greenhouse", "wiz"), ("greenhouse", "wizinc"), ("ashby", "wiz")],
    "Retool": [("greenhouse", "retool"), ("ashby", "retool")],
    "HashiCorp": [("greenhouse", "hashicorp")],
    "Sourcegraph": [("greenhouse", "sourcegraph"), ("ashby", "sourcegraph"), ("lever", "sourcegraph")],
    "Deel": [("greenhouse", "deel"), ("ashby", "deel")],
    "Rippling": [("greenhouse", "rippling"), ("ashby", "rippling"), ("lever", "rippling")],
    "Codeium": [("greenhouse", "codeium"), ("ashby", "codeium"), ("ashby", "windsurf")],
    "Replicate": [("ashby", "replicate"), ("greenhouse", "replicate")],
    "Modular": [("greenhouse", "modular"), ("ashby", "modularai"), ("greenhouse", "modularinc")],
    "Predibase": [("greenhouse", "predibase"), ("ashby", "predibase")],
    "Chroma": [("ashby", "trychroma"), ("greenhouse", "chroma")],
    "Qdrant": [("greenhouse", "qdrant"), ("ashby", "qdrant")],
    "Timescale": [("greenhouse", "timescale")],
    "Monte Carlo": [("greenhouse", "montecarlodata"), ("ashby", "montecarlo")],
    "Redpanda": [("greenhouse", "redpandadata"), ("ashby", "redpanda")],
    "Dagster Labs": [("greenhouse", "dagsterlabs"), ("ashby", "dagster")],
    "Marqeta": [("greenhouse", "marqeta")],
    "Increase": [("ashby", "increase")],
    "Cyera": [("greenhouse", "cyera"), ("ashby", "cyera")],
    "Reka AI": [("ashby", "reka"), ("greenhouse", "reka")],
    "AI21 Labs": [("greenhouse", "ai21labs"), ("greenhouse", "ai21")],
    "Hebbia": [("ashby", "hebbia"), ("greenhouse", "hebbia")],
    "EvenUp": [("greenhouse", "evenup"), ("ashby", "evenup")],
    "Suki AI": [("greenhouse", "suki"), ("ashby", "suki")],
    "Captions": [("ashby", "captions")],
    "Black Forest Labs": [("ashby", "blackforestlabs")],
    "Factory AI": [("ashby", "factory"), ("greenhouse", "factory")],
    "Fal": [("ashby", "fal"), ("ashby", "features-and-labels")],
    "Turso": [("ashby", "turso"), ("greenhouse", "turso")],
    "Val Town": [("ashby", "valtown")],
    "Raycast": [("ashby", "raycast")],
    "The Browser Company": [("ashby", "thebrowsercompany"), ("greenhouse", "thebrowsercompany")],
    "Stainless": [("ashby", "stainless")],
    "Chronosphere": [("greenhouse", "chronosphere")],
    "Tigris Data": [("ashby", "tigris")],
    "SentinelOne": [("greenhouse", "sentinelone")],
    "Aqua Security": [("greenhouse", "aquasecurity")],
    "Panther": [("greenhouse", "pantherlabs"), ("ashby", "panther")],
    "Method Financial": [("ashby", "method"), ("greenhouse", "methodfinance")],
    "Maven Securities": [("greenhouse", "mavensecurities")],
    "Quantlab": [("greenhouse", "quantlab"), ("lever", "quantlab")],
    "Balyasny": [("greenhouse", "balyasny"), ("greenhouse", "bamfunds")],
    "The Voleon Group": [("greenhouse", "voleon"), ("lever", "voleon")],
    "PEAK6": [("greenhouse", "peak6")],
    "Susquehanna": [("greenhouse", "sig")],
    "HeyGen": [("greenhouse", "heygen")],
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
