# LzyFischer.github.io

Static homepage built from YAML with a tiny Python script.

| To change…                          | edit                  |
|-------------------------------------|-----------------------|
| profile, about, news, education, honors, service | `data/site.yaml` |
| the full publication list           | `data/papers.yaml`    |
| papers on the homepage              | `data/selected.yaml`  |
| Playground: projects, resources, posts, misc | `data/playground.yaml` |
| look & layout                       | `templates/`          |

Then run locally:

```bash
pip install -r requirements.txt
python build.py        # writes index.html, publications.html, playground.html
```

or just push — `.github/workflows/build.yml` rebuilds and commits the HTML.

`research.html`, `education.html` and `about.html` are redirect stubs so old links keep working.
