# lzyfischer.github.io

Zhenyu (Fischer) Lei's personal academic website, built with [al-folio](https://github.com/alshedivat/al-folio).

## Editing content

- **Publications** — edit `_bibliography/papers.bib`. Add a new BibTeX entry (Google Scholar → "Cite" → BibTeX gives you 90% of it) with an optional `preview` (image filename in `assets/img/publication_preview/`), `abstract`, and `selected: true` to feature it on the homepage.
- **Bio / Education / Experience / Service** — edit `_pages/about.md`.
- **News** — add a new file to `_news/` (copy an existing one and change the date + text).
- **CV** — edit `_data/cv.yml` for the on-page CV; replace `assets/pdf/CV_lzy.pdf` for the downloadable PDF button.
- **Social links / email** — edit `_data/socials.yml`.

## Local preview (optional)

```
bundle install
bundle exec jekyll serve
```

Then open http://localhost:4000/

## Deploying

Pushing to `main` triggers `.github/workflows/deploy.yml`, which builds the site and pushes it to the `gh-pages` branch. In the repo's **Settings → Pages**, set the source to deploy from the `gh-pages` branch.
