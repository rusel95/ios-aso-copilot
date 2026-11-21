# Export and page: from the store to what a person looks at

Two commands, both offline. `export` turns the store into `data/`; `build` turns `data/` into one page.
Neither reads the network, and the export does not read the clock: it is told its day.

```bash
python3 "$COPILOT" export --store "$STORE" --as-of YYYY-MM-DD   # writes data/ and STATE.md; prints the day it used
python3 "$COPILOT" export --store "$STORE" --as-of YYYY-MM-DD --check   # writes nothing; fails if data/ differs
python3 "$COPILOT" build  --store "$STORE" [--out DIR]           # data/ → DIR/index.html (default: <store>/public)
python3 "$COPILOT" check  --store "$STORE"                       # looks through data/ for what must not be published
python3 "$COPILOT" due    --store "$STORE" [--as-of YYYY-MM-DD]  # the rank reads live hypotheses still need
```

Without `--as-of` the day is today and the command prints `as of <day>`, so the run can be repeated. Run
the same export twice and the second says `0 written`; build twice and the two pages are byte for byte the
same. That is the test of the whole chain, and `export --check` is how a scheduled job proves it.

An export for a day before the one `data/` already holds would delete every file of the days after it, so it is
refused (`FAIL export: data/ is as of …`) unless `--rewind` is given. `--check` writes nothing and needs no flag.

## Several projects

A project's output lives in its own store: `<app repo>/marketing/data/` and `<app repo>/marketing/public/`.
Nothing is shared and nothing has to be configured: point `--store` at another project and its files land
there. To gather several pages in one place, give each its own folder: `build --store A/marketing --out
site/a`, `build --store B/marketing --out site/b`.

## What `data/` holds

Contract `aso-copilot/dashboard-data@1`. Every file is canonical JSON (sorted keys, one-space indent, a
final newline), so a change in a figure is a one-line diff.

| File | One per | Holds |
|---|---|---|
| `week/<monday>.json` | closed Monday week | the flow families: `store_funnel`, `lifecycle`, `money`, `ads`, `in_app` |
| `snapshot/<date>.json` | day something was read | the stock families: `ranks`, `coverage`, `demand`, `impression_share`, `subscriptions`, `ratings`, `charts` |
| `hypotheses.json` | store | each hypothesis: state on the export's day, window, basket, reads in the window, and its verdict reasoning |
| `keys.json` | store | each tracked key: its position on every sweep date, its movement, its priority row |
| `events.json` | store | the queue entries and the releases |
| `notes.json` | store | the newest `decisions.md` entries and the latest cycle report, as written |

## The written parts

Judgement is not a figure, and the page does not make it: it shows what the store's own files say, as written, and the
catalog (`prose`) states the rule for each. All of it is plain escaped text; no markdown is interpreted.

| Part | Read from | Rule |
|---|---|---|
| `reasoning` in `hypotheses.json` | the hypothesis file's `## Verdict reasoning` section | the newest day in the heading wins (`## Verdict reasoning (2026-10-25)`); an undated section loses to a dated one, and of two equal the later in the file stands. The section runs to the next `#` or `##` heading, so its `###` parts stay in. `null` when the file has none. Read as the file stands today, whatever `--as-of` says |
| `decisions` in `notes.json` | `decisions.md`, entries headed `## <day> — <title>` | the newest eight dated on or before `--as-of`, newest first, each cut at a line end past 6,000 characters (`truncated`). A `##` heading that is not an entry is reported and left out |
| `report` in `notes.json` | `reports/*cycle*.md` (so `aso_cycle_<day>.md` and `aso_full_cycle_<day>.md`) | the newest by the last day in its file name, on or before `--as-of`, cut at a line end past 30,000 characters; `null` when there is none |

The export masks the store's own account identifiers in this text, as in a confound, and says so in a `NOTE`.

A family carries its `source` and `fetched_at` once, then its figures. A figure is a `value`, with
`numerator` and `denominator` when it is a ratio, and `by_market` (and `by_campaign` for ads) when it
splits. What a figure means, its unit and how exact it is are static facts and live in
`assets/dashboard/catalog.json`, not in every file.

Apple's own weekly figures (search popularity, impression share) sit on the last day of the week they measure,
whenever they were read, so a history pull of fifty weeks is fifty snapshots; `fetched_at` says when each was read.

A week is shown only once it has closed (from the Monday after it). A figure the store cannot give is not a
zero and not a blank: it is `unavailable` with a code and a sentence.

| Code | Means |
|---|---|
| `no_source` | nothing stores this figure for this store yet |
| `no_data` | the source is stored, and holds nothing for this period |
| `not_configured` | the store's `config.md` lacks what the source needs |
| `unreachable` | the source was asked and did not answer |

The export prints a `NOTE` for everything it left out and why: rows a person typed into `weekly.csv`, weeks
still open, rows recorded after the export's day, a cell that is not a number. Read them; they are the
difference between "nothing happened" and "nothing was stored".

## One owner per figure

A figure is computed in one place, the ledger code under `scripts/aso/`, and the export calls it. The page
formats, sorts and draws; it computes nothing. `STATE.md` is written from the exported objects. So the
ledger report, the data files, the page and `STATE.md` cannot disagree, and a figure in a reply is quoted
from one of them.

## The page

One self-contained `index.html`: the data, the catalog, the style and the script are inside it, and it asks
nothing of the network. Tabs: Overview (headline tiles, what is due, sources and their age), Ledger
(hypotheses by state; every hypothesis as a row, filtered by verdict or state through `#/ledger?mark=worked`, and a
square or a row opens its card: prediction, kill criterion, confounds, the reads against the window and the reasoning
behind the verdict), Notes (the newest decisions and the latest cycle report), Keywords (rank bands sweep by sweep, every key's
positions over time, movers, the priority order), Store funnel (the funnel and the install lifecycle by
week and storefront), Money, Apple Ads (with each term's search popularity drawn across the weeks held), In-app, and How data gets here (every figure's definition and
source). A sweep that read less than half of the tracked keys is left out of trends and headlines, on the
page and in `STATE.md` alike; the share is `ranks.partial_under` in the catalog.

## Before publishing

`check` reads `data/` and reports, by file and kind and never by value: the store's own account
identifiers from `config.md`, e-mail addresses, anything shaped like a key or a token, and whatever
the `**Never publish**:` line of the store's `config.md` lists. That line is the owner's: with no line, or a
`TODO`, the check refuses; `none` says nothing more is held back.
Hypothesis prose, verdict reasoning, decisions and the cycle report are exported as written, so an address, a key or
an identifier typed into any of them will be found there.
Publishing itself is in `references/publish.md`.
