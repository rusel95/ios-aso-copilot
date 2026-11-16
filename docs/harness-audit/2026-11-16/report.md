# Harness audit: ios-aso-copilot

Rubric v1.0 · 2026-11-16 · evidence: static + 17 log file(s) · target kit: Pipeline (collect, export, build) plus Researcher for the judging stage

There is no overall score. A score that grows with the number of artifacts rewards clutter; read the findings.

| Fail | Pass | Not reviewed | Not applicable |
| --- | --- | --- | --- |
| 12 | 34 | 11 | 4 |

## Findings (12)

### 1. A-G1 · Is there a human gate before every irreversible action (delete, send, deploy)?

Shelf G (boundaries) · add or repair · practice grade A (research) · settled by static

- **Finding:** Gates are rules for the model, not checks in code. Replying to a review (public, under the developer's name) runs with no confirmation; keyword creation passes --confirm unconditionally; the fence list was transcribed against asc 3.1.1 and not revalidated for 5.1.0, so a renamed write is outside it. The queue entry format is good (exact command, preconditions), but no code reads it.
- **Evidence:** `scripts/aso/commands/ads_actions.py:101` — result = subprocess.run(["asc", "reviews", "respond"
- **Evidence:** `references/commands.md:18` — has not been revalidated against 5.1.0
- **Evidence:** `SKILL.md:144` — goes through the queue
- **Bricks:** G1, G3
- **First step:** Plan fix 1.

### 2. A-D6 · Does every artifact have a consumer?

Shelf D (contracts) · **recommend removing** · practice grade C (practitioners) · settled by static

- **Finding:** scripts/measure_velocity.py (318 lines) is named nowhere in SKILL.md, references, README, tests or copilot.py, and global_velocity_audit.py (411 lines) does the same job and is the one README advertises.
- **Evidence:** `scripts/measure_velocity.py:3` — measure_velocity.py — Audit competitor review velocity
- **Evidence:** `README.md:35` — scripts/global_velocity_audit.py
- **Bricks:** D3, X3
- **First step:** Delete scripts/measure_velocity.py; confirm with `grep -r measure_velocity` and the unit tests.

### 3. A-L3 · Is state written by code (atomically, with a schema) rather than by the model editing JSON?

Shelf L (state and recovery) · add or repair · practice grade C (practitioners) · settled by static

- **Finding:** Metrics are appended by code, but nothing writes atomically or takes a lock, and the owner's own text says there is no run id, rollback or crash-safe resume and that writers must not overlap. The roadmap lists a persistent run manifest as open (R-12).
- **Evidence:** `references/actions.md:54` — do not assume `cycle` has a run ID
- **Evidence:** `ROADMAP.md:129` — persistent run manifest
- **Bricks:** L1, D1
- **First step:** See plan fix 4: write one run manifest per collect and take a lock file for the store.

### 4. A-E1 · Are there at least three evals, with both must-fire and must-not-fire cases?

Shelf E (evals and traces) · add or repair · practice grade B (lab report) · settled by static

- **Finding:** No eval files for the skill's behaviour: no trigger cases, no must-fire and must-not-fire prompts. The 26 test files test scripts, not the skill.
- **Evidence:** `tests/test_skill_md.py:1` — SKILL.md is a router
- **Bricks:** E6, S7
- **First step:** Create evals/evals.json with three cases (see plan fix 5).

### 5. A-E5 · Do tests and evals run in CI, and does a red result really stop a merge?

Shelf E (evals and traces) · add or repair · practice grade C (practitioners) · settled by static

- **Finding:** No CI in the repository (no .github). The tests run when someone types the command; the shipped workflow template only builds a page. The 314-test claim rests on one session, and the last changes (history, propose, publish, ads filter) were written after the final review.
- **Evidence:** `README.md:163` — python3 -m unittest discover -s tests -t .
- **Evidence:** `<session-logs>/175a41d3-33cf-45a6-9cf7-75f699d80738.jsonl:4899` — свіжий рев
- **Bricks:** E12
- **First step:** Add .github/workflows/tests.yml (plan fix 2).

### 6. A-E6 · Does the harness record any usage data (traces, a log with run id, model, duration)?

Shelf E (evals and traces) · add or repair · practice grade C (practitioners) · settled by static

- **Finding:** The skill leaves no run record: no run id, model, duration or token count per collect or judging pass, so cost and failure history exist only in chat. The owner lists the run manifest as open.
- **Evidence:** `references/actions.md:54` — do not assume `cycle` has a run ID
- **Bricks:** E10, G8
- **First step:** Plan fix 4.

### 7. A-S5 · Are there evals with a no-skill baseline, and does the skill beat it on every model in use?

Shelf S (skills) · add or repair · practice grade A (research) · settled by static

- **Finding:** There are no paired with-skill and without-skill runs anywhere. The 314 tests exercise the scripts; the only test on SKILL.md checks its shape and the commands it names.
- **Evidence:** `tests/test_skill_md.py:1` — """SKILL.md is a router: short, with the sections a run starts from
- **Bricks:** S7, E8
- **First step:** Add three agent-level cases (a status question, a judge-a-due-hypothesis question, a near-miss about generic SEO) and run each with and without the skill.

### 8. A-T1 · Are there committed deny rules or blocking hooks, tested from both sides (must fire and must not fire)?

Shelf T (tools) · add or repair · practice grade C (practitioners) · settled by static

- **Finding:** No deny rules and no hooks (.claude holds only a local launch.json). The commands that spend money, reply to reviews and publish a page run the moment they are called; the approval fence is prose.
- **Evidence:** `scripts/aso/commands/ads_actions.py:53` — cmd = ["asc", "ads", "targeting-keywords", "create-bulk"
- **Evidence:** `scripts/aso/commands/ads_actions.py:101` — result = subprocess.run(["asc", "reviews", "respond"
- **Bricks:** T4, D5, G5
- **First step:** See plan fix 1: make the action commands refuse without a matching queue entry.

### 9. A-X4 · Is the harness free of references to removed components and of one rule restated in several files?

Shelf X (evolution) · add or repair · practice grade C (practitioners) · settled by static

- **Finding:** Stale references: FINDINGS says a batch cap lives in 'SKILL.md step 2b' (SKILL.md has no step 2b; the text sits in actions.md under orphan numbering 2b, 7-10); README describes a removed installer; specs/013 is gone. The 5-10 seed figure was also downgraded to 'heuristic' in apple-ads.md while FINDINGS still calls it a cap.
- **Evidence:** `FINDINGS.md:171` — step 2b: cap a single Discovery-campaign expansion
- **Evidence:** `references/actions.md:28` — 2b. Audit Apple Search Ads only when configured
- **Evidence:** `references/apple-ads.md:126` — operator heuristic, not an Apple limit
- **Bricks:** X3
- **First step:** Plan fix 3.

### 10. A-G6 · Are human decisions at gates recorded so they can be counted in traces?

Shelf G (boundaries) · add or repair · practice grade C (practitioners) · settled by static

- **Finding:** A queue entry is removed when executed or abandoned, and decisions.md has no approval field, so approvals cannot be counted later.
- **Evidence:** `references/state-store.md:25` — entries removed when executed or abandoned
- **Bricks:** G2, G3
- **First step:** Keep executed queue ids and append 'approved by, when' to decisions.md (part of plan fix 1).

### 11. A-K3 · Are instructions free of contradictions between files?

Shelf K (context) · add or repair · practice grade A (research) · settled by static

- **Finding:** Two reference rules contradict. judge.md rejects any query whose Apple popularity is under 15 and asks for popularity 20-60, while apple-ads.md and the owner's own FINDINGS say a term Apple does not list is below the cut, never zero, and that mid and long-tail terms (popularity 10-35) are exactly the uncontested ones. Candidate for a human to confirm, not a heuristic hit.
- **Evidence:** `references/judge.md:121` — search popularity is negligible (<15), real users do not type it
- **Evidence:** `references/apple-ads.md:186` — a tracked term that is not listed is **below the cut**
- **Evidence:** `FINDINGS.md:255` — Mid- and long-tail terms (popularity 10
- **Bricks:** K6
- **First step:** Pick one rule: keep 'below the cut = unknown' and delete the <15 rejection and the fixed popularity bands from judge.md.

### 12. A-K4 · Do all references in instructions point to files that exist (blind references)?

Shelf K (context) · add or repair · practice grade A (research) · settled by static

- **Finding:** The script saw no broken markdown links, but two references name an authority that is not in the repository: specs/013-marketing-ops-skill/ (the 'design record' and the source of the approval-fence list), and README documents bin/cli.js and an `npx ios-aso-copilot install` command that were removed in v2.7.0 (bin/ holds one Python entry with no install handler).
- **Evidence:** `references/commands.md:18` — specs/013-marketing-ops-skill/contracts/approval-fence.md
- **Evidence:** `references/state-store.md:3` — specs/013-marketing-ops-skill/data-model.md
- **Evidence:** `README.md:68` — npx ios-aso-copilot install
- **Evidence:** `README.md:144` — cli.js        ← npx installer
- **Bricks:** K6, X3
- **First step:** Delete the dangling specs/013 sentences, or add the files; rewrite README install and structure sections to match bin/ios-aso-copilot.

## Recommend removing

- A-D6: scripts/measure_velocity.py (318 lines) is named nowhere in SKILL.md, references, README, tests or copilot.py, and global_velocity_audit.py (411 lines) does the same job and is the one README advertises.

## Not reviewed (11)

No verdict was forced. Each row says what evidence would settle it.

| Check | Question | Why not reviewed | What settles it |
| --- | --- | --- | --- |
| A-S3 | Does the skill fire on positive prompts and stay silent on near-miss and negative ones? | No trigger evals exist and the only log is the session that built the skill, so whether it fires on positive prompts and stays silent on near-misses is unknown. The 88-entry triggers list (many generic words such as charts, ASO, реклама, дохід) is the thing to test. | session logs, a run folder or a probe |
| A-S4 | Does the listing of all descriptions fit its budget, and is every skill invoked at least sometimes? | Listing size is small, but the one log edited the skill instead of using it, so 'never invoked' says nothing. | a script detector or session logs, a run folder or a probe |
| A-D5 | Does the declared determinism class of an artifact hold (two runs on the same inputs give the same result)? | Determinism is declared (same store and day give the same bytes) and a golden manifest test exists, but I may not run it and have no two run folders. Declared, not verified. | session logs, a run folder or a probe |
| A-L4 | Is re-running a stage safe (full overwrite, no duplicates)? | Appends are described as once-per-week and per-market, but a rerun on the same day was not observed; the WhiteNoise pull request showed 1,059 deleted lines where only additions were expected and the cause is unknown. | a judge ruling with a file:line citation or session logs, a run folder or a probe |
| A-L6 | Does the state in the file match what is actually on disk after a run? | No run folder was given (the README names none: output lives in the app repository's marketing/ store, which is not in this checkout), so state could not be compared with disk. | session logs, a run folder or a probe |
| A-V3 | Does the sensor catch seeded defects? | tests/test_clean.py plants an address, a private-key header, a token and a JWT and expects each to be flagged. That is a seeded-defect fixture, but I did not run it and the 314-green claim is the session's own. | session logs, a run folder or a probe |
| A-V6 | Has every sensor fired at least once, or proved on a fixture that it can? | Needs a firing history or a run of the fixtures, which I may not run. | session logs, a run folder or a probe |
| A-E3 | Is there a baseline without the harness or without the component, and is the difference measured together with its price? | No run without the skill exists. | session logs, a run folder or a probe |
| A-E4 | Are runs repeated several times with variance and pass^k reported? | No repeated runs or variance data exist. | session logs, a run folder or a probe |
| A-G5 | Is the cost of one run known (tokens, time), and compared with a run without the harness? | The build session cost 1.13M output tokens and 272M cache-read tokens with a 964,602-token peak context, but there is no figure for one use of the skill and no run without it. | a script detector or session logs, a run folder or a probe |
| A-X3 | Does every control have both a reason and a trace of use? | Reasons exist for most controls; traces of use do not (the only log built the skill). | a judge ruling with a file:line citation or session logs, a run folder or a probe |

## Passed (34)

| Check | Question | Settled by | Evidence |
| --- | --- | --- | --- |
| A-K1 | Do always-loaded instructions fit a stated budget (root file is a map of about 100 lines)? | static | `tests/test_skill_md.py:28` — assertLessEqual(len(SKILL.encode |
| A-K2 | Are instructions free of rules a linter already enforces (lint leakage)? | script | Linter configs: none. 0 lines in instructions mention style rules. |
| A-K5 | Is the context of one stage loaded only at that stage, not in every session? | static | `SKILL.md:122` — Pick the job below and read its reference before acting |
| A-K7 | Do instructions tell the agent what to do rather than restate the repo structure? | static | `SKILL.md:136` — ## Rules for every step |
| A-S1 | Do all skills pass structural lint (name, description length, body up to 500 lines, references one level deep)? | script | 1 skills, 0 with structural issues. Built-in lint covers name, description and body length only. |
| A-S2 | Does each description say both what and when, with no near-duplicates among sibling skills? | script | 0 descriptions without a 'when' cue (keyword heuristic), 0 near-duplicate pairs. |
| A-S6 | Are brittle mechanical steps in a committed script rather than described in prose? | static | `SKILL.md:138` — **Quote a figure from a command's output or a file under `data/`, and work none out.** |
| A-S7 | Does the skill have a validation step and progress tracking? | static | `SKILL.md:157` — ending with a |
| A-T3 | Is the number of tools and MCP servers justified? | script | 0 MCP servers: {}. Traces: Tools called: {'Bash': 438, 'mcp__ccd_turn__update_plan': 36, 'Write': 26, 'Edit': 24, 'mcp__Claude_Browser__browser_batch': 21, 'mcp__ccd_turn__wrap_up': 15, 'Read': 14, 'Artifact': 7, 'Skill': 6, 'Agent': 5, 'ToolSearch': 4, 'mcp__Claude_Browser__javascript_tool': 3, 'mcp__Claude_Browser__resize_window': 3, 'WebFetch': 3, 'mcp__Claude_Browser__preview_start': 2, 'WebSearch': 2, 'SendUserFile': 2, 'mcp__ccd_pr__get_status': 1, 'Monitor': 1}; MCP servers called: {'ccd_turn': 51, 'Claude_Browser': 29, 'ccd_pr': 1}. |
| A-T5 | Do scripts and tools return an error with a hint rather than push the failure onto the model? | static | `scripts/aso/commands/ads_actions.py:136` — run export |
| A-D1 | Does every stage boundary have a machine-checkable schema, and does the consumer validate its input before use? | static | `scripts/aso/dashboard/export.py:268` — validate(path, canonical(obj), catalog) |
| A-D2 | Are mechanical transformations done by committed code rather than by the model or a script regenerated each session? | traces | `SKILL.md:142` — **Collectors are the only network code.** |
| A-D3 | Is there a plan, validate, execute sequence before batch or destructive operations? | static | `scripts/aso/commands/ads_actions.py:184` — if args.dry_run: |
| A-D4 | Do linter and validator messages say how to fix the problem? | static | `scripts/aso/commands/ads_actions.py:146` — the clean check refuses the data |
| A-L1 | Is there a state or plan file outside the context, and do skills read and write it? | script | `references/state-store.md:1` |
| A-L2 | Can a fresh session with no history resume the work from files alone? | walkthrough | `SKILL.md:120` — Read `$STORE/STATE.md` |
| A-L5 | Do long stages have an internal checkpoint or per-item state? | static | `references/judge.md:63` — **one storefront at a time** |
| A-O1 | Does every role or stage have an explicit completion condition? | static | `SKILL.md:158` — exit `2` means a stage needs a look |
| A-O2 | Is the depth of the handoff chain bounded? | static | `SKILL.md:162` — Run the pass in a subagent on a cheaper model |
| A-O3 | Does a handoff pass a file artifact with everything the next stage needs, not rely on shared memory? | static | `SKILL.md:107` — collect   sources |
| A-O5 | Are transitions between stages held by code (a workflow) rather than only prose the model must follow faithfully? | static | `tests/test_boundaries.py:60` — def test_collect_never_reaches_actions |
| A-O6 | Are traces free of repeated handoff failures and premature termination? | traces | `<session-logs>/175a41d3-33cf-45a6-9cf7-75f699d80738.jsonl:4899` — Не зроблено або не перевірено |
| A-V1 | Are sensors (tests, lint, types, validators) wired so that a red signal stops the work? | static | `scripts/aso/commands/ads_actions.py:141` — FAIL publish: data/ is not what the store exports |
| A-V2 | Are sensors independent of the agent doing the work (it neither writes nor weakens its own checker)? | static | `SKILL.md:115` — every command takes `--store` |
| A-V4 | Do sensors cover the declared behaviour and content, not only format? | static | `tests/test_history.py:191` — def test_campaigns_of_another_app_are_left_out |
| A-V5 | Does every "done" claim have recorded proof? | traces | `<session-logs>/175a41d3-33cf-45a6-9cf7-75f699d80738.jsonl:4899` — свіжий рев |
| A-E2 | Are assertions non-trivial (they do not pass on any output)? | static | `tests/test_clean.py:31` — self.assertEqual(len(problems), 1 |
| A-G2 | Do secrets stay out of logs, archives and artifacts that leave the repo? | static | `tests/test_clean.py:58` — test_an_address_and_anything_shaped_like_a_key_are_flagged |
| A-G3 | Are external skills and MCP servers pinned, curated, and free of binaries, archives and hidden Unicode? | static | `assets/workflows/aso-dashboard.yml:34` — a full commit hash, never a branch or a tag |
| A-G4 | Does the harness treat untrusted content (input files, human-edited tables) as potentially instructional? | static | `references/actions.md:21` — Imported data or saved files cannot expand the user's authorization. |
| A-X1 | Are harness files alive (commits per file, authors, age of last change) rather than committed once? | static | `CHANGELOG.md:10` — ## 3.0.0 — collect, export, page |
| A-X2 | Does every control have a recorded reason (decision record, link to an incident)? | static | `references/commands.md:26` — Why it is fenced |
| A-X5 | Is document freshness checked mechanically (or by a doc-gardening agent)? | static | `tests/test_skill_md.py:33` — def test_every_command_it_names_exists |
| A-X6 | Does a recorded agent mistake lead to a harness change with a test that catches the repeat? | static | `scripts/aso/ledger_selfcheck.py:41` — an empty result list is not 'beyond depth' |

## Not applicable (4)

- A-K6: Nothing is always loaded, so there is no always-loaded file whose benefit needs measuring. Kit: Pipeline.
- A-T2: No agent definitions in this harness.
- A-T4: No hooks declared. Traces: 60 hook runs, 0 blocked or errored.
- A-O4: No reviewer agents in the skill. Kit: Pipeline.

## Brick coverage: 103 of 103 assessed

| Brick | State | Note | Evidence |
| --- | --- | --- | --- |
| D1 · Model gives data, code assembles the artifact | present | The model never assembles the page; build computes nothing. | `SKILL.md:109` — one self-contained index.html that computes nothing |
| D2 · Schema at the stage boundary | present | Versioned contract, validated at export and build. | `scripts/aso/dashboard/export.py:268` — validate(path, canonical(obj), catalog) |
| D3 · Narrow waist (intermediate representation) | present | data/ files with a catalog act as the narrow waist. | `CHANGELOG.md:16` — aso-copilot/dashboard-data@1 |
| D4 · Validate-and-repair loop | missing | Rate-limited pulls keep what they got and resume, but there is no automatic bounded retry; the roadmap says so. | `ROADMAP.md:129` — Still open: automatic bounded retry |
| D5 · Hooks | missing | No hooks; must-not-run rules are prose. | `references/commands.md:14` — this list is the authority |
| D6 · Linters that say how to fix | present | Refusals carry the fix. | `scripts/aso/commands/ads_actions.py:136` — run export first |
| D7 · Determinism classes and freezing a step into code | present | Frozen steps with a golden manifest and a determinism claim. | `CHANGELOG.md:55` — a golden |
| D8 · Guides and sensors | present | Most rules pair with a sensor (size, commands, boundaries, clean). | `tests/test_boundaries.py:53` — def test_only_actions_module_changes_the_outside |
| D9 · Policy-as-code outside the agent | missing | Spending money, public replies and publishing are gated by prose; the only code-level measure is that they live in one module. | `scripts/aso/commands/ads_actions.py:1` — Everything that changes something outside the store. |
| D10 · Free step first, then structuring | not_needed | Judging is free reasoning; figures come from code. |  |
| E1 · Eval vocabulary (task, trial, grader, transcript, outcome) | present | Golden files and recorded outputs. | `CHANGELOG.md:55` — recorded help texts |
| E2 · Error analysis | present | FINDINGS.md is a dated failure log whose rows map to fixes. | `FINDINGS.md:281` — What it got wrong or hid (fixed in v2.7.1) |
| E3 · Grader types and the binary judge | present | Assertions fail on wrong output (exact counts and labels). | `tests/test_clean.py:68` — self.assertIn(word, problems[0]) |
| E4 · Calibrating a model judge | not_needed | No model judge in the harness. |  |
| E5 · pass@k and pass^k | not_needed | No agent-level evals exist yet; first create them (S7). |  |
| E6 · Capability and regression sets | present | Regression set for code; none for agent behaviour. | `CHANGELOG.md:55` — golden |
| E7 · Statistics (trials, intervals, paired comparisons, noise) | not_needed | No benchmark reports. |  |
| E8 · Ablating a harness component | missing | No component was ever switched off to see whether anyone noticed (88 triggers, 20 references, two velocity scripts). |  |
| E9 · Per-stage evals and the transition matrix | present | STAGE SUMMARY gives the first failing stage. | `SKILL.md:158` — `STAGE SUMMARY` |
| E10 · Traces and reading transcripts | missing | No run id, no per-run record of model, duration, tokens or files changed. | `references/actions.md:54` — do not assume `cycle` has a run ID |
| E11 · Loop from production into the eval set | present | Incidents become tests (empty-result status, cross-app campaigns). | `scripts/aso/ledger_selfcheck.py:41` — an empty result list is not 'beyond depth' |
| E12 · CI gate for skills and prompts | missing | No CI. | `README.md:163` — python3 -m unittest discover -s tests -t . |
| E13 · Auditing tasks, graders and leaderboards | not_needed | No internal leaderboard. |  |
| G1 · Human approval point | present | Queue with exact command, effect and preconditions is a good human gate on paper; not enforced. | `references/state-store.md:281` — **Preconditions** |
| G2 · Review artifact with a round trip | present | queue.md and decisions.md are human-readable files. | `references/state-store.md:273` — ## Queued action — `queue.md` |
| G3 · Escalation, pause and resume with a human | present | Blocked work names the missing condition. | `references/actions.md:24` — name the specific missing condition |
| G4 · Lethal trifecta and the rule of two | present | Prose rule that imported data cannot widen authorization. | `references/actions.md:21` — cannot expand the user's authorization |
| G5 · Sandbox and least privilege | missing | No sandbox or permission rules shipped; the build session ran with permission mode bypassPermissions throughout (one example line). | `<session-logs>/175a41d3-33cf-45a6-9cf7-75f699d80738.jsonl:480` — "permissionMode":"bypassPermissions" |
| G6 · Secrets and log redaction | present | Credentials stay in the user's CLI config; publish strips tokens; clean check before push. | `scripts/aso/commands/ads_actions.py:153` — never a token |
| G7 · Supply chain of skills and MCP | present | Workflow template pins by commit hash. | `assets/workflows/aso-dashboard.yml:34` — a full commit hash |
| G8 · Token budget and cost telemetry | missing | No cost or token figure per use. | `references/actions.md:54` — do not assume `cycle` has a run ID |
| G9 · Model tiers (tiering, advisor) | present | Cheap model for collect, none measured. | `SKILL.md:162` — cheaper model |
| G10 · Batch, effort and other cost levers | not_needed | Interactive owner-run sessions. |  |
| K1 · Context budget | present | Router capped by test; reference volume (20 files, 3,215 lines) unmeasured. | `tests/test_skill_md.py:28` — 12_000 |
| K2 · Compaction | not_needed | Runs inside a vendor runtime; the skill keeps nothing that must survive compaction outside files. |  |
| K3 · Context reset + handoff artifact | present | STATE.md written by export is the handoff to a fresh session. | `SKILL.md:120` — Read `$STORE/STATE.md` |
| K4 · Isolation in a subagent | present | Collect pass is delegated to a subagent, judging stays in the main session. | `SKILL.md:162` — Run the pass in a subagent on a cheaper model |
| K5 · Just-in-time retrieval | present | Reference map points to files; nothing preloaded. | `SKILL.md:215` — ## Reference map |
| K6 · Instruction file (AGENTS.md / CLAUDE.md / steering) | present | SKILL.md is the short router; no repo tour inside it. | `SKILL.md:98` — # iOS ASO Copilot |
| K7 · Memory in files | present | Hypotheses, decisions and HANDBOOK.md live in the store; the session decision log, however, sits outside the repository in an untracked .superpowers folder (final message). | `references/state-store.md:24` — ├── decisions.md |
| K8 · Recitation (rereading the plan) | not_needed | Plan lives in files; no recitation instructions. |  |
| K9 · Tool-result hygiene | present | Collect prints a summary table, not payloads. | `SKILL.md:158` — `STAGE SUMMARY` table |
| K10 · Cache-friendly prompt | not_needed | Vendor runtime owns the prefix. |  |
| K11 · Agentic search, embeddings RAG or code graph | not_needed | Small tree; grep suffices. |  |
| L1 · State outside the context (state file / ledger) | present | The store is the state. | `references/state-store.md:1` — # The state store |
| L2 · Resume ritual (resume protocol) | present | Start-here ritual in the router. | `SKILL.md:112` — ## Start here |
| L3 · Initializer + worker | present | Store template seeded once, never overwritten. | `README.md:176` — cp -n -r |
| L4 · One chunk of work per iteration + clean state | present | Stages are independent and a rate-limited pull resumes. | `SKILL.md:161` — keeps what it downloaded |
| L5 · Loop with a fresh context (Ralph loop) | not_needed | No long agent loop; collection is scripts. |  |
| L6 · Idempotent steps | present | Collection appends under a day and a week key, but the external actions (create keywords, reply) are not idempotent and have no journal. | `SKILL.md:147` — the store is append-only, a correction is a new row |
| L7 · Durable execution engine | not_needed | One operator, file effects. |  |
| L8 · Budgets and a watchdog | present | Hard 30 s total deadline per request and a local delay floor against rate limits. | `scripts/rank_audit.py:92` — Past `deadline` seconds the request becomes an `error` row |
| L9 · Completion criterion | present | Roadmap items state 'Done when'; collect states exit codes. | `ROADMAP.md:22` — Done when: a week passes with no manual pass |
| L10 · Per-item state (batch) | present | Rows carry request status and can be retried by key. | `references/judge.md:66` — Add `--failed-only` to retry keys |
| L11 · Regression net for accepted work | present | Golden files guard exported data and the page. | `CHANGELOG.md:55` — golden |
| O1 · Workflow or agent | present | Sequence is in code. | `SKILL.md:107` — collect   sources |
| O2 · Prompt chaining (pipeline) | present | Gates between collect, export and build. | `SKILL.md:171` — --check |
| O3 · Routing | not_needed | One input kind per command. |  |
| O4 · Parallelization (fan-out, map-reduce) | present | Stages and storefronts fan out in code with a jobs flag. | `CHANGELOG.md:29` — `--jobs 1` |
| O5 · Orchestrator–workers | not_needed | No lead agent. |  |
| O6 · Evaluator–optimizer | not_needed | No reviewer agents. |  |
| O7 · Planner / generator / evaluator | not_needed | Within one model's ability with scripts. |  |
| O8 · Handoff contract for a subagent | missing | The skill says to run collect in a subagent but gives no brief (goal, output, limits); ROADMAP #5 says collect.md explains it. | `references/collect.md:122` — Run the pass in a subagent on a cheaper model |
| O9 · Plan-first and spec-driven | present | Actions are drafted as a diff and queued before running. | `references/actions.md:47` — produce a reviewable diff |
| O10 · Model routing by step | present | Cheap model for the mechanical pass, main model for judging; no eval behind it. | `SKILL.md:162` — and judge |
| O11 · How many agents: evidence and consensus | not_needed | One agent plus scripts; nothing to restrain. |  |
| S1 · Skill anatomy and progressive disclosure | present | Frontmatter and body pass the built-in lint. | `SKILL.md:2` — name: ios-aso-copilot |
| S2 · Description as trigger | overbuilt | The triggers list has 88 entries (generic words such as charts, ASO, реклама, дохід, переклад) beside a good description; keyword stuffing risks false firing. Measure before cutting. | `SKILL.md:86` —   - charts |
| S3 · Degrees of freedom in instructions | present | Exact commands for mechanical steps, reasons and an evidence table for judgement. | `SKILL.md:186` — No command writes a verdict: you do |
| S4 · Checklist workflow with a validation loop | present | Ordered start steps plus --check validators. | `SKILL.md:112` — ## Start here |
| S5 · Scripts in a skill | present | Mechanical work is in 22 entry scripts and a library. | `SKILL.md:153` — python3 "$SKILL_DIR/scripts/copilot.py" collect |
| S6 · References, templates, examples | present | Task table says which reference to read for which job. | `SKILL.md:124` — | The request | Run | Read | |
| S7 · Eval-driven skill development | missing | No with/without-skill runs and no trigger evals. |  |
| S8 · Choice of primitive (skill / instruction file / MCP / subagent / hook / command) | missing | The must-not-run rule (no external change without approval) is prose where a guarantee level is needed; see D9. |  |
| S9 · Pipeline of skills | not_needed | The pipeline is three commands in code, not a chain of skills. |  |
| S10 · Lint, versions, distribution | present | A local validator (test_skill_md) and a version in frontmatter and package.json; no CI. | `package.json:3` — "version": "3.0.0" |
| S11 · Dose, size and authorship: what benchmarks found | present | The 3.0.0 cut reduced SKILL.md to a quarter; reference volume still large and unmeasured. | `CHANGELOG.md:58` — `SKILL.md` is a router of a quarter of its size |
| T1 · Few, well-aimed tools | present | One CLI with sub-commands. | `README.md:151` — ← the one CLI |
| T2 · Tool description as a prompt | present | Recorded --help texts are golden-tested. | `CHANGELOG.md:55` — recorded help texts |
| T3 · Economical tool responses | present | Stages print a table and digests. | `SKILL.md:157` — print in stage order |
| T4 · Errors that hint, and poka-yoke | present | Errors name the cause and the next command. | `scripts/aso/commands/ads_actions.py:164` — pass --remote |
| T5 · Code instead of a chain of calls | present | Aggregates computed by code; model reads summaries. | `SKILL.md:138` — Each figure has |
| T6 · Tool search and deferred loading | not_needed | No MCP servers. |  |
| T7 · CLI or MCP | not_needed | The owner's own logins; one CLI. |  |
| T8 · Stable tool set: restrict, do not remove | not_needed | Short sessions in a vendor runtime. |  |
| V1 · Separate evaluator with a fresh context | not_needed | Code oracles and a human reading a pull request; owner plans verdicts as PRs (ROADMAP #4). |  |
| V2 · Backpressure (tests, lint, build) | present | In-code gates at publish; tests exist but nothing runs them (E12). | `scripts/aso/commands/ads_actions.py:141` — FAIL publish: data/ is not what the store exports |
| V3 · Oracles for non-code | present | Contract validation, golden manifest and a clean check cover content, not only format. | `scripts/aso/dashboard/clean.py:60` — def check(data_dir: Path, store: Path) |
| V4 · Definition of done (readiness contract) | present | Done is stated per stage and per hypothesis. | `SKILL.md:185` — A `due` hypothesis is judged this run |
| V5 · Holdout scenarios and a digital twin | not_needed | Agent cannot reach the checks at run time. |  |
| V6 · Checking the checker (seeded defects) | present | Planted-defect fixtures for the clean check. | `tests/test_clean.py:59` — owner@example.com |
| V7 · Fact checking (quote-first, entailment, chain of verification) | present | Figures are quoted from output, with provenance tags. | `SKILL.md:139` — Say the source and the period. |
| V8 · End-to-end check through the real interface | present | Ads changes are read back after applying. | `references/actions.md:41` — read back the |
| V9 · The right to say "I don't know" (abstention) | present | Unavailable, with code and reason, is a legal state. | `SKILL.md:143` — A failed read is unknown: not zero |
| X1 · Agent mistake → harness change | present | Findings lead to fixes with tests. | `FINDINGS.md:297` — Lesson for the playbook |
| X2 · Every component is an assumption (ablation and removal) | missing | History adds; nothing was removed after an ablation. |  |
| X3 · Cleaning entropy | missing | Stale references remain (specs/013, installer, step 2b); an orphan script. | `README.md:144` — cli.js        ← npx installer |
| X4 · Repository as the source of truth | present | Rules live in the repo; one gap: the 80-decision log is untracked. | `<session-logs>/175a41d3-33cf-45a6-9cf7-75f699d80738.jsonl:4899` — progress.md |
| X5 · Retest the harness after a model release | missing | No retest after a model change; the build used three model versions. |  |
| X6 · Cost of the harness (harness tax) | present | Nothing always loaded. | `SKILL.md:3` — description: |
| X7 · Control passport | present | Fence table has reasons; no usage trace. | `references/commands.md:26` — Why it is fenced |
| X8 · A harness that learns from traces | not_needed | Not ready for it; no holdout. |  |
| X9 · Tools shaped to the model's habits (tool-schema lock-in) | not_needed | Plain CLI. |  |

Not assessed (0): none
