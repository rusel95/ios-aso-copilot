# Provenance — the narrow waist

Every factual claim this skill emits — a figure, a status, a position, a date, a ranking — carries a
provenance tag naming its source and when it was observed. This is not a style preference: it is the
single mechanism that implements every honesty rule in this skill (live-beats-stored, never
fabricate, label estimates, say what's missing). Four separate habits lapse invisibly; one mechanical
check — "does this claim have a tag" — does not.

**Unciteable is unsayable.** If you cannot name a source kind for a claim, do not emit the claim.
State the gap instead, using `absent:<reason>`. "We don't have this" is itself a citable statement,
not a silence to be filled with a plausible-looking number.

## Closed vocabulary

Do not invent a new kind at the point of use. If nothing below fits, the claim is `absent:`.

| Kind | Form | Example | Freshness bound |
|---|---|---|---|
| `live` | `live:<command>@<date>` | `live:asc validate@2026-08-19` | Phase / release-readiness: **same session**. Older is `stale`. |
| `store` | `store:<file>#<row-key>` | `store:metrics/weekly.csv#2026-09-07/search` | none — the row's own `recorded`/`date` column carries its age |
| `doc` | `doc:<file>§<section>` | `doc:HANDBOOK.md§1.3` | none |
| `web` | `web:<host><path>@<date>` | `web:developer.apple.com/help/…@2026-08-19` | **90 days** — App Store rules change |
| `user` | `user:@<date>` | a figure the developer read off a web UI and typed in | none, but never upgrade it to `live` |
| `derived` | `derived:(<input>,<input>,…)` | `derived:(price,commission,retention,trial-cvr)` | inherits the **worst** of its listed inputs |
| `absent` | `absent:<reason>` | `absent:no analytics report generated yet` | none |

Three rules that are easy to violate without noticing:

1. **`derived:` must list every input**, by name or by tag. A bare `derived:` defeats its own
   purpose — the point is that a wrong output is traceable to the wrong input without re-deriving it.
2. **Provenance survives copying.** A figure carried from a live check into `STATE.md` and then into
   a summary still cites the original `live:` or `store:` observation — never `store:STATE.md`.
   `STATE.md` is a cache; citing it makes a stale number look freshly observed. This is the most
   likely place this rule gets violated by accident, because citing the cache *looks* correct.
3. **`user` never gets promoted to `live`.** A human-read figure is trustworthy but was observed once
   by a person, not by a re-runnable command. Collapsing the two loses the ability to re-check.

## Staleness

A claim older than its kind's freshness bound is marked **stale, with its age**, and must not be used
to raise confidence in a verdict. It may still lower confidence — a stale rank is a reason to
withhold a verdict, never a reason to issue a confident one.

```text
Phase: P1-review  [live:asc validate@2026-08-19]
Rank, "compress videos" (US): #58  [store:metrics/ranks.csv#2026-09-08/us — 11 days old, stale]
Trial rate: not measured  [absent:no paid conversions recorded yet]
```

## Where a tag is required, and where it is not

**Required** on anything a decision could rest on: the phase and how it was determined; every funnel
figure; every rank/popularity/difficulty score; every verdict's supporting evidence; every economic
output; every claim about what Apple does or allows; every blocker reported.

**Not required** on your own reasoning, arguments, or recommendations. "Start with Brand and
Discovery" is an argument, not an observation — tag every figure that argument cites, not the
argument itself. Over-tagging is a real failure mode: once tags appear on things that can't be wrong,
readers stop reading them.

**The test**: could this claim be wrong in a way a reader could check against a source? If yes, tag
it. If it's a judgment call, don't.

## What this rule alone enforces

- **Live beats stored** (FR-032) — a `live:` tag always outranks a `store:` tag for the same claim;
  surface the disagreement by showing both tags rather than silently picking one.
- **Never fabricate** (FR-033) — there is no tag for an invented number. Producing one requires
  writing a tag that is false, not merely omitting caution.
- **Label estimates** (FR-034) — an estimate is `derived:` from named assumptions; the tag *is* the
  label.
- **No per-keyword organic attribution** (FR-025) — such a claim has no available source kind, full
  stop. It fails here, at the one interface every claim passes through, rather than needing a
  separate rule wherever someone might ask for it. If asked directly (e.g. "how many downloads came
  from the keyword X"), say plainly that no source produces that number — Apple's own Discovery and
  Engagement report has no search-term dimension, and the only first-party search-query data is the
  Apple Ads search-terms report, which covers paid queries only (research.md §3).

A rule enforced at this one waist cannot be forgotten at some other site. Every other reference file
in this skill assumes you apply this one without being told again per-figure.

## ASO joins and transport

MCP is a transport, not the origin of a score. Preserve exact query, country, observation date,
provider, method, selected popularity source and fallback detail. Translation is not a join key.
A successful MCP envelope may contain an error: inspect its content before treating it as data.
A generated report date never replaces the dates of its underlying observations.

RSS written-review samples and cumulative ratings are different observations. Their absence cannot
be converted into download velocity, query searches or competitor ad spend. Identity must match
App ID/bundle, never a fuzzy app-name substring.
