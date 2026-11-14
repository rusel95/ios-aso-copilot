# Publish: the page on GitHub Pages, and the reads that run by themselves

Nothing here is installed by the skill. Two workflow templates sit in `assets/workflows/`; copying one into
an app repository is the owner's step, after the decision below.

## Decide first: a public page or a private one

A GitHub Pages site is public to anyone who has its address, even when the repository is private (unless
the account has access-controlled Pages). So the first decision is the owner's: **public or private**.

- **Private.** Keep the page a local file: `ios-aso-copilot build` writes `marketing/public/index.html`,
  which opens from disk and asks nothing of the network. Or deploy the same folder to a host with access
  control. Do not copy `aso-dashboard.yml`.
- **Public.** Then say what must never leave the repository. `ios-aso-copilot check` always refuses the
  store's own account identifiers from `config.md`, e-mail addresses and anything shaped like a key. What
  else stays in (revenue, the keyword basket, hypothesis prose) is `NEVER_PUBLISH` in
  `scripts/aso/dashboard/clean.py`: a list of patterns, empty until the owner fills it. The page shows
  everything in `data/`, so what `check` lets through is what the world sees.

## The short way: `publish`

```bash
python3 "$COPILOT" publish --store "$STORE" --dry-run     # checks, builds, says what it would push
python3 "$COPILOT" publish --store "$STORE"               # pushes index.html to the gh-pages branch of the app's repository
```

`publish` is an action: it puts a page where the world can read it, so it runs only with the owner's go. It
pushes nothing unless `data/` is what the store exports for its day and the clean check passes. The page is
committed in a temporary folder and pushed from it, replacing the branch: the app's own checkout, its `main`
and its uncommitted work are not touched, and the branch always holds one commit with `index.html` and
`.nojekyll`. Run it after every `export` and the page follows the data.

Once per repository, tell GitHub to serve that branch (Settings → Pages → Deploy from a branch → `gh-pages`,
or `gh api -X POST repos/<owner>/<repo>/pages -f 'source[branch]=gh-pages' -f 'source[path]=/'`). The page
is then at `https://<owner>.github.io/<repo>/`. Serving Pages from a private repository needs a paid GitHub
plan, and the page is public either way; it carries `noindex`, which asks search engines to leave it out and
stops nobody who has the address. The export masks the store's own account identifiers where a text holds
one, and says so in a `NOTE`.

## The page from a workflow: `assets/workflows/aso-dashboard.yml`

Copy it to `.github/workflows/aso-dashboard.yml` in the app repository, replace the forty zeros with the
full commit hash of the skill commit you reviewed (a branch or a tag can move; a hash cannot), and in the
repository's settings set Pages to deploy from GitHub Actions. Commit `marketing/data/`.

On every push that changes `marketing/data/` it:

1. proves the committed data is what the store exports for its day (`export_dashboard.py --check`, with the
   day read from the data itself), so a file edited by hand never reaches the page;
2. runs `copilot.py check`;
3. builds the page with `build_site.py` and deploys it.

It collects nothing, commits nothing and holds no source credential: its permissions are reading the
repository and publishing Pages.

## The reads: `assets/workflows/rank-reads.yml`

Copy it to `.github/workflows/rank-reads.yml` and pin the skill the same way. Once a day it runs
`copilot.py due`, and when a live hypothesis is in the last three days of its window it asks the App Store
again for those storefronts only (`ledger.py refresh --markets …`) and commits `marketing/metrics/ranks.csv`
and nothing else. The search it asks needs no account, so it too holds no source credential. It needs
`contents: write` to push the observations. Not yet verified from a hosted runner: Apple may answer a data
centre's address less willingly than a home one; a failed read is stored as `error`, never as an absence.

## What these two do not do

They do not run `collect`. A job that reads App Store Connect, GA4, BigQuery, RevenueCat and Apple Ads
needs those credentials as repository secrets, and that is a decision about each of them. It is the first
item of `ROADMAP.md`; until then the pass is run by hand (or by a subagent, `references/collect.md`), and
the page updates when the exported `marketing/data/` is committed.

## Several projects

Each app repository publishes its own page from its own `marketing/data/`. To gather several pages under
one site, build each into its own folder (`build --out site/<app>`) and deploy that folder.
