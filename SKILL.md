---
name: ios-marketing-ops
description: >
  Post-launch marketing operations for this repo's App Store app: ASO / keyword iteration, App
  Store release readiness, Apple Ads setup and economics, product-page experiments, reviews,
  content backlog. Reads a persistent state store from the current repo's own marketing/ (app
  identity and numbers are per-repo, never shared across apps) and answers "where am I, what's
  next" — never starts from zero.
  Triggers on: ASO, App Store keywords, App Store Connect status/readiness, Apple Ads / Search Ads,
  marketing hypothesis or iteration, weekly funnel numbers, keyword rank, product page experiment,
  review replies, marketing content backlog — and the Ukrainian equivalents: маркетинг, ASO,
  ключові слова, статус релізу, Apple Ads / реклама, гіпотеза, ітерація, ранжування, відгуки,
  де я і що далі, що робити далі, запусти рекламу, онови позиції, проведи мене по кроках, зроби
  ітерацію в авто-режимі.
argument-hint: "[status | manual | auto] [free text]"
metadata:
  version: 1.0.0
---

# marketing-ops

Marketing for an app store runs on a cycle measured in weeks; this session's context does not. This
skill's job is continuity: read what past iterations recorded, answer **what is the single next
action**, and never re-propose something already tried. It changes nothing by default.

**Identity is per-repo; content is not, yet.** `MAIN_CHECKOUT`/`STORE` and the app id/version
(Step 1) all resolve live from whichever repo the session is in and from that repo's own
`$STORE/config.md` — nothing here hardcodes Compresso's identity. What each reference file *does*
still assume is Compresso's own numbers, honestly labeled as such where they appear: prices,
tracked locales, competitors, Apple Ads org, `marketing/HANDBOOK.md`'s reasoning. Point this skill
at a second app — symlink it into `~/.claude/skills/` (Step 1's `SKILL_DIR` note already anticipates
this) or into that repo's own `.claude/skills/` — and it reads and writes *that* repo's own
`marketing/` correctly; it will just report an uninitialized store, or thin/absent ASO content,
until that repo grows its own `config.md`/`HANDBOOK.md`/keyword lists. That per-app content is
unfinished work, not a wiring bug.

**Standing refusal rule** (FR-043, applies everywhere below): whenever you decline to act — refuse a
hypothesis, withhold a verdict, stop at the fence — say what would have to be true for you to act.
"Not yet" without a condition is not a refusal, it's a dead end.

**Standing provenance rule**: every figure, status, position or date you say out loud carries a
source tag. Read `references/provenance.md` before emitting your first claim in any run — it is not
optional polish, it is the mechanism every honesty requirement in this skill routes through.

## Step 1 — Resolve the store, always to the main checkout of the app repo

```text
SKILL_DIR     = the directory this SKILL.md file itself lives in (Claude Code reports it as
                "Base directory for this skill" when this file loads — use that value; do not
                hardcode a path here, it must resolve correctly whether this skill is installed
                per-project or symlinked into ~/.claude/skills/ for use across repos)
MAIN_CHECKOUT = `git rev-parse --show-toplevel` from the session's working directory — the root of
                whichever app repo you're actually in. For a worktree this returns the worktree's
                own path, which is wrong here (see below); resolve to the worktree's *main* checkout
                instead — `git worktree list` run from inside the worktree shows it, marked without
                a branch name in brackets, or read `.git` (a file, not a dir, in a worktree) for the
                `gitdir:` line and strip back to the shared `.git`'s parent.
STORE         = $MAIN_CHECKOUT/marketing/
APP_ID        = read from `$STORE/config.md`'s `**App ID**:` line — this repo's own App Store
                Connect app id. Never hardcoded in this skill.
VERSION       = read from `$STORE/config.md`'s `**Version**:` line — the version currently being
                worked on. Static unlike `STATE.md`: Step 8 of `auto` mode never rewrites
                `config.md`, so bump this by hand when a new version starts (same moment
                `MARKETING_VERSION` gets bumped in the Xcode project).
```

Missing `config.md`, or either field still the seeded template's placeholder → refuse and name
`$STORE/config.md` as the fix, same zero-guess rule as the uninitialized-store case below: never
invent an app id, never validate against a guessed version.

As of this writing this skill has run for real against one app, Compresso — every reference file's
worked examples, current numbers, and Apple Ads setup are still its own. A second repo now gets a
correctly-located **and correctly-identified** store (`$STORE` and `$APP_ID`/`$VERSION` all resolve
live, above); what it does *not* get automatically is that repo's own prices, tracked locales,
competitor list, or `HANDBOOK.md` reasoning — those live inside that repo's own `marketing/`, once
someone writes them, same as Compresso's do today.

`SKILL_DIR` matters for the same reason `STORE` does: every script and template path below is given
relative to it, never as a bare `scripts/...` or `assets/...` — those don't resolve unless the
session's cwd happens to already be inside this skill's own folder, which it usually isn't.

Never `$PWD/marketing/` as a shortcut for the `git rev-parse` above, and never a path relative to
this session otherwise. This project runs many concurrent git worktrees (`.claude/worktrees/*`); a
session started in any of them must still read and write the *one* store at the main checkout's
`marketing/`, never a copy under the worktree. Do not "simplify" this to a bare relative path — that
silently forks the store into one copy per worktree, which is the exact failure FR-001 exists to
rule out. If `$STORE` doesn't exist yet, that is a fact to report (uninitialized store), never a
reason to create it outside `manual`/`auto` mode — see Step 3.

## Step 2 — Detect mode

| Said | Mode |
|---|---|
| nothing, or "де я", "що далі", "статус", "status" | `status` (default — cheapest wrong guess is the one that changes nothing) |
| "manual", "по кроках", "веди мене", "проведи мене по кроках" | `manual` |
| "auto", "сам", "автоматично", "зроби ітерацію в авто-режимі" | `auto` |

Full guarantees per mode: `specs/013-marketing-ops-skill/contracts/invocation.md` (design record) —
the operative version is Step 4 below.

## Step 3 — Detect phase, live, every run

**Never read the phase from `STATE.md` as authority** — it is a cache, corrected when it disagrees.

```bash
asc validate --app $APP_ID --version $VERSION --platform IOS --output table
```

| Phase | Detected by | Rigor |
|---|---|---|
| `P0-prelaunch` | version editable **and** `asc validate` reports blocking findings | none — fix blockers |
| `P1-review` | version state `WAITING_FOR_REVIEW` / `IN_REVIEW` | none — prepare only, never measure |
| `P2-cold` | live **and** last full week's downloads < `VOLUME_THRESHOLD` | rank movement only |
| `P3-measure` | live **and** last full week's downloads ≥ `VOLUME_THRESHOLD` | full: one variable, declared windows |

`VOLUME_THRESHOLD = 100 downloads/week` — **the one named constant** both the phase boundary above
and the low-volume verdict rule in `references/aso-loop.md` (FR-026) read from. Below it, weekly
movement is indistinguishable from noise; do not let the two rules drift to different numbers.

`P2-cold` additionally carries `honeymoon = true` for the first three weeks after the app's first
live day. Honeymoon weeks are recorded normally but are **never** a valid comparison baseline
(FR-013) — if asked for one during honeymoon, refuse and state when a real baseline arrives (three
weeks after first going live).

Phase transitions are not assumed one-way: detect fresh every run, so `P1→P0` (rejected review) or
`P3→P2` (traffic collapse) need no special-casing.

**If the network is unreachable**: answer from `STATE.md` instead of failing, name which parts
couldn't be refreshed, and mark the cached phase stale with its age rather than presenting it as
freshly checked (FR-009, FR-041).

## Step 4 — Dispatch by mode

### `status` — orientation. Read-only. No exceptions.

**Zero writes of any kind, including no store initialization.** Asking a question must never create
the thing being asked about (FR-009) — if `$STORE` doesn't exist, say so and name
initialization (which happens only in `manual`/`auto`) as the next action, and stop there. The
failure mode here is specifically the helpful instinct: seeding a missing store "so there's
something to show" is itself an unrequested write. If you notice yourself about to run the `cp -n`
seed step while answering a `status` question, that is the bug, not a shortcut.

**If `$STORE` exists but `config.md` is missing or still templated**: item 1 below is the named
refusal ("app identity unresolved — fill in `$STORE/config.md`"), not a phase — phase cannot be
computed without `$APP_ID`/`$VERSION` (Step 1). Items 2–4 still print from whatever the store
already has; item 5 (the single next action) is filling in `config.md`. Narrower than the
missing-store case above: here the store exists, only its identity doesn't yet.

Output, in this fixed order, one screen, nothing else (FR-008, contracts/invocation.md):

1. **Phase**, how it was determined, and the date of the live check
2. **Open hypotheses** — each with days elapsed / days remaining before it's judgeable (read
   `hypotheses/*.md`; logic in `references/state-store.md`)
3. **Storefront Conversion Funnel & Health Status** — latest weekly or 30-day conversion metrics (Impressions → Page Views → Downloads → Trials), rendered with visual progress bars, compared against category benchmarks, with immediate bottleneck diagnosis (🔴 CRITICAL LEAK, 🟡 FAIR, 🟢 HEALTHY) using `scripts/funnel_visualizer.py` (see `references/funnel-analytics.md`)
4. **Missing weekly records** — named by week (`metrics/weekly.csv` gaps since going live)
5. **Queue** — pending approvals, oldest first (`queue.md`)
6. **The single next action** — exactly one, concrete enough to start without a follow-up question:
   the command to run, or the URL to open and what to look for there (FR-010, SC-001). "Work on
   ASO" fails this; "open <url>, check whether a Publish button is showing" satisfies it. Priority
   order when more than one thing is eligible: a release-readiness blocker outranks everything: then
   a hypothesis whose window just closed (a verdict is waiting to be written); then an overdue
   weekly recording; then drafting the next hypothesis; then queue cleanup. Pick the highest-priority
   item with something concrete to do right now and name only that one.

Run twice in a row against an unchanged store → byte-identical output, byte-identical store
(SC-010). If that's not true, something upstream wrote when it shouldn't have — that's the bug to
find, not a flaky test to retry past.

Release-readiness detail (severity/blocking/remediation parsing, actor classification, the
awaiting-review case): `references/commands.md`.

### `manual` — guided execution

Runs the same cycle as `auto` below but **stops at every decision point**. Each stop presents
numbered options with the consequence of each, and **always** includes a defer option (FR-019).
Deferring continues the cycle rather than ending it — "not now" is a first-class answer, not a
failure.

### `auto` — unattended cycle

Eight steps, in order, each completing or recording a named blocker before the next starts (this
*is* the completion condition, FR-024 — the cycle does not loop, wait, or reach into the next
cycle's work):

1. Determine phase live; correct `STATE.md` if it disagreed, and surface the disagreement (FR-032)
2. Record any weekly figures obtainable now; mark the rest `absent:<reason>`, never a zero
3. Refresh rank observations if the tracker is reachable (`references/commands.md` degradation path
   if not)
4. Judge every hypothesis whose window has closed (`references/aso-loop.md`); write verdict +
   reasoning
5. Draft the next hypothesis (or batch of market-isolated hypotheses, exactly 1 per market for eligible markets with identified opportunities). **Active-experiment collision guard**: audit existing hypotheses in `STATE.md`; if a market already has an active hypothesis whose 21-day window is in flight (`status: live` or `status: staged`), refuse new metadata mutations for that market and save them as future proposals in the Ideas Backlog (`marketing/ROADMAP.md` / `status: idea`). Only draft/stage for markets with no active experiment running; refuse any hypothesis if any of the four required parts is missing
6. Prepare everything preparable up to the fence, exploiting the `plan`/`approve` vs `apply`/`push`
   asymmetry so only the crossing itself waits (FR-022): pull live metadata with `asc metadata
   pull`, draft the change across all four tracked locales, validate character limits offline
   (`asc metadata validate`), compute and read back the exact diff (`asc metadata plan`, then
   `approve` — both local), and queue only the resulting `apply`
7. Write `queue.md` entries for whatever the fence stopped; **do not abort the cycle** on a fenced
   command — queue it and keep going (FR-021)
8. Rewrite `STATE.md`; print a done / queued / next summary

**The fence itself — literal commands, deny-by-default — lives in `references/commands.md`. Read it
before every write in `auto` or `manual` mode**, not from memory: a command not on its allow list is
fenced whatever it appears to do.

**Interruption safety**: each step's write completes before the next step starts, so a run
interrupted mid-cycle leaves earlier steps durable and later ones simply absent — never a state a
later `status` run misreads as complete (SC-013).

**Before executing an approved queue entry**, re-verify its preconditions — an approval given weeks
ago was given against a world that has since moved (FR-023).

## Reference map — read on demand, not all at once

| Need | Read |
|---|---|
| Provenance / citing a claim | `references/provenance.md` — read this one first, always |
| Store file formats, schemas, append rules | `references/state-store.md` (runtime authority) |
| Exact `asc` invocations, the approval fence, release-readiness parsing | `references/commands.md` |
| The ASO iteration loop, verdicts, keyword selection | `references/aso-loop.md` |
| Apple Ads: credentials, campaign structure, economics | `references/apple-ads.md` |
| Product page experiments, CPPs, reviews, content backlog | `references/playbooks.md` |
| Handbook reasoning (cited, never restated — FR-035) | `marketing/HANDBOOK.md` |

Three bundled scripts, all re-run every iteration rather than one-off. Each has `--self-check`.

- `$SKILL_DIR/scripts/harvest_keywords.py` — Apple autocomplete hints + competitor discovery
- `$SKILL_DIR/scripts/economics.py` — LTV / break-even / scaling verdict
- `$SKILL_DIR/scripts/rank_audit.py` — full keyword rank audit with opportunity scoring

### rank_audit.py — when and how to run

**Trigger:** Step 3 of `auto` mode ("refresh rank observations") — run this instead of or in addition
to `check_ranks.py` whenever a full audit is warranted (new version live, post-hypothesis verdict,
quarterly review, or user explicitly asks for a rank/opportunity report).

**Keyword generation — the right approach (not manual lists):**

Keyword lists are **generated from Apple's own autocomplete**, not typed from memory:

```bash
# Step 1: get autocomplete hints for seed terms → these are what users actually type
python3 $SKILL_DIR/scripts/harvest_keywords.py hints \
  --storefront us --term "white noise"

# Step 2: run rank_audit with auto-expand mode (harvests hints for each seed, deduplicates)
python3 $SKILL_DIR/scripts/rank_audit.py \
  --bundle "$APP_BUNDLE_ID" \
  --markets us,de,gb \
  --expand-from-hints \    # uses harvest_keywords.py to auto-expand seed terms
  --output $STORE/reports/aso_rank_audit_$(date +%Y-%m-%d).md
```

**Market-proportional query budgets** — bigger markets get more queries:

| Market weight | Queries |
|---|---|
| ≥ 50 (US, JP) | 80–100 |
| 20–49 (DE, GB, FR, KR, IT, ES, CA, AU) | 40–60 |
| 10–19 (BR, RU, NL, MX, IN, TR, PL, SE) | 25–40 |
| < 10 (UA, SA, IL, TW, CN) | 15–20 |

**Output interpretation:**
- `opportunity score` = market_weight × volume_proxy × rank_reachability × (1 − difficulty)
- Higher = more downloads available if rank improves here
- Sort by opportunity to set keyword hypothesis priority
- "colour noise" terms (brown/pink) consistently show low competition across all markets — systematic gap

**Saving results:** append a summary row to `$STORE/metrics/ranks.csv` and save full report to
`$STORE/reports/aso_rank_audit_YYYY-MM-DD.md`. The `check_ranks.py` script handles the CSV append;
`rank_audit.py --output` handles the full report.

First run against an uninitialized store: seed it with
`cp -n -r $SKILL_DIR/assets/store-template/. $STORE` (never overwrites an existing file — safe to
re-run) — but only inside `manual`/`auto`, never `status` (see Step 4 above). Seeding alone doesn't
finish the job: `config.md` comes in with `TODO` placeholders, and Step 1 refuses to proceed past
them — filling in this app's real App Store Connect app id and version is the next thing to do
after seeding, not an optional follow-up.
