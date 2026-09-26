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

# Filter buttons on publications.html: topic id -> label (in display order)
TOPICS = {
    "reasoning": "Reasoning",
    "memory": "Memory",
    "distill": "Distillation",
    "edit": "Editing",
    "llm": "Other LLM",
    "graph": "Graph & time series",
    "brain": "Brain & science",
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

    topics = p.get("topic") or "reasoning"
    topics = [topics] if isinstance(topics, str) else list(topics)
    for t in topics:
        if t not in TOPICS:
            print(f"  WARNING: unknown topic '{t}' on: {title}")
    return {
        "title": title,
        "venue": p.get("venue", ""),
        "year": int(p["year"]) if str(p.get("year", "")).isdigit() else 0,
        "authors_html": bold_owner(p.get("authors", "")),
        "topics": topics,
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
    stats = {"total": len(papers), "first_author": sum(p["first_author"] for p in papers)}
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
        {"id": tid, "label": label, "count": sum(tid in p["topics"] for p in papers)}
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
    print(f"      first-author papers: {stats['first_author']} / {stats['total']}")


if __name__ == "__main__":
    main()
