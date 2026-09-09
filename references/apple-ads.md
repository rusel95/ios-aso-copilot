# Apple Ads — setup, structure, economics

Historical app/account figures below are examples, not current configuration. Resolve identity, price, proceeds, trial duration, attribution window and account access from the current app. All calculator outputs are scenarios; they do not justify scaling without mature cohort economics and a bounded loss budget. Paid installs have no guaranteed permanent organic-rank effect.


**This playbook opens at account creation, not campaign setup.** Apple Ads is a separate account at
ads.apple.com — not App Store Connect. Credentials are now live
(`live:asc ads auth status@2026-08-19` → profile "Compresso Ads", validation ok; `live:asc ads
me@2026-08-19` → `parentOrgId 23140040`) — Steps 1-3 below are done; pass `--org 23140040` (the
active profile has no org selected by default) or run `asc ads auth switch` to persist it. Step 4
(campaign structure) is next, whenever campaign work is actually wanted — nothing has been created
yet (`asc ads campaigns list --org 23140040` → empty).

## Credential-state detection — never conflate the two stores (FR-031)

`asc` keeps **two independent credential stores**. Check both, report both, and never collapse them
into one "asc is not set up" statement — that's simply wrong when only one is missing, and it's the
first thing this playbook must get right before saying anything else:

```bash
asc auth status        # App Store Connect — configured, used by every other playbook in this skill
asc ads auth status     # Apple Ads — separate account, separate keys
```

## Step 1 — Create the Apple Ads account (Developer's — needs web sign-in)

Sign in at ads.apple.com with the Apple ID used for App Store Connect (or create the Apple Ads
account if none exists there yet — read the live screen; Apple's own onboarding flow is the
authority on the exact sequence, not this file). This step is fenced from the skill regardless of
mode — it's an account creation under the developer's identity — so it's always the developer's to do, in every mode.

## Step 2 — Get the "API Account Manager" role

The account needs a user with the **API Account Manager** role before the public-key upload field
even appears in the UI (Account Settings). Without it, there is nothing to generate a key against —
if the field isn't there, this is why; it's not a bug in these instructions, check the role first.

**Where this actually lives**, confirmed against Apple's own help pages
[web:ads.apple.com/app-store/help/get-started/0011-invite-users-to-your-account@2026-08-19,
web:ads.apple.com/app-store/help/campaigns/0022-use-the-campaign-management-api@2026-08-19]:

- Account Settings → **User Management** tab. Two branches live there off the same single-select
  role list (Account Admin / Account Finance / Account Read Only / API Account Manager / API
  Account Read Only / Limited Access): **edit an existing user's row**, or **Invite User** for
  someone new. Landing straight on the Invite User form is the "add a new person" branch — check
  User Management's main listing for your own row first; don't assume a second identity is required
  just because Invite User is what's on screen.
- **Confirmed (2026-08-19, live walkthrough)**: roles genuinely are mutually exclusive per user, and
  Apple explicitly does not let a sole Account Admin also hold API Account Manager on the same
  login — the API tab / public-key field stays empty even for Account Admin. A **second identity**
  is required, not optional. That second identity needs its own real Apple ID — a Gmail `+` alias
  (e.g. `you+ads@gmail.com`) **does not work**; Apple ID creation rejects plus-addressed emails.
  Use a genuinely separate inbox (a second Gmail account, an iCloud address, anything you can
  receive mail at) instead. Invite it from User Management with the API Account Manager role,
  accept the invite, sign in as that identity, and the **API** tab (Account Settings → API) then
  shows the public-key upload field. It's a one-time-use identity — once the key is uploaded and
  Client ID / Team ID / Key ID are captured, there's no need to sign into it again.
- The public-key upload field is on a separate **API** tab in Account Settings that only appears
  once you're signed in **as the API Account Manager identity** — not visible from User Management,
  and not visible to the plain Account Admin login. This is the field Step 3 below refers to.

## Step 3 — Generate the key pair and register it with `asc`

There is no single paste-able token here — Apple Ads API auth is OAuth2 client-credentials with a
**self-generated EC key pair** (curve `prime256v1`, i.e. P-256), not a downloaded secret. In broad
strokes (confirm the exact field names against the live Account Settings → API screen, since Apple's
UI wording shifts over time and this file is not the authority on it):

1. Generate a private key locally, e.g. `openssl ecparam -genkey -name prime256v1 -noout -out
   private-key.pem`, and its public counterpart.
2. Upload the **public** key in the Apple Ads account's API settings. Apple returns a **Client ID**
   and **Team ID** (both look like `SEARCHADS.xxxxxxxx-xxxx-...`) and a **Key ID** for that
   registration.
3. Register the credential set locally:

   ```bash
   asc ads auth login \
     --name "Ads" \
     --client-id "SEARCHADS..." \
     --team-id "SEARCHADS..." \
     --key-id "<KEY_ID>" \
     --private-key ./private-key.pem
   ```

   Default storage is the macOS System Keychain — use that, not `--bypass-keychain --local`, which
   writes the credential set to `.asc/config.json` inside the repo working tree instead.

4. Find the organization ID rather than guessing it:

   ```bash
   asc ads auth discover --output json
   ```

   Then re-run `login` with `--org "<ORG_ID>"` if it wasn't already supplied, or use `asc ads auth
   switch` if multiple orgs come back.

5. Verify: `asc ads auth status`, and `asc ads auth doctor` if anything looks wrong.

**After this one-time setup, `asc` signs the client-secret JWT and refreshes access tokens itself —
no ongoing token management, no wrapper needed.** `asc ads auth token --confirm` will print a
current access token on demand, but there is nothing to copy into anywhere by hand on a recurring
basis; that's the point of the client-credentials flow over a plain API token.

Once credentials exist, real query data arrives through tooling already installed —
`asc ads reports search-terms` / `keywords` — no additional purchase needed for that part.

---

## Step 4 — Four-campaign architecture

Once credentials exist, the structure (`doc:HANDBOOK.md` Part 2.2 for the full reasoning):

| Campaign | Match type | Search Match | Role |
|---|---|---|---|
| Brand | exact | **off** | capture searches for the app's own name — cheap, defends the name |
| Category | exact | off | head terms in the app's category ("photo compressor", etc.) |
| Competitor | exact | off | competitor app names surfaced via `references/commands.md`'s iTunes Search API discovery |
| Discovery | broad | **on** | everything else — where new query data comes from |

**The negative-keyword wiring that matters**: every exact-match term live in Brand, Category or
Competitor is added as a **negative** on Discovery. Without this, Discovery (broad, Search Match on)
bids against your own exact-match campaigns for the same query, driving your own cost up for no
gain. This is set up once and maintained every time a term graduates from Discovery (Step 6 below).

Campaign *creation* is fenced (`references/commands.md`) — this section is what to prepare and
queue, never what to apply unattended.

## Step 5 — Economics: is the spend paying for itself

`$SKILL_DIR/scripts/economics.py` computes LTV per trial, the break-even trial rate, and a verdict
against the observed cost per install — every output tagged `derived:` naming every input it used
(FR-034, FR-039), because a scaling decision made from an untraceable number is a decision nobody
can debug later.

```bash
python3 $SKILL_DIR/scripts/economics.py --price 49.99 --commission 0.15 --retention 0.221 --trial-to-paid-cvr 0.38 --cpi <observed>
```

If the measured trial rate is **below** break-even: recommend fixing the trial rate before raising
spend. This is product work (onboarding, paywall copy, trial length) and it is cheaper than bid
optimization, because bidding harder to buy more installs at a trial rate that doesn't convert just
buys more of the same loss (US5 acceptance scenario 3). State this as the recommendation, not as a
foregone conclusion — it's an argument, not a citation, so it isn't itself provenance-tagged
(`references/provenance.md`), only the figures it rests on are.

Every input that is an estimate rather than a measured figure is labelled as such, and the
conclusion's sensitivity to it is stated (US5 acceptance scenario 5) — e.g. "retention is the
21-day figure from RevenueCat as of `<date>`; if actual 12-month retention comes in lower, break-even
rises and today's spend may already be under water."

## Step 6 — Harvesting from Discovery

Once Discovery has run long enough to produce query data:

```bash
asc ads reports search-terms --campaign <discovery-campaign-id>
```

For each winning query (converts, and passes the same conversion-veto reasoning as organic keyword
candidates — `references/aso-loop.md`): propose it for **promotion** to the matching exact-match
campaign **and** as a **negative keyword** on Discovery, in the same queue entry. Both together, not
one — promoting without the negative just recreates the campaigns-bidding-against-each-other problem
Step 4's wiring exists to prevent (US5 acceptance scenario 4). Both are prepared and queued, never
applied unattended (`asc ads targeting-keywords create-bulk`/`update-bulk` and the negative-keyword
write commands are both fenced — `references/commands.md`).

## Degraded path — no credentials yet (today's actual state, and S5)

Asked to "run ads" / "запусти рекламу" before Step 1–3 are done: open at **Step 1**, not campaign
work, name the missing credential state precisely (distinguish `asc auth` from `asc ads auth` per
the detection rule above), and do not attempt any `asc ads` write. Nothing past Step 3 can be shown,
because there is nothing to show — say that plainly rather than describing a hypothetical campaign
structure as if it were ready to launch.
