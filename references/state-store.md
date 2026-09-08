# The state store

**This file is the runtime authority.** `specs/013-marketing-ops-skill/data-model.md` is the design
record the plan was built from; if the two ever disagree, this file wins, because it is what you
actually read at run time. Schema changes are made here first and back-ported there — never the
reverse.

## Location — read this before touching any path

The store is `marketing/` at the repository root, **always resolved to the main checkout of
whichever repo the session is actually in** — `$MAIN_CHECKOUT/marketing/`, computed live by
`SKILL.md` Step 1 (`git rev-parse --show-toplevel`, corrected back from a worktree). Never
`$PWD/marketing/`, never a path hardcoded to any one app's repo, never relative to wherever this
session happens to be running. A repo that runs many concurrent git worktrees needs this doubly: a
session started in one worktree must still read and write the *same* store as every other session
in that repo — never a copy under the worktree, and never another repo's store. See `SKILL.md` for
the resolution logic — do not "simplify" it to a relative or literal path, that is precisely the bug
this exists to prevent.

```text
marketing/
├── config.md            this repo's App Store Connect app id + version · static, never rewritten
├── STATE.md            read first on every run · rewritten in place · holds no authority of its own
├── decisions.md         append-only
├── queue.md             pending approvals · entries removed when executed or abandoned
├── hypotheses/
│   ├── TEMPLATE.md
│   └── H001-<slug>.md   one file per hypothesis
├── metrics/
│   ├── weekly.csv        append-only
│   └── ranks.csv         append-only
├── keywords/             tracking lists, one file per market (exists already)
├── HANDBOOK.md           the reasoning layer — cite it, never copy it (exists already)
└── README.md             (exists already)
```

Two formats, chosen by shape: **CSV for time series** (append a row, never rewrite a row), **Markdown
for records that carry reasoning** (a hypothesis is an argument, not a row). Both must stay readable
and hand-correctable in a plain text editor — a store the user cannot fix by opening it goes wrong
silently.

**Never rewrite a CSV row.** A correction is a new row with a later `recorded`/`date` and a note —
history is a ledger, not a spreadsheet cell.

## Provenance is shared vocabulary

Every `source` column below uses the closed vocabulary in `references/provenance.md`. Read that file
first; this one just names which column carries the tag in each file.

## Phase

Not stored as an entity — **computed fresh on every run**, then cached into `STATE.md` for display
only. `SKILL.md` owns the detection logic. When the cache disagrees with a live check, the live check
wins and the disagreement is shown, never silently repaired.

Track live version, candidate version/review status, and measurement readiness separately.
An update in review does not make the live app unmeasurable. Missing weekly data means volume is
unknown. P2/P3 are planning labels; 100 downloads/week and three launch weeks are not significance
or baseline-validity tests. See SKILL.md for current detection.

## Hypothesis — `hypotheses/H<NNN>-<slug>.md`

One file per hypothesis. `<NNN>` is monotonic and **never reused**, including for abandoned
hypotheses — a discarded idea keeps its number so a later reference to it stays unambiguous. Start
from `$SKILL_DIR/assets/store-template/hypotheses/TEMPLATE.md`, which carries every field below with inline
guidance.

| Field | Type | Rule |
|---|---|---|
| `id` | `H001`… | monotonic, never reused |
| `status` | `idea` / `draft` / `queued` / `staged` / `live` / `judged` / `abandoned` | |
| `phase_at_start` | a Phase value | which rigor applied — fixes how an old verdict should be read |
| `change` | text | **what** is changing — one variable only when `phase_at_start` is `P3-measure` |
| `mechanism` | text | **why** it should work — the causal story |
| `prediction` | text + number | the expected effect **and** by when |
| `kill_criterion` | text + number | what counts as failure |
| `kill_criterion_written` | date | must precede exposure; use timestamps if both are on one date |
| `went_live` | date or empty | the day the change reached the **live store**, not the day it was submitted |
| `window_days` | integer | declared per hypothesis, default 21 for a keyword change; shorter for fast feedback, longer for a slow mechanism; never bounded by a data provider's retention |
| `primary_signal` | `rank` / `funnel` | `rank` if `phase_at_start` is `P2-cold`, `funnel` if `P3-measure` |
| `verdict` | `worked` / `no-effect` / `adverse` / `withheld` | absent until judged |
| `confounds` | list | concurrent release, seasonal peak, competitor activity |

**Validation, enforced at entry, not at verdict time:**

- `change`, `mechanism`, `prediction`, `kill_criterion` must all be present. Refuse a hypothesis
  missing any of them, name which is missing, and draft prospectively when requested; never backdate a criterion after seeing outcomes.
- A criterion must be recorded before exposure. A retrospective correction is a dated amendment, not a preregistration. Keep the historical record and mark evaluation observational or withheld.
- No verdict before `went_live + window_days` has elapsed. A window shorter or longer than the
  default is accepted, with the reason recorded in the file.
- **Exposure rule**: inspect all hypothesis files and live metadata, including queued items. Map locales to storefronts and shared release changes before claiming independence. Record partial deployment and confounds.
- **Prior-verdict guard**: before drafting or accepting a hypothesis, search `hypotheses/` for a
  settled `no-effect` or `adverse` verdict on the same change. If one exists, refuse until it is
  cited and what has changed since is stated. Without this check the ledger is written but never
  consulted, and the same idea returns every quarter.

**Verdict outcomes:**

| Verdict | Condition | Action |
|---|---|---|
| `worked` | primary signal moved as predicted, CVR not down | keep; draft the next hypothesis |
| `no-effect` | sufficient precision rules out the useful effect | record evidence; sparse data is not proof that the mechanism was wrong |
| `adverse` | credible harm to a declared outcome or guardrail | evaluate a justified rollback; no assumed all-query ranking penalty |
| `withheld` | window closed but data missing, or a confound dominates | name what's missing; do not guess |

## Channel Hypothesis — `hypotheses/C<NNN>-<channel>-<slug>.md`

One file per external traffic experiment (Reddit, Threads, Twitter/X, Product Hunt, ASA). `<NNN>` is monotonic (`C001`, `C002`...) and never reused. Governed by `references/channel-playbooks.md`.

| Field | Type | Rule |
|---|---|---|
| `id` | `C001`… | monotonic, prefixed with `C` to distinguish from ASO `H` hypotheses |
| `channel` | `reddit` / `threads` / `x` / `producthunt` / `asa` | external marketing vector |
| `type` | `contextual_reply` / `dev_showcase` / `post` / `ad` | execution format |
| `status` | `idea` / `draft` / `queued` / `staged` / `live` / `judged` / `abandoned` | operational state |
| `target_community` | string (e.g. `r/iphonehelp`, `r/iosapps`) | destination community or ad group |
| `campaign_token` | string (e.g. `reddit_storage_fix`) | alphanumeric token passed in `?ct=...` |
| `tracked_link` | URL | full App Store URL with `ct` and optional `pt` |
| `prediction` | text + numbers | expected clicks and installs within window (default 7–14 days) |
| `kill_criterion` | text + numbers | removal/ban, or < N clicks in window |
| `copy_template` | text / markdown | exact native copy (English & Ukrainian) prepared for posting |
| `went_live` | date | day the post/comment/ad was actually published |
| `window_days` | integer | default 7 days for social comments, 14 days for ads/showcases |
| `verdict` | `worked` / `no-effect` / `adverse` / `withheld` | outcome judged via ASC Campaign Analytics |

**Attribution Ledger — `campaigns.csv`**: Every generated campaign link is appended to `marketing/campaigns.csv` via `scripts/campaign_link.py`. Results are cross-referenced in App Store Connect (App Analytics → Sources → Campaigns).

**Anti-Collision & Deduplication Guard**:
Before creating or proposing a new channel experiment, `campaign_link.py` and the skill check all existing `C*.md` files. If a community already has an active `queued` or `live` hypothesis (or if `r/iosapps` is under its 30-day cooldown), the skill refuses to generate a duplicate proposal and cites the existing hypothesis.



## Weekly record — `metrics/weekly.csv`

Append-only. A logical observation is keyed by period, segment, market and metric definition. Corrections retain the old row and explicitly name the superseded record; until duplicate selection is implemented, the visualizer rejects ambiguous rows.

```csv
week_start,segment,impressions,product_page_views,downloads,cvr_pct,trial_starts,source,recorded,note
2026-09-07,search,,,,,,unavailable,2026-09-14,ASC analytics not yet generated
```

- `week_start` — Monday, ISO date. Weeks are whole; never record a partial week.
- Record whether impressions and views are total or unique, and downloads first-time or total.
  Preserve the source's `cvr_pct`; ASC conversion is total downloads plus pre-orders divided by
  unique-device impressions, with Apple's pre-order counting rules. Downloads/views is not page CVR.
- `segment` and territory filters must be explicit. Search may include Apple Ads; browse is context.
  If adding an optional `market` column, preserve historical blanks as unknown, not global totals.
- `source` — a provenance tag (`user:@<date>` for a figure read off the web UI, `live:<command>@<date>`
  for one pulled by API, `absent:<reason>` when unobtainable). Never invented: an unobtainable figure
  is an empty cell tagged `absent:<reason>` — never a zero, never an estimate.
- Trial starts may come from a subscription provider or eligible ASC subscription reports; record the source and definition. They are not paid users. An optional `paid_subscribers` field must be separately observed.
- **Metrics display**: use `funnel_visualizer.py` with explicit filters; no fabricated values, fixed benchmarks, sequential funnel or inferred cash. See `references/funnel-analytics.md`.

## Rank observation — `metrics/ranks.csv`

Append-only, one row per `(date, market, keyword)`.

```csv
date,market,keyword,group,position,popularity,difficulty,source,depth,status
2026-09-08,us,compress videos,target,,58,,astro,200,beyond-depth
```

- `market` — `us` / `gb` / `de` / `ua` for the weekly set; other locales are fine for a monthly pass.
- `group` — `own` / `title` / `target` / `competitor`, matching `marketing/keywords/`.
- `position` — a blank is ambiguous without request status and depth. Only a successful query can establish not observed within the tracked depth. A
  keyword that was not checked at all is simply an absent row, not an empty-position row — the two
  are not the same thing and must not be conflated.
- Preserve source/method/depth/status, exact query, timestamp and app identity in the linked raw snapshot. A failed request is unknown. Historical rows missing these fields cannot support paired rank verdicts.
- `depth` / `status` — the queried depth and the request outcome, the two fields that make a pair
  comparable. `status` is `ok` (found, `position` set), `beyond-depth` (queried, absent within
  `depth`, `position` blank) or `error` (request failed, nothing observed). Two `beyond-depth`
  observations are not a zero delta; `ok` -> `beyond-depth` and back are events in their own right.
  `scripts/ledger.py ingest` writes these and refuses any position deeper than the result list its
  query returned, which is what a value carried over from an older snapshot looks like.
- Append on the skill's own cadence, not the tracker's retention window. History accumulates locally
  independent of how long the provider keeps it — provider retention only bounds how much can be
  back-filled on first use, never how long an experiment may run.

## Storefront economics — `metrics/markets.csv`

One row per territory, refreshed when prices change, never estimated.

```csv
territory,storefront,currency,customer_price,proceeds_local,fx_to_usd,proceeds_usd,source
DEU,de,EUR,35.99,25.71,0.860364,29.88,live:asc subscriptions pricing prices list@2026-09-08
```

- `proceeds_local` is Apple's own proceeds figure from the price record, not price minus a guessed
  commission. Pull it with `asc subscriptions pricing prices list --subscription-id ID --include
  territory,subscriptionPricePoint --paginate`.
- `fx_to_usd` carries its own date and source in `source`; it is the only estimated field, and a
  blank one leaves `proceeds_usd` blank rather than inventing a conversion.
- `storefront` is the alpha-2 code that joins to `ranks.csv`; a blank one means that territory
  cannot be ranked against the others yet.

## Decision — `decisions.md`

Append-only, newest entry last, never reordered.

```markdown
## 2026-08-19 — Buy Astro on the day the app leaves review, not before
**Evidence**: no trial, 14-day refund only; app ranks for nothing while in review, so the window
would be spent with nothing to evaluate against.
**Supersedes**: earlier "buy before launch to capture the baseline" — the baseline *is* the first
live day, so there is nothing to capture earlier.
```

Every entry: a date-stamped heading naming the choice, an **Evidence** line (provenance-tagged where
it cites a figure), and a **Supersedes** line naming what it reverses — even `none` if it's the first
decision on the topic. This is what makes a reversal legible as a reversal instead of reading as if
the new position had always been held.

## Queued action — `queue.md`

Entries removed when executed or abandoned, so this file stays short by construction.

```markdown
### Q003 · queued 2026-09-10 · fence: publishes
**Effect in plain language**: replies publicly, under your name, to the 1★ review from "mkdev".
**Command**: asc reviews respond --review-id <ID> --response "<text>"
**Preconditions**: review still unanswered; text unchanged since drafting.
```

Every entry: the **exact** runnable command with no placeholders left to fill in, the effect in one
plain-language sentence naming what changes and who sees it, and its preconditions. Re-verify
preconditions immediately before executing an approved entry — an approval given weeks ago was given
against a world that has since moved; a stale entry is re-planned, not executed on trust.

## STATE.md

Rewritten in place on every `manual`/`auto` run; `status` mode reads it but never writes it. It holds
**no authority of its own** — everything in it is derived from the files above plus a live check, and
exists only so a human can see the whole position at a glance without re-deriving it. A figure carried
into `STATE.md` keeps its **original** provenance tag; never cite `store:STATE.md` as if the cache
were the source (see `references/provenance.md`).

```markdown
# <this repo's app> — marketing state
_Last run: 2026-08-19 · mode: manual_

**Phase**: P1-review (version 1.0, WAITING_FOR_REVIEW, 0 blocking) — live-checked 2026-08-19
**Next action**: confirm App Privacy is published (web UI only — see queue Q001)

## Open hypotheses
_none_

## Drafted, waiting for an editable version
- H001 — lead with video in the app name (see hypotheses/H001-video-first.md)

## Missing weekly records
_none — measurement starts when the app is live_

## Queue
- Q001 — confirm App Privacy publish state (yours; web UI)
```

## Entity relationships

```text
Phase ──governs──▶ which rigor applies to ──▶ Hypothesis.primary_signal
                                                  │
Hypothesis ──judged against──▶ Weekly record (P3-measure)
           └──judged against──▶ Rank observation (P2-cold)
           └──produces────────▶ Decision
           └──may produce─────▶ Queued action

STATE.md ──derived from──▶ everything above + a live check (never authoritative on its own)
```

Two invariants that override everything else in this file:

1. **No file except a live check may raise confidence.** Every stored artifact can lower it (missing
   data, a confound, a stale rank) but none can establish what is true of the App Store right now.
2. **No claim leaves the skill without a provenance tag** (`references/provenance.md`).
