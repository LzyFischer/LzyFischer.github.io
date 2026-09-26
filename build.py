#!/usr/bin/env python3
"""
Builds index.html and publications.html from the files in data/.

  data/site.yaml      profile, about, news, education, honors, service, misc
  data/papers.yaml    the full publication list (publications.html)
  data/selected.yaml  which papers appear under "Selected Research" on the homepage

Any paper in papers.yaml that is missing venue / year / authors is looked up
on Semantic Scholar and cached in data/cache.json, so the build still works
offline once a paper has been fetched.

Usage:
    pip install -r requirements.txt
    python build.py
"""
import datetime
import html
import json
import re
from pathlib import Path

import requests
import yaml
from jinja2 import Environment, FileSystemLoader

ROOT = Path(__file__).parent
DATA = ROOT / "data"
CACHE = DATA / "cache.json"

SITE_OWNER = "Zhenyu Lei"  # bolded in every author list

# Filter buttons on publications.html: topic id -> label
TOPICS = {
    "llm": "LLM reasoning & distillation",
    "edit": "Knowledge editing",
    "brain": "Brain & science",
    "graph": "Graph learning",
}


def load_yaml(name, default):
    path = DATA / name
    return (yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None) or default


def load_cache():
    return json.loads(CACHE.read_text()) if CACHE.exists() else {}


def fetch_from_semantic_scholar(title):
    try:
        r = requests.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": title, "fields": "title,venue,year,authors", "limit": 1},
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
        }
    except requests.RequestException:
        return None


def fetch_scholar_citations(scholar_id):
    """Total citations from a Google Scholar profile, or None if Scholar can't be reached."""
    try:
        r = requests.get(
            "https://scholar.google.com/citations",
            params={"user": scholar_id, "hl": "en"},
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"},
            timeout=10,
        )
        r.raise_for_status()
        m = re.search(r'<td class="gsc_rsb_std">(\d+)</td>', r.text)
        return int(m.group(1)) if m else None
    except requests.RequestException:
        return None


def citation_count(stats, cache):
    """Fresh Scholar count if reachable, else the last cached one, else the manual value."""
    sid = stats.get("scholar_id")
    fresh = fetch_scholar_citations(sid) if sid else None
    if fresh is not None:
        cache["_scholar"] = {"citations": fresh, "fetched": datetime.date.today().isoformat()}
        return fresh
    cached = cache.get("_scholar", {}).get("citations")
    manual = stats.get("citations")
    candidates = [c for c in (cached, manual) if isinstance(c, int)]
    return max(candidates) if candidates else None


def is_first_author(authors_text):
    """True if the site owner is first author, or a co-first author marked with *."""
    names = [n.strip() for n in authors_text.split(",")]
    if not names:
        return False
    if names[0].rstrip("*") == SITE_OWNER:
        return True
    return names[0].endswith("*") and f"{SITE_OWNER}*" in names


def bold_owner(authors_text):
    """Escape the author string and bold the site owner (keeps a trailing *)."""
    escaped = html.escape(authors_text)
    return re.sub(
        re.escape(SITE_OWNER) + r"\*?",
        lambda m: f"<b>{m.group(0)}</b>",
        escaped,
    )


def build_paper(raw, cache):
    p = {"title": raw} if isinstance(raw, str) else dict(raw)
    title = p["title"]

    if not all(p.get(k) for k in ("venue", "year", "authors")):
        fetched = cache.get(title)
        if fetched is None:
            print(f"  fetching: {title}")
            fetched = fetch_from_semantic_scholar(title)
            if fetched:
                cache[title] = fetched
        fetched = fetched or {}
        authors = fetched.get("authors") or []
        if isinstance(authors, str):  # older cache entries
            authors = [a.strip(" '[]") for a in authors.split(",")]
        p.setdefault("year", fetched.get("year") or "")
        venue = fetched.get("venue") or ""
        if venue and p.get("year") and str(p["year"]) not in venue:
            venue = f"{venue} {p['year']}"
        p.setdefault("venue", venue or "Preprint")
        p.setdefault("authors", ", ".join(authors) or SITE_OWNER)

    topic = p.get("topic") or "llm"
    return {
        "title": title,
        "venue": p.get("venue", ""),
        "year": int(p["year"]) if str(p.get("year", "")).isdigit() else 0,
        "authors_html": bold_owner(p.get("authors", "")),
        "topic": topic,
        "tag": p.get("tag", ""),
        "links": p.get("links") or {},
        "first_author": is_first_author(p.get("authors", "")),
    }


def main():
    site = load_yaml("site.yaml", {})
    papers_raw = load_yaml("papers.yaml", [])
    selected_raw = load_yaml("selected.yaml", [])

    cache = load_cache()
    papers = [build_paper(p, cache) for p in papers_raw]
    stats_cfg = site.get("stats") or {}
    sid = stats_cfg.get("scholar_id")
    stats = {
        "citations": citation_count(stats_cfg, cache),
        "first_author": sum(p["first_author"] for p in papers),
        "scholar_url": f"https://scholar.google.com/citations?user={sid}&hl=en" if sid else "",
    }
    CACHE.write_text(json.dumps(cache, indent=2))

    by_title = {p["title"]: p for p in papers}
    selected = []
    for s in selected_raw:
        t = s["title"] if isinstance(s, dict) else s
        if t in by_title:
            selected.append(by_title[t])
        else:
            print(f"  WARNING: selected title not in papers.yaml: {t}")

    # group the full list by year (newest first, keeping file order inside a year)
    years = sorted({p["year"] for p in papers}, reverse=True)
    groups = [{"year": y or "Other", "papers": [p for p in papers if p["year"] == y]} for y in years]
    topic_counts = [
        {"id": tid, "label": label, "count": sum(p["topic"] == tid for p in papers)}
        for tid, label in TOPICS.items()
    ]
    topic_counts = [t for t in topic_counts if t["count"]]

    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=False)
    common = dict(
        site=site,
        profile=site.get("profile", {}),
        updated=datetime.date.today().strftime("%b %Y"),
        year_now=datetime.date.today().year,
    )
    pages = [
        ("index.html.j2", "index.html", "home", dict(selected=selected, stats=stats)),
        ("publications.html.j2", "publications.html", "publications",
         dict(groups=groups, total=len(papers), topics=topic_counts)),
    ]
    for tpl, out, active, ctx in pages:
        (ROOT / out).write_text(env.get_template(tpl).render(active=active, **common, **ctx), encoding="utf-8")
        print(f"  wrote {out}")

    print(f"\nDone: {len(selected)} selected on the homepage, {len(papers)} papers on publications.html.")
    print(f"      citations: {stats['citations'] if stats['citations'] is not None else 'unavailable'}, "
          f"first-author papers: {stats['first_author']}")


if __name__ == "__main__":
    main()
