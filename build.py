#!/usr/bin/env python3
"""
Rebuilds the site's pages (index.html, work.html, education.html,
about.html) from the files in data/.

- data/site.yaml     -> home/hero text, news, education, experience, service, about
- data/selected.yaml -> highlighted papers + a one-line pitch (references papers.yaml by title)
- data/papers.yaml   -> the papers selected.yaml can reference; only
                         `title` is required per entry, everything else
                         (authors, venue, year, description, topic icon)
                         is fetched from the Semantic Scholar API.
                         There is no full publications page — the CV
                         covers that.

Results are cached in data/cache.json so re-running the build doesn't
re-query papers you've already fetched, and so the site still builds
even if Semantic Scholar is briefly unreachable.

Usage:
    pip install -r requirements.txt
    python build.py
"""
import json
import re
import sys
from pathlib import Path

import requests
import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
DATA = ROOT / "data" / "papers.yaml"
CACHE = ROOT / "data" / "cache.json"
SITE_DATA = ROOT / "data" / "site.yaml"
SELECTED_DATA = ROOT / "data" / "selected.yaml"

# ---- who to bold in author lists -------------------------------------------------
SITE_OWNER = "Zhenyu Lei"

# ---- topic -> (color, icon) --------------------------------------------------
# Add more keywords/categories any time; unmatched papers get "general".
TOPICS = {
    "reasoning":     {"keywords": ["reasoning", "circuit", "chain-of-thought"], "color": "navy",  "icon": "circuit"},
    "memory":        {"keywords": ["memory", "agent"],                          "color": "sage",  "icon": "layers"},
    "distillation":  {"keywords": ["distill", "distillation", "teacher"],       "color": "rust",  "icon": "funnel"},
    "editing":       {"keywords": ["editing", "edit"],                         "color": "plum",  "icon": "pencil"},
    "graph":         {"keywords": ["graph", "network", "social"],              "color": "slate", "icon": "graph"},
    "brain":         {"keywords": ["brain", "disorder", "neuro", "fmri"],      "color": "sage",  "icon": "brain"},
    "molecule":      {"keywords": ["molecule", "molecular", "chemistry", "biomed"], "color": "plum", "icon": "molecule"},
    "general":       {"keywords": [], "color": "navy", "icon": "spark"},
}

ICONS = {
    "circuit":  '<circle cx="6" cy="12" r="2.4"/><circle cx="18" cy="6" r="2.4"/><circle cx="18" cy="18" r="2.4"/><line x1="8.2" y1="10.8" x2="15.8" y2="7.2"/><line x1="8.2" y1="13.2" x2="15.8" y2="16.8"/>',
    "layers":   '<path d="M12 4 3 9l9 5 9-5-9-5Z"/><path d="M3 15l9 5 9-5"/>',
    "funnel":   '<path d="M4 5h16l-6 8v6l-4-2v-4L4 5Z"/>',
    "pencil":   '<path d="M4 20l1-5 11-11 4 4-11 11-5 1Z"/>',
    "graph":    '<circle cx="6" cy="7" r="2.2"/><circle cx="6" cy="17" r="2.2"/><circle cx="18" cy="12" r="2.2"/><line x1="7.8" y1="8.2" x2="16.2" y2="11"/><line x1="7.8" y1="15.8" x2="16.2" y2="13"/>',
    "brain":    '<path d="M9 4a3 3 0 0 0-3 3v1a3 3 0 0 0-2 5 3 3 0 0 0 2 5v1a3 3 0 0 0 6 0V7a3 3 0 0 0-3-3Z"/><path d="M15 4a3 3 0 0 1 3 3v1a3 3 0 0 1 2 5 3 3 0 0 1-2 5v1a3 3 0 0 1-6 0"/>',
    "molecule": '<circle cx="6" cy="6" r="2.2"/><circle cx="18" cy="6" r="2.2"/><circle cx="12" cy="14" r="2.2"/><circle cx="6" cy="20" r="2.2"/><circle cx="18" cy="20" r="2.2"/><line x1="7.5" y1="7.5" x2="10.5" y2="12.5"/><line x1="16.5" y1="7.5" x2="13.5" y2="12.5"/><line x1="10.5" y1="15.5" x2="7.5" y2="18.5"/><line x1="13.5" y1="15.5" x2="16.5" y2="18.5"/>',
    "spark":    '<path d="M12 3v6M12 15v6M3 12h6M15 12h6"/>',
}


def load_cache():
    if CACHE.exists():
        return json.loads(CACHE.read_text())
    return {}


def save_cache(cache):
    CACHE.write_text(json.dumps(cache, indent=2))


def fetch_from_semantic_scholar(title):
    """Look up a paper by title. Returns dict or None on failure."""
    try:
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={
                "query": title,
                "fields": "title,venue,year,authors,abstract,externalIds",
                "limit": 1,
            },
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return None
        p = data[0]
        return {
            "title": p.get("title") or title,
            "venue": p.get("venue") or "",
            "year": p.get("year"),
            "authors": [a["name"] for a in p.get("authors", [])],
            "abstract": p.get("abstract") or "",
        }
    except requests.RequestException:
        return None


def bold_owner(authors):
    out = []
    for a in authors:
        if SITE_OWNER.lower() in a.lower() or a.lower() in SITE_OWNER.lower():
            out.append(f"<b>{a}</b>")
        else:
            out.append(a)
    return ", ".join(out)


def first_sentence(text, max_len=180):
    if not text:
        return ""
    text = text.strip().replace("\n", " ")
    m = re.split(r"(?<=[.!?])\s+", text)
    sent = m[0] if m else text
    if len(sent) > max_len:
        sent = sent[:max_len].rsplit(" ", 1)[0] + "…"
    return sent


def guess_topic(title, abstract):
    text = f"{title} {abstract}".lower()
    for key, spec in TOPICS.items():
        if key == "general":
            continue
        if any(kw in text for kw in spec["keywords"]):
            return key
    return "general"


def build_entry(raw, cache):
    title = raw["title"] if isinstance(raw, dict) else raw
    overrides = raw if isinstance(raw, dict) else {}

    fetched = cache.get(title)
    if fetched is None:
        print(f"  fetching: {title}")
        fetched = fetch_from_semantic_scholar(title)
        if fetched:
            cache[title] = fetched
    else:
        print(f"  cached:   {title}")

    fetched = fetched or {"title": title, "venue": "", "year": "", "authors": [], "abstract": ""}

    venue = overrides.get("venue") or fetched.get("venue") or "—"
    year = overrides.get("year") or fetched.get("year") or ""
    authors_list = fetched.get("authors") or []
    authors_html = overrides.get("authors") or (bold_owner(authors_list) if authors_list else f"<b>{SITE_OWNER}</b>")
    description = overrides.get("description") or first_sentence(fetched.get("abstract", ""))
    topic = overrides.get("topic") or guess_topic(title, fetched.get("abstract", ""))
    spec = TOPICS.get(topic, TOPICS["general"])

    return {
        "title": fetched.get("title") or title,
        "venue": f"{venue} {year}".strip() if year and str(year) not in venue else venue,
        "authors_html": authors_html,
        "description": description or "Description not found automatically — add a `description:` override in papers.yaml.",
        "color": spec["color"],
        "icon_svg": ICONS[spec["icon"]],
        "links": overrides.get("links", {}),
    }


def main():
    papers_raw = yaml.safe_load(DATA.read_text()) or []
    site = yaml.safe_load(SITE_DATA.read_text()) or {}
    selected_raw = yaml.safe_load(SELECTED_DATA.read_text()) or []
    cache = load_cache()

    # papers.yaml is only used to resolve Selected Work entries now —
    # there is no full publications page. Nothing here writes a
    # publications list to any output file.
    entries = [build_entry(p, cache) for p in papers_raw]
    save_cache(cache)

    by_title = {e["title"]: e for e in entries}
    selected = []
    for s in selected_raw:
        base = by_title.get(s["title"])
        if base is None:
            print(f"  WARNING: selected title not found in papers.yaml: {s['title']}")
            continue
        item = dict(base)
        item["pitch"] = s.get("pitch", "")
        selected.append(item)

    profile = site.get("profile", {})
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")))

    common = dict(
        profile=profile,
        cv_url=next((l["url"] for l in profile.get("links", []) if l["label"] == "CV"), "#"),
        fun_stats=site.get("fun_stats", {}),
    )

    pages = [
        ("index.html.j2", "index.html", "home", "Home",
         dict(news=site.get("news", []))),
        ("work.html.j2", "work.html", "work", "Work",
         dict(selected=selected)),
        ("education.html.j2", "education.html", "education", "Education",
         dict(education=site.get("education", []), experience=site.get("experience", []), service=site.get("service", []))),
        ("about.html.j2", "about.html", "about", "About",
         dict(about=site.get("about", []), about_json=json.dumps(site.get("about", [])))),
    ]

    for template_name, out_name, active, page_title, ctx in pages:
        template = env.get_template(template_name)
        html = template.render(active=active, page_title=page_title, **common, **ctx)
        (ROOT / out_name).write_text(html)
        print(f"  wrote {out_name}")

    print(f"\nDone. {len(selected)} selected papers rendered on work.html; no full publications page (per request).")


if __name__ == "__main__":
    main()
