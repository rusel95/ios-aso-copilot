# Playbooks: product page, reviews, content

Three independent sub-playbooks. Each states its own precondition and refuses to proceed past it —
none of these three depend on each other or on the ASO loop.

## Product Page Optimization (PPO) — the only real A/B test (`doc:HANDBOOK.md§1.5`)

Apple's built-in test. What it can test: **icon, screenshots, preview video — and only these.**
Never name, subtitle, keywords or description — those have no A/B mechanism at all; anything
calling itself an A/B test of keywords is actually a weaker before/after comparison, because
everything else in the world also changed between "before" and "after".

**Feasibility first.** Use Apple's duration estimate, baseline, desired effect and traffic allocation.
A universal downloads/week cutoff cannot determine whether a particular test will be conclusive.
If volume is sparse, prepare one strong contrast and keep the outcome inconclusive until evidence
supports a decision. See https://developer.apple.com/app-store/product-page-optimization/.

**Candidate test order**, to adapt to the evidence and app:

1. **First screenshot** — test whether the benefit is understandable
2. **Icon** — influences search results before anyone even opens the page
3. Screenshot order
4. **Preview video** — present or absent
5. Remaining screenshots

For utility apps specifically, the first screenshot should show **a substantiated result** with the actual UI; any savings or performance number must come from a reproducible example, not a universal promise.

Up to 3 treatments against the original at once. Once a variant wins, it becomes the new original
and the next test runs against it — treat this as a ladder, not a one-shot test.

## Custom Product Pages (CPPs) — organic since 30 July 2025

Since 30 July 2025, CPPs can be linked to keywords from the keyword field and served **organically**
in search results, not just used as paid-traffic landing pages — the per-app limit was raised from
35 to 70 at the same time (`research.md §7`). This moved CPPs out of "paid acquisition nice-to-have"
and into core ASO.

**Precondition**: each CPP needs its **own** screenshot set (reusing the default set defeats the
purpose — a CPP exists to show a different first impression to a different search intent), and which
keywords deserve a dedicated page is a traffic-data question — a page only pays for itself if the
keyword it targets brings enough search volume to matter. Until weekly search-segment data exists to
answer that, this playbook has nothing to queue. Once it does: propose CPP candidates the same way
`references/aso-loop.md` proposes keywords — relevance, popularity, and specifically here, volume
high enough to justify a dedicated screenshot set. Creating or updating a CPP is fenced
(`references/commands.md`) — prepare and queue, never apply unattended.

## Reviews (`doc:HANDBOOK.md§1.6`)

**List worst-rating-first**, with a drafted reply for every unanswered review, **queued and never
posted automatically** (`asc reviews respond` is fenced — a public reply under the developer's name is
exactly the kind of action this skill never takes on its own). Replying matters most on 1–3★: the
reply is public, future visitors read it, and the original author often revises their rating after a
good one.

Recent review language can reveal current product issues. Apple does not publish a numeric
exchange rate between old and new reviews or a formula converting them into search rank. Do not
infer ad spend or download momentum from written-review counts.

**The ask itself**: native `SKStoreReviewController` only — never a custom review-prompt UI. Ask
**immediately after a win**, which for this app is unambiguous and already built: the confetti
screen after a month's cleanup completes, right after "freed X GB" is shown. **Never ask before a
paywall and never ask right after an error** — Apple grants only 3 prompts per user per year, and
spending one at a bad moment is a wasted, non-recoverable shot. If asked to add a review prompt
anywhere else in the app, name why the confetti screen beats the proposed location rather than just
agreeing to add another one.

## Content backlog — short-form video (`doc:HANDBOOK.md§4.2`)

**Highest-priority content type.** What works is one of three formats, never an app demo:

1. **Oddly satisfying** — fast cut of swipes, a GB counter melting down, no words, music only
2. **Life hack** — "Your phone says storage is full. Don't delete anything. Do this instead"
3. **Relatable pain** — "Storage Almost Full" screenshot → reaction → resolution

What doesn't work, and should be rejected as a concept if proposed: a developer-intro video, a
step-by-step UI tour, or anything past 15 seconds without a hook in the first 2.

**Mechanics that shape every concept**: the first 1–2 seconds decide everything — a number on
screen immediately ("−54 GB") beats any line of text as the hook. Post one video to all three
platforms (TikTok, Reels, Shorts) — the cost of the third placement is near zero. **Quantity over
polish**: the algorithm is a lottery, thirty simple videos are thirty tickets; a few polished ones
are not a substitute. Do not propose TikTok ad spend at this stage — the same budget in Apple Ads
buys a warmer user (`references/apple-ads.md`).

**This app's own visual hooks** — build concepts on these, not generic advice:
- The melting GB counter (the number that drops as compression runs — format 1, oddly satisfying)
- The swipe gesture itself (the core interaction — format 1, fast cuts of swipe-to-keep/delete)

**Tracking, honestly**: use a campaign URL/CPP where supported, recording attribution limits; views alone cannot be converted to installs. Each content item is tracked as shipped or not-shipped, with where it was
published and when. **Do not claim attribution a content item can't have** — there is no measurable
link between "this TikTok got N views" and "this many downloads came from it" (the same
no-attribution rule as keywords, `references/provenance.md`); track output (shipped, where, when),
never a manufactured download count next to it.
