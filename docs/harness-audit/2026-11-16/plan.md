# Improvement plan: ios-aso-copilot

## Verdict

This harness is a single skill that keeps an iOS app's marketing work going: scripts collect what App Store Connect, Apple Ads, RevenueCat and Google report, export a deterministic page and let a model judge hypotheses. The code half is strong: one owner per figure, a versioned data contract, a golden-file test, an AST test that confines every outside-world write to one module, and a habit of turning each found bug into a test. The weak half is everything the model must obey on its own. Spending money, replying to a review under the developer's name and publishing a page are guarded by prose and a queue file that no code reads, no CI runs the 314 tests, and the skill leaves no record of its own runs. Several reference files have also drifted from the code (a removed installer, a missing specs folder, two rules that contradict each other).

Target kit: Pipeline (collect, export, build) plus Researcher for the judging stage. Answers to the six questions: does not fit one session, yes; steps known in advance, yes; code can check results, mostly (the verdict itself is model-written); irreversible or private, yes (money, public replies, a public page); many similar items, yes (storefronts, keys, weeks); lives longer than a month, yes.

Evidence base: static scan and walkthrough of the pull-request branch; one 22 MB transcript. That transcript is the session that built the branch, not a session that used the skill, so "never invoked" and "never read" facts from it are not used. No `marketing/` store was available, so state-versus-disk checks stay open.

## Fix first

### 1. Make the three outside-world actions refuse to run without an approved queue entry
- Problem: the approval fence is a list for the model to remember (`references/commands.md:11-18`). The code runs the action when called: `reviews respond` posts publicly with no confirmation (`scripts/aso/commands/ads_actions.py:101`), keyword creation passes `--confirm` itself (`ads_actions.py:53`), campaign resume the same (`ads_actions.py:83`), and `publish` pushes as soon as the data checks pass (`ads_actions.py:198-204`). The fence was transcribed against `asc` 3.1.1 and "has not been revalidated" for 5.1.0 (`references/commands.md:18`), so a renamed write is outside it. The queue entry format (exact command, effect, preconditions, `references/state-store.md:273-285`) is good, but nothing reads it. Approvals are also not recorded: entries are deleted once executed (`state-store.md:25`).
- Bricks: D9 policy outside the agent, D5 hooks, G1 approval point, G2 review artifact, G6 decisions recorded (checks A-G1, A-T1, A-G6).
- Smallest first step: make `cmd_reviews_respond` require `--queue-id Qnnn`, look the id up in `marketing/queue.md`, refuse when it is absent or its `Command` line differs from what is about to run, and append one line to `decisions.md` ("Q003 approved, executed 2026-11-16") instead of deleting the entry. Do `reviews respond` first because it is public and cannot be taken back; ads changes and `publish` follow the same pattern. Keep the existing `--dry-run`.
- How to see it worked: a new test in `tests/test_boundaries.py` calls `cmd_reviews_respond` with a fake `asc` earlier on PATH and no queue id; today the fake is called, after the change it is not and the exit code is non-zero. A second case with a matching queue entry calls it exactly once and leaves a line in `decisions.md`.
- Why this rank: harm leaves the repository (money, public text under the developer's name). Practice grade: the idea of a gate is graded A only for prevalence of "never asks a human" (77 percent of skills); hooks and code-level policy are grade C, so the evidence is practitioner experience, not a measured effect.
- Files: `scripts/aso/commands/ads_actions.py`, `scripts/copilot.py`, `tests/test_boundaries.py`, `references/actions.md`, `references/state-store.md`

### 2. Run the 314 tests on every push
- Problem: there is no `.github` folder. The tests are run by hand (`README.md:163`), the shipped workflow only builds a page (`assets/workflows/aso-dashboard.yml`), and the last session ended with changes (history, `propose`, `publish`, the ads filter) that "a fresh reviewer had not read" and with a usage-limit stop (transcript line 4899). Counting `def test_` gives 314, which matches the claim, but nobody but the author has seen it green.
- Bricks: E12 CI gate, V2 backpressure (checks A-E5, A-V1).
- Smallest first step: add `.github/workflows/tests.yml` that checks out the branch and runs `python3 -m unittest discover -s tests -t .` on Python 3.10 and 3.12.
- How to see it worked: a throwaway commit that breaks `tests/test_skill_md.py` turns the check red on pull request 2; reverting turns it green.
- Why this rank: cheapest control in the plan and the base for fixes 1, 3 and 5. Grade C.
- Files: `.github/workflows/tests.yml`

### 3. Remove the documentation drift and the one real contradiction
- Problem: `references/judge.md:121` tells the agent to reject any query with Apple popularity under 15 and to aim for popularity 20-60, while `references/apple-ads.md:186` says an unlisted term is "below the cut, never zero" and the owner's FINDINGS (2026-10-03, `FINDINGS.md:252-257`) say the mid and long tail is exactly what Apple's index omits. `judge.md:123-125` also hard-codes one app's query tiers ("white noise", "brown noise") in a reference the README calls per-app. `references/commands.md:18` and `state-store.md:3` lean on `specs/013-marketing-ops-skill/`, which is not in the repository. `README.md:68-72` and `:144` describe `npx ios-aso-copilot install` and `bin/cli.js`, removed in v2.7.0 (`bin/` holds one Python entry). `FINDINGS.md:171` points to "SKILL.md step 2b", which no longer exists (the text sits in `references/actions.md:28` under orphan numbers 2b, 7-10), and the batch-size cap it describes became "an operator heuristic" in `apple-ads.md:126`.
- Bricks: K6, X3, X4 (checks A-K3, A-K4, A-X4).
- Smallest first step: first extend `tests/test_skill_md.py` to scan every file in `references/` for backticked repository paths and fail on any that do not exist (it fails today on `specs/013-...`). Then delete the dangling sentences, delete the `<15` rule and the fixed popularity bands from `judge.md` (move the white-noise tiers to that app's `HANDBOOK.md`), correct the README install and structure sections, renumber `actions.md`, and fix the `FINDINGS.md` pointer.
- How to see it worked: the new test passes; `grep -n "specs/013" -r references` and `grep -n "cli.js" README.md` return nothing; a second reader finds one popularity rule, not two.
- Why this rank: these are what a fresh agent reads literally; a wrong rule here is followed. Grade A for prevalence of contradictions and blind references, effect on quality unmeasured.
- Files: `tests/test_skill_md.py`, `references/judge.md`, `references/commands.md`, `references/state-store.md`, `references/actions.md`, `README.md`, `FINDINGS.md`

### 4. Leave a run record and stop concurrent writers
- Problem: the owner's text says outright that `cycle` has no run id, no rollback and no crash-safe resume, and that writers must not overlap (`references/actions.md:53-55`); the roadmap lists "a persistent run manifest" as open (`ROADMAP.md:129`, item R-12). The consequence showed up at the end of the build session: a pull request for one app carried 1,059 deleted lines where only additions were expected and "I did not find the cause" (transcript line 4899). Cost and duration of a pass are unknown for the same reason.
- Bricks: L1, L6, L8, E10, G8 (checks A-L3, A-E6).
- Smallest first step: at the end of `collect`, write `marketing/runs/<utc timestamp>.json` with, per stage, status, rows appended per file, files touched and duration; create `marketing/.lock` at the start and refuse a second `collect` while it exists.
- How to see it worked: a test in `tests/test_collect_parallel.py` runs two stages against the sample store, finds a manifest with both stages and their row counts, and shows a second invocation exiting non-zero while the lock exists. A fresh session can then say which stage failed without reading chat.
- Why this rank: it is the base for resuming, for explaining a surprising diff and for any later cost figure. Grade C. Already on the owner's list, so this adds an observed consequence, not a new idea.
- Files: `scripts/aso/commands/cycle.py`, `scripts/aso/commands/collect.py`, `references/state-store.md`, `tests/test_collect_parallel.py`

### 5. Add the first agent-level evals
- Problem: the 26 test files test scripts, not what the model does with the skill; the only test on `SKILL.md` checks its shape (`tests/test_skill_md.py:1`). There is no with-and-without-skill run, no trigger test, and the frontmatter lists 88 trigger words (`SKILL.md:4-92`), many of them generic ("charts", "ASO", "реклама", "дохід"). The judging stage, where the model writes verdicts, has no evaluator; the owner plans to route verdicts through pull requests (`ROADMAP.md:29-31`).
- Bricks: S7, E6, E1, S2 (checks A-E1, A-S3, A-S5).
- Smallest first step: create `evals/evals.json` with three cases: a must-fire prompt ("where are we and what is next for my app"), a must-fire judging prompt against the sample store with one due hypothesis, and a near-miss that must not fire ("write meta tags for my website"). Hand them to `epam-skill-creator` for a paired with/without run.
- How to see it worked: the file exists with at least one must-not-fire case; the benchmark output shows the skill's pass rate against the no-skill baseline for each case.
- Why this rank: it is the evidence the other cuts (triggers, references, subagent model) wait for. Grade B for evals, C for the rest; small first sample only.
- Files: `evals/evals.json`

## Remove or trim

- `scripts/measure_velocity.py` (318 lines): named nowhere in `SKILL.md`, references, README, tests or `copilot.py`, and `scripts/global_velocity_audit.py` does the same job and is the one README advertises. Delete it; confirm with `grep -r measure_velocity` and the unit tests (check A-D6).
- `.claude/launch.json`: tracked, points at a temporary folder of the build session (`/private/tmp/...`), and serves nothing in a clone. Delete it and add `.claude/` to `.gitignore`. Nothing depends on it.
- Fixed popularity bands and the white-noise tiers in `references/judge.md:119-125`: covered by fix 3.

## Measure before deciding

- The 88-entry `triggers` list (`SKILL.md:4-92`; brick S2 overbuilt). Run 10 prompts (5 on topic, 5 near-miss such as general SEO, charts in a dashboard, translation) with and without the list; cut entries that fire on the near-misses. Cost: a few dozen short sessions.
- Reference volume (20 files, 3,215 lines; `apple-ads.md` alone is 574). The only log is a build session, so "never read" is not usable. Collect two or three real use sessions with `scan_trace.py`, then decide what to merge.
- Collect pass on a cheaper model (`SKILL.md:162`). Compare the STAGE SUMMARY of the same pass on both models in a copy of a store. The skill gives no brief for the subagent (brick O8).
- Determinism claim (check A-D5): run `export` twice on a copy of one store with the same `--as-of` and compare bytes. Free and offline.
- Cross-app leakage beyond Apple Ads. The build session found another app's campaigns in a store (both apps share one ads account) and fixed it with a test (`tests/test_history.py:191`). Whether GA4, BigQuery or RevenueCat reads can do the same is not tested: probe with two sample stores on one account in a sandbox.
- Whether a verdict written by the model needs a separate evaluator (V1). Decide after the pull-request approval flow from `ROADMAP.md:29-31` has produced five verdicts and the owner's edits can be counted.

## Keep

- The thin router `SKILL.md` and its test (size, sections, every named command exists): `tests/test_skill_md.py:28`. Declared and tested, not run by me.
- One owner per figure, deterministic export and page, versioned contract validated at export and build (`scripts/aso/dashboard/export.py:268`, `site.py:66`), golden files in `tests/golden`.
- Write containment: only `ads_actions.py` may change the outside, and `collect` may not import it (`tests/test_boundaries.py:43-65`). This is the best control in the repository; fix 1 builds on it.
- The queue entry format with exact command and preconditions re-verified before execution (`references/state-store.md:273-285`).
- "Unknown is not zero" discipline: `unavailable` with a code and a reason, `no-results` status, `below the cut` (`SKILL.md` rule 3, `scripts/aso/ledger_selfcheck.py:41`).
- Publish refuses stale data and runs the clean check first; the clean check has planted-defect tests (`tests/test_clean.py:57-65`). The test file contains deliberate fake secrets; no real credential was found.
- The FINDINGS to fix to test loop. The owner's claim "no Python file over 600 lines" holds (largest 591, enforced at `tests/test_boundaries.py:111`).
- The final message of the build session: it separates done from unverified, which is the behaviour a done-claim needs.

## Next in queue

- Validate the model-written records (hypothesis files, queue entries) with a small linter; today only the template and the ledger's "incomplete legacy record" warning guard them.
- Write store files atomically (temp file and rename) once the lock from fix 4 exists.
- Revalidate the fence list against the current `asc --help` (it names 3.1.1 and 5.1.0).
- Define `$COPILOT` once in `SKILL.md`; it is set only in `references/collect.md:60` but used in `judge.md`, `export-and-page.md` and `publish.md`, and three call styles are mixed (`ios-aso-copilot x`, `python3 $SKILL_DIR/...`, `$COPILOT`).
- The decision log of about 80 entries sits in an untracked `.superpowers/` folder (transcript line 4899); commit it under `docs/` or discard it.
- ROADMAP items 1-3 (a weekly job collects, the skill only judges) would remove network reads from the model's work; do them after fix 1, since the job's credentials become repository secrets.
- Explain the 1,059 deleted lines in the second app's pull request before merging it.

## Limits of this audit

- Model-judged rulings are wrong about one time in ten; every ruling cites a line, but A-K3 and A-X4 are my reading of two documents and should be confirmed by the owner.
- Nothing was run: not the 314 tests, not the scripts. "Tests green", "same bytes" and "fixtures catch planted values" are declared, not verified.
- The single transcript is the build session (1.13M output tokens, peak context 964,602 tokens, one compaction, ended on a usage limit). It shows how the branch was made, not how the skill behaves in use. Checks needing real runs (A-D5, A-L4, A-L6, A-V3, A-V6, A-E3, A-E4, A-G5, A-S3, A-S4, A-X3) stay Not Reviewed.
- Secret scan: the three hits are planted fixtures in a test (file and line only recorded); regex scans miss unshaped credentials, and no real credential was seen.
- No published evidence shows that a harness audit improves agent results. Measure two or three tasks (a status question, a judged hypothesis, a dry-run publish) before and after fixes 1, 3 and 4.
- Practice grades: most advice here is grade C (practitioner experience) or B (lab report); only the contradiction and blind-reference checks are grade A, and those measure prevalence, not effect.
