# Commands — the `asc` / free-endpoint cookbook, and the approval fence

App: `$APP_ID` — read from `$STORE/config.md`, per repo (SKILL.md Step 1); never hardcoded here.
Two independent `asc` credential stores exist — `asc auth` for App Store Connect
(configured) and `asc ads auth` for Apple Ads (a separate account, see `references/apple-ads.md`).
Never report "asc is not set up" — that conflates the two and is simply wrong when only one is
missing.

## The approval fence

**Implements FR-020…FR-023.** FR-020 states the fence as categories — spends money, publishes,
posts under Ruslan's name, changes account settings. That is not enough to bind you: nothing about
the word "publishes" tells you that `asc reviews respond` does it. So the fence is the literal list
below, and this list is the authority, not the category description.

Apply the user's existing authorization across turns. Unlisted read-only or reversible local commands can proceed after checking their help; do not invent a permission gate. For external mutations outside the authorized scope, prepare the concrete artifact before asking.

**Version note.** This list was transcribed against `asc` 3.1.1 (`specs/013-marketing-ops-skill/contracts/approval-fence.md`, 2026-08-19) and spot-checked against the installed `asc --version` before this file was written — still 3.1.1. If a future run sees a different version, diff this list against that version's `--help` output before trusting it: a major bump can rename or restructure a write subcommand, and a renamed command missing from this list is invisible to the deny rule, not denied by it.

In `auto` mode, hitting a fenced command does **not** abort the cycle (FR-021): write it to
`marketing/queue.md` with its exact command, its plain-language effect, and its preconditions, and
continue.

### External actions require authorization within the user's requested scope

| Command | Why it is fenced |
|---|---|
| `asc metadata apply` | writes the live App Store listing |
| `asc metadata push` | same |
| `asc localizations update` | writes listing text directly |
| `asc versions update` | changes the version record |
| `asc reviews respond` | **publishes text publicly under Ruslan's name** |
| `asc reviews respond-batch` | same, in bulk |
| `asc reviews response delete` | removes published content |
| `asc ads campaigns create` / `update` | **spends money** |
| `asc ads ad-groups create` / `update` | spends money |
| `asc ads budget-orders create` / `update` | spends money |
| `asc ads targeting-keywords create-bulk` / `update-bulk` / `delete` / `delete-bulk` | changes what is bid on |
| `asc ads campaign-negative-keywords` / `ad-group-negative-keywords` (writes) | changes what is bid on |
| `asc ads ads create` / `update`, `asc ads creatives` (writes) | publishes ad creative |
| `asc product-pages experiments create` / `start` / `update` | changes what a share of visitors sees |
| `asc product-pages custom-pages create` / `update` | creates public pages |
| `asc app-tags update` | changes public store-page tags |
| `asc analytics request` | creates a persistent App Store Connect account resource |
| `asc screenshots` (writes), `asc video-previews` (writes) | changes public media |
| `asc subscriptions` (writes), `asc pricing` (writes) | **money and public commercial terms** |
| `asc release` (any), `asc testflight` distribution | ships |
| anything creating, submitting or cancelling a review submission | ships |

Also fenced, beyond `asc`: publishing to any social platform, posting to Reddit or Product Hunt,
sending email, buying a subscription (Astro, aso.dev, an Apple Ads budget), entering payment
details. Several of these — payment details, account credentials — the skill must never do at all,
approval or not; it drafts and Ruslan executes.

### Allowed unattended — reads and local-only work

| Command | Note |
|---|---|
| `asc validate` (all forms) | candidate validation; read live/candidate version states first |
| `asc metadata pull` | writes only to a local directory |
| `asc metadata plan` | **local** — computes the diff, writes a review artifact |
| `asc metadata approve` | **local** — marks a local plan approved; does not touch Apple |
| `asc metadata status` / `validate` | local |
| `asc versions list`, `asc apps`, `asc localizations list` | reads |
| `asc analytics requests` / `view` / `reports` / `instances` / `download` | reads (creating a request is fenced) |
| `asc insights weekly` / `daily` | reads |
| `asc reviews list` / `view` / `ratings` / `summarizations` | reads |
| `asc ads reports *`, `asc ads campaigns list` / `view` | reads |
| `asc subscriptions list` / `view`, `asc pricing list` | reads |
| Astro MCP: `list_apps`, `get_app_keywords`, `search_rankings`, `get_app_ratings`, `extract_competitors_keywords`, `get_keyword_suggestions`, `search_app_store` | reads |
| Astro MCP: `add_app`, `add_keywords`, `set_keyword_note`, `set_keyword_tag`, `manage_tag` | writes, but to a **local personal tool** — reversible, free, affects nobody else |
| `$SKILL_DIR/scripts/harvest_keywords.py`, `$SKILL_DIR/scripts/economics.py` | local |
| iTunes Search API, `MZSearchHints` | public reads, no key |
| all writes inside `marketing/` | the state store is the skill's own |

### The asymmetry, and why it matters

`asc metadata plan` and `asc metadata approve` sound like they cross the line and don't — both are
local. `plan` diffs local canonical files against what Apple currently holds and writes a review
artifact; `approve` marks that local artifact approved. **Only `apply` and `push` transmit
anything.** This is what makes `auto` mode worth having (FR-022): a full unattended cycle can pull
live metadata, draft a complete keyword change across all four tracked locales, validate character
limits offline, compute and read back the exact diff, and queue **one line** — `apply` — for
approval. The overnight run does the hours of work; the morning decision is yes/no on a diff already
computed. A fence that stopped one step earlier would leave nothing but an unverified suggestion.

### Queue entries

Format and the precondition re-check rule: `references/state-store.md` → *Queued action*.

---

## Release readiness (US2) — reading `asc validate`

```bash
asc validate --app $APP_ID --version $VERSION --platform IOS --output table
```

Interpret this against the actual version state from `asc versions list`. A live version failing an editability check is not a prelaunch blocker. This is a CLI validation source for candidate readiness — never a hand-maintained checklist, and
never `STATE.md` when it disagrees (FR-032, live beats stored). Each finding carries three fields
that matter:

- **severity** (`error` / `warning` / `info`)
- **blocking** (boolean) — present it first if true; **never render an advisory finding as a
  blocker**, and never render a blocker as advisory
- **remediation** — a string Apple/`asc` provides. Carry it through verbatim; do not paraphrase or
  invent your own advice for a finding that already ships one

**Actor classification** — every finding is either the skill's to resolve or Ruslan's:

- The skill's: anything fixable through `asc metadata`/`asc versions`/similar local-then-`plan`
  workflow, once past the fence.
- Ruslan's: anything requiring a web-UI action the API cannot perform — accepting terms, confirming
  a publish state, App Privacy questionnaire changes, anything App Store Connect only exposes as a
  click. For his items, say **what he will see on the screen**, not just what to do, so he can
  confirm he's looking at the right control.

**The awaiting-review case.** `WAITING_FOR_REVIEW` / `IN_REVIEW` is a **state to wait out**, not a
defect. Apple locks the version for editing while it's under review, which `asc validate` reports as
`version.state.editable` — an error by severity, zero blocking by the flag. Identify any finding that
exists *only because the version is locked* and say so explicitly rather than listing it as
outstanding work; conflating "the version is locked for review" with "there is unfinished work"
recreates exactly the stale-notes failure this feature exists to prevent (research.md §2).

Current known state (**live-tag this, don't treat it as a fact of this file** — re-check every run):
version 1.0 was `ACCEPTED` (non-editable) as of `live:asc validate@2026-08-22`, 1 error / 2 warnings
/ 1 info, 1 blocking (the non-editable-state finding — unlike the `WAITING_FOR_REVIEW` case above,
`asc validate` flagged this one as blocking). The two warnings were missing subscription promotional
images; the info was that App Privacy publish state isn't verifiable through the public API
(Ruslan's, web UI only). This moved from `WAITING_FOR_REVIEW` sometime between 2026-08-19 and
2026-08-22 — `STATE.md` still says the older state as of this writing; a `manual`/`auto` run will
correct it (FR-032).

---

## Free endpoints — no key, no account

Both verified working during implementation, 2026-08-19 (this session, not carried over from
research.md unverified). Use them for keyword **discovery**; neither produces a real App Store
*rank* — see `references/aso-loop.md` for why rank still needs a tracker.

### iTunes Search API — competitor discovery

Official, documented, stable for years.

```bash
curl -s "https://itunes.apple.com/search?term=compress%20photos&country=us&entity=software&limit=25"
```

JSON. Use `trackName` and `artistName` per result. For **COMPETITOR** candidates: run each seed
keyword through this per target country, and rank the apps that come back by how many *different*
seed terms surfaced them — an app appearing for many seeds is a real competitor, one appearing for
one is noise. This index is **not** the real App Store search index (research.md §4) — do not use
its ordering as a position claim.

### `MZSearchHints` — autocomplete, ordered by real search popularity

Undocumented but stable and free. **Requires the storefront header** — without it, every query
silently returns zero hints, which looks like "no suggestions" rather than "wrong request":

```bash
curl -s \
  -H "X-Apple-Store-Front: 143441-1,29" \
  -A "iTunes/12.0 (Macintosh)" \
  "https://search.itunes.apple.com/WebObjects/MZSearchHints.woa/wa/hints?clientApplication=Software&term=compress"
```

Returns a plist XML `<array>` of `<dict>` entries, each with a `term` string, in popularity order.
Storefront IDs for the four tracked markets:

| Market | Storefront header value |
|---|---|
| US | `143441-1,29` |
| GB | `143444-1,29` |
| DE | `143443-1,29` |
| UA | `143492-1,29` |

Use this for **TARGET** candidates (head terms not yet ranked for) — harvest hints from short
prefixes of the app's own vocabulary and from competitor names, not invented words. This is also the
first thing to check whenever a new hypothesis needs a supporting popularity signal and the tracker
is unavailable (`references/aso-loop.md` degradation path).

**What neither endpoint gives you**: Apple's own popularity/difficulty scores, or any rank history
predating when tracking started. That's what a paid tracker is for, contingently — see
`references/aso-loop.md`.

---

## Astro (rank tracker) — contingent, local MCP

Not purchased as of this writing (`references/apple-ads.md` and `references/aso-loop.md` both
handle its absence as a normal condition, not an error). When present: a Mac app exposing an MCP
server on `127.0.0.1:8089`. Read tools (`search_rankings`, `get_app_keywords`, etc.) and the local
list-management writes (`add_keywords`, `set_keyword_tag`, etc.) are both unattended-safe — see the
allow list above; nothing it does leaves your machine or costs money beyond the subscription itself
(which is fenced as a purchase decision, separately, once).

## Apple Ads reads

`asc ads reports search-terms` and `asc ads reports keywords` — both read-only, both blocked today
only by missing credentials (`references/apple-ads.md`), not by anything else.

## RespectASO

Read `references/respectaso.md` for the installed MCP tool groups. Access/status and non-saving queries are reads; settings changes, saved data, background AI usage and session cancellation have distinct effects. Parse embedded errors even when MCP `isError` is false.
