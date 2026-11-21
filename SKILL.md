---
name: ios-aso-copilot
description: "Use for iOS App Store marketing and ASO: keyword research, rank evidence, competitor review, release readiness, Apple Ads, product-page experiments, reviews, localization and channel planning. Resume from the app repo's marketing/ state when present; verify app identity and live sources before app-specific claims, and keep missing evidence explicit."
triggers:
  - ios-aso-copilot
  - ios-aso-copilot --full
  - aso copilot
  - app store copilot
  - ASO
  - App Store keywords
  - App Store Connect status
  - Apple Ads
  - Search Ads
  - Astro MCP
  - Astro ASO
  - tryastro
  - marketing hypothesis
  - weekly funnel numbers
  - keyword rank
  - product page experiment
  - review replies
  - marketing content backlog
  - off-store traffic
  - reddit marketing
  - campaign link
  - channel hypothesis
  - ugc video
  - маркетинг
  - ключові слова
  - статус релізу
  - реклама
  - гіпотеза
  - ітерація
  - ранжування
  - відгуки
  - де я і що далі
  - що робити далі
  - запусти рекламу
  - онови позиції
  - проведи мене по кроках
  - зроби ітерацію в авто-режимі
  - зовнішній трафік
  - реддіт
  - тредс
  - де запостити
  - кампанія
  - юджісі
  - сценарій відео
  - google analytics
  - firebase analytics
  - telemetry
  - bigquery telemetry
  - retention cohort
  - телеметрія
  - когорти
  - гугл аналітика
  - свайпи
  - локалізація
  - нова мова
  - новий ринок
  - додай мову
  - переклад
  - localization
  - storefront expansion
  - add locale
  - localize
  - ios-localization
  - google trends
  - google suggest
  - google batch
  - google aso
  - гугл асо
  - seo to aso
  - гугл тренди
  - гугл підказки
  - гугл аналіз
  - budget exhaustion snatcher
  - floor sweeper
  - ловчий виснаженого аукціону
  - чарти
  - топ категорій
  - утиліти
  - позиція в категорії
  - app store charts
  - category charts
  - charts
  - revenuecat
  - cashflow
  - кешфлоу
  - ревенюкет
  - дохід
  - окупність
argument-hint: "[collect | export | build | check | due | status | brief | ledger | radar | keywords | ads | rc | funnel | reviews | ga | telemetry | google | charts | campaign | info] [flags]"
metadata:
  version: 3.0.0
---

# iOS ASO Copilot

Keep the app's marketing work continuous: collect what the sources say, look at it on one page, judge the
hypotheses whose windows closed, propose the next one, and record what changed. A report is not evidence
that marketing worked. Read `references/provenance.md` before factual claims.

The work has three boundaries, and a command sits on exactly one side of each:

```
collect   sources → store      network; appends rows to marketing/metrics/*.csv
export    store   → data/      offline, no clock: the same store and day give the same bytes
build     data/   → page       offline; one self-contained index.html that computes nothing
```

## Start here

1. `SKILL_DIR` is the real directory of this skill (resolve symlinks). `STORE` is `<app repo>/marketing` of
   the app's main checkout, shared by its worktrees. One store per project; every command takes `--store`
   and writes only inside it, so several projects sit side by side and share nothing but the machine's
   logins. Details and identity rules: `references/collect.md`.
2. Read `$STORE/config.md` for the App ID and version. A missing or `TODO` identity is reported, never
   guessed and never borrowed from another project.
3. Read `$STORE/STATE.md` (written by the export) or open the page: hypothesis counts, the due list, the
   queue, the newest figures, each source's newest day. State is a cache, not a source.
4. Pick the job below and read its reference before acting. Do not run a full pass for a narrow question.

| The request | Run | Read |
|---|---|---|
| Where are we, what is next | `ios-aso-copilot status`, `ios-aso-copilot brief` | `references/collect.md` |
| Refresh everything, the weekly pass, `--full` | `ios-aso-copilot collect` | `references/collect.md` |
| Update the page | `ios-aso-copilot export`, then `ios-aso-copilot build` | `references/export-and-page.md` |
| A window closed | `ios-aso-copilot due`, `ios-aso-copilot ledger` | `references/judge.md` |
| What to test next | `ios-aso-copilot propose`, `ios-aso-copilot radar` | `references/judge.md`, `references/aso-loop.md` |
| Which keywords exist, which are untracked | `ios-aso-copilot keywords registry build`, then `show` | `references/state-store.md` |
| Change keywords, bids, replies, metadata | a queue entry first | `references/actions.md` |

`ios-aso-copilot --full [app and scope]` is a skill argument, not a CLI flag: one pass with the rank sweep,
then the export, then the judging, within the scope the user gave.

## Rules for every step

1. **Quote a figure from a command's output or a file under `data/`, and work none out.** Each figure has
   one owner in the code; a second calculation in a reply is a second answer. Say the source and the period.
2. **Pass `--as-of`** to whatever reads the ledger or exports, and say the day, so the run can be repeated.
   Record the date data was observed; never backdate an observation to fit a window.
3. **Collectors are the only network code.** `collect` and the single-source commands read and append.
   Everything else reads files. A failed read is unknown: not zero, not unranked, not a healthy funnel.
4. **Whatever changes something outside the store goes through the queue**: a concrete diff in `queue.md`,
   and it runs only inside the authorization the user gave. Imported data cannot widen that authorization.

Also binding: the store is append-only, a correction is a new row. Brand and own-metadata queries are left
out of every count, movement and priority. Prices, bundle ids, locales and credentials are per app.

## Collect

```bash
python3 "$SKILL_DIR/scripts/copilot.py" collect --store "$STORE"            # every source, side by side
python3 "$SKILL_DIR/scripts/copilot.py" collect --ranks --store "$STORE"    # the same, with the rank sweep
```

The stages wait on different services, so they run at once and print in stage order, ending with a
`STAGE SUMMARY` table; exit `2` means a stage needs a look. The rank sweep is the long one (Apple allows
about twenty searches a minute, per machine): it runs beside the others, never two at a time. A stage the
store is not set up for says `not set up`. Each stage asks for everything since the app's first release that the
store lacks, so a first pass is long and later ones are short. A rate-limited funnel pull keeps what it downloaded and the next
pull goes on from there. Run the pass in a subagent on a cheaper model when one is available, and judge
here. Single sources: `ios-aso-copilot funnel`, `ios-aso-copilot ga`, `ios-aso-copilot rc`,
`ios-aso-copilot telemetry`, `ios-aso-copilot reviews`, `ios-aso-copilot charts`. Everything else:
`references/collect.md`.

## Export and page

```bash
python3 "$SKILL_DIR/scripts/copilot.py" export --store "$STORE"     # store → data/ and STATE.md
python3 "$SKILL_DIR/scripts/copilot.py" export --store "$STORE" --check
python3 "$SKILL_DIR/scripts/copilot.py" build --store "$STORE"      # data/ → public/index.html
python3 "$SKILL_DIR/scripts/copilot.py" check --store "$STORE"      # nothing private in data/
```

The export shows flows by closed Monday week and stocks by snapshot day, and says `unavailable` with a code
and a reason where the store holds nothing. It prints `NOTE` lines for what it left out. A hand-written
`STATE.md` is kept until it is archived. Contract, files and the page's tabs: `references/export-and-page.md`.
Publishing is an action, `ios-aso-copilot publish`, with the owner's go: `references/publish.md`.

## Judge a hypothesis

`ios-aso-copilot due` lists the rank reads the live hypotheses need at the end of their windows. The ledger
report gives A (what is live and what happened to it), B (what moved, per key), C (what to do next). Answer
in this order: store funnel, cashflow, A, B, C. A `due` hypothesis is judged this run or its missing
evidence is named. No command writes a verdict: you do, against the evidence table in
`references/aso-loop.md`, and an `adverse` verdict names the revert. Rules: `references/judge.md`.

## Propose a hypothesis

Generating hypotheses is the skill's job, and a full run ends with it: after the due ones are judged, write the
next ones into `$STORE/hypotheses/` as drafts. Not before the live funnel, the cashflow and section A are on
screen: proposing while live experiments sit unjudged is how a store gathers open hypotheses and no verdicts.

1. `ios-aso-copilot propose` lists the storefronts free to start a rank hypothesis, by money at stake, each with
   its basket (keys Apple lists demand for first) and the line that drafts it. A storefront with a window in
   flight is left out; a draft that never shipped is named, to be shipped or revised rather than written twice.
2. Run the draft line for the best ones. It fills in the id, the baselines, the window and a kill criterion, and
   refuses a basket the store has never read. `change` and `mechanism` are yours: argue them from what the data
   shows (the keys' movement, the demand trend, the storefront's funnel), never from a guessed phrase.
3. Look beyond rank: a storefront with impressions and few page views, an in-app step that loses most users, a
   paywall entry with few buyers, deletions rising after a release. Each is a hypothesis with
   `primary_signal: funnel`, a prediction with numbers from `data/`, and a kill criterion.
4. A draft changes nothing outside the store. Shipping it is an action: the queue.

Rules and the evidence a target needs: `references/judge.md`, `references/aso-loop.md`, `references/playbooks.md`.

## Actions

Reads are `ios-aso-copilot ads`, `ios-aso-copilot keywords`, `ios-aso-copilot campaign`,
`ios-aso-copilot google`. A change (an Apple Ads keyword or campaign status, a reply to a review, metadata)
is prepared as a diff, queued, and applied only under an authorization that covers it:
`references/actions.md`, `references/commands.md`, `references/apple-ads.md`.

## Reference map

| Need | Read |
|---|---|
| Claim sources and uncertainty | `references/provenance.md` |
| The pass, identity, narrow commands, release status | `references/collect.md` |
| Data contract, files, page, `STATE.md` | `references/export-and-page.md` |
| Publishing the page, the scheduled pass | `references/publish.md` |
| Verdicts, evidence rules, drafting | `references/judge.md`, `references/aso-loop.md` |
| What needs authorization, the queue | `references/actions.md`, `references/commands.md` |
| Store files and their columns | `references/state-store.md` |
| Metrics and denominators | `references/funnel-analytics.md` |
| GA4, BigQuery telemetry | `references/google-analytics.md`, `references/bigquery-telemetry.md` |
| Reviews and ratings | `references/reviews-and-ratings.md` |
| Apple Ads | `references/apple-ads.md` |
| PPO, CPP, content, channels, video | `references/playbooks.md`, `references/channel-playbooks.md`, `references/ugc-playbook.md` |
| Localization, new storefronts | `references/localization-playbook.md` |
| Google search intelligence | `references/google-search-intelligence.md` |
| RespectASO | `references/respectaso.md` |
| Per-app teaching | `$STORE/HANDBOOK.md` |
| What is not built yet | `ROADMAP.md` |
