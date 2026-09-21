# Channel Playbooks: Off-Store Traffic Generation

Tactical playbooks for generating external, high-intent traffic to kickstart App Store download velocity.
Every external channel campaign is executed as a testable, tracked **Channel Hypothesis (`C001...`)** documented under `marketing/hypotheses/` and logged in `marketing/campaigns.csv`.

---

## 1. Reddit: The High-Intent Channel

Reddit users have urgent, specific problems ("iPhone storage full", "System data taking 50GB", "iCloud full but don't want to upgrade"), but the platform has an extreme allergic reaction to marketing. Follow these strict rules to generate organic traffic without getting banned.

### Golden Rules of Reddit
1. **The 90/10 Rule**: 90% of your account activity must be genuine help/participation. Max 10% may mention your app.
2. **Value-First Always**: A comment must solve the user's problem *even if they never download your app*.
3. **Transparent Disclosure**: Always state your relationship: *(Disclaimer: I'm the developer of [App Name])*. Redditors respect indie developers; they ban astroturfers and fake users.
4. **No Link Shorteners**: Use direct App Store campaign URLs (`https://apps.apple.com/app/id<APP_ID>?ct=...`). Shorteners are automatically spam-filtered by Reddit bots.
5. **Pacing**: Never comment in more than 2–3 threads per day with app mentions. Space them out across days and different subreddits.

---

### Playbook 1A: Contextual Problem-Solving (Comment Engine)

Target subreddits where users post daily tech support questions:
- `r/iphone` (4.6M members)
- `r/ios` (1.2M members)
- `r/iphonehelp` (130k members)
- `r/iCloud` (50k members)

#### Target Search Queries
Search Reddit weekly for fresh posts (sort by New / Past 24 hours):
- `url:https://www.reddit.com/r/iphone/search/?q="system+data"+OR+"storage+full"&sort=new`
- `url:https://www.reddit.com/r/ios/search/?q="storage"+OR+"iphone+storage"&sort=new`
- `url:https://www.reddit.com/r/iphonehelp/search/?q="storage"&sort=new`
- `url:https://www.reddit.com/r/iCloud/search/?q="storage"+OR+"full"&sort=new`

#### The 3-Step Value-First Reply Blueprint

```text
[Step 1: Explain the Root Cause]
Explain WHY the user is seeing this storage bug / bloat (e.g. iOS caches, unpurged system logs, 4K ProRes video bitrates).

[Step 2: Free Built-in Solutions First]
Give 2–3 free solutions using native iOS tools:
- Perform a hard reboot (triggers the `maintenanced` system process to flush cache).
- Check Recently Deleted in Photos (often forgotten).
- Clear Safari website data (Settings > Safari > Clear History).
- Offload heavy apps like Instagram or Telegram.

[Step 3: Seamless & Transparent App Mention]
Introduce your app as a focused solution:
"If you want to solve this specifically, you can use [App Name] for this (on-device, private, lets you clean up without subscriptions): [App Store Link with ?ct=...]. But definitely try the reboot and cache clear first!"
```

---

### Playbook 1B: Developer Showcase (`r/iosapps`)

`r/iosapps` permits developer promotion under strict format guidelines:
- **Prerequisite**: 10+ local comment karma in `r/iosapps` before posting.
- **Frequency**: Max once per 30 days per developer.
- **Post Flair**: Must select appropriate flair (e.g. `Freemium` or `Paid`).
- **Mandatory ABC Structure**:

```text
Title: [App Name] — [One-line value proposition / problem solved] [Freemium]

Hey r/iosapps! I'm the developer of [App Name]. [Brief backstory on the problem you hit and why you built a native tool to solve it].

**A - Answer (Problem solved):**
[Explain the exact problem solved and why existing alternatives are frustrating or overpriced].

**B - Better (Key differences):**
- Native & Private: Built cleanly with Swift/SwiftUI. Zero tracking.
- Fast & lightweight: Thoughtful gestures and UX.
- Transparent: No dark patterns or predatory pricing.

**C - Cost & Links:**
Freemium / Free trial with transparent purchase options.
App Store: https://apps.apple.com/app/id<APP_ID>?ct=reddit_iosapps_abc
```

---

## 2. Threads & Twitter/X: Visual Hooks & The Anti-iCloud Tax

On microblogging platforms, attention spans are 2 seconds. The winning angle is financial relief + visual proof.

### Angle 1: "The Anti-iCloud Tax"
- **Hook**: "Stop paying Apple $2.99 every single month just because your camera roll is bloated."
- **Narrative**: Apple charges $36/year for 200GB iCloud just to hold uncompressed 4K video clips you took 2 years ago. Compressing them locally shrinks 30GB down to 4GB in minutes.
- **Call to Action**: Direct App Store link with `?ct=threads_icloud_tax` or `?ct=x_icloud_tax`.

### Angle 2: Visual Before/After Card
- **Asset**: Side-by-side screenshot:
  - Left: Problem state (e.g. storage red bar / unorganized data).
  - Right: Solved state after using [App Name].
- **Copy**: "Turned a frustrating problem into a 3-minute fix on my iPhone. All processed on-device with zero server uploads."

---

## 3. Product Hunt & Hacker News (Show HN)

Tech communities respond strongly to:
1. **100% On-Device Privacy**: No analytics tracking your photos, no external APIs.
2. **Native Performance**: Swift + SwiftUI + Metal + VideoToolbox.
3. **Honest Business Model**: Free trial month with transparent one-time purchase.

### Show HN Structure:
```text
Show HN: [App Name] – [One-line pitch of native iOS utility]

Hi HN, I built [App Name] because I was tired of existing tools requiring cloud accounts and charging aggressive subscriptions.

[App Name] uses native Apple APIs to solve [problem], preserving privacy and running entirely on-device.

No network requests for processing, completely private. Would love your feedback on the UX!
[App Store Link]
```

---

## 3B. Developer & Tech Community Playbooks (LinkedIn, DOU, dev.ua, GitHub)

When marketing as software engineers to other software engineers, never use consumer marketing speak or generic claims. The winning angle is **engineering transparency, technical hurdles, architecture choices, and honest founder journey**.

### 1. LinkedIn: The Founder & Engineering Craft Story
- **Audience**: Peers, engineering leaders, tech early adopters.
- **Narrative Archetype**: *"Why I built a native iOS utility on Swift 6 with zero backend"*.
- **Key Talking Points**:
  - Almost every "phone cleaner" in the App Store is a scam: they upload media to remote servers, compress with lossy web-grade codecs, and charge predatory $6.99/week subscriptions.
  - Engineering challenge: How to achieve hardware-accelerated 4K HEVC compression locally using VideoToolbox and Metal without blowing through iOS memory limits (OOM jetsam).
  - Preserving 10-bit HDR Gain Maps and lossless audio passthrough bit-for-bit.
  - Transparent business model: free trial month, localized one-time/monthly pricing.
- **Attribution**: Use `?ct=linkedin_founder_post`.

### 2. DOU.ua: Community Forum & Engineering Blog
- **Audience**: Ukrainian developer community (highly critical, tech-savvy, strong iOS representation).
- **Formats**:
  1. **DOU Forum (Розділ «Свій бізнес / Стартапи» або «iOS»)**:
     - Title: *"Створив Compresso — офлайн-компресор відео та фото для iOS на Swift 6: як це влаштовано зсередини"*.
     - Focus: Open discussion of architectural choices, SwiftData challenges, memory management, App Store Review battles. Ask for feedback on UX and edge-case device performance.
  2. **DOU Tech Article / Blog**:
     - Deep dive: *"Як стискати 4K відео на iOS без хмари: VideoToolbox, оптимізація пам'яті та строга паралельність у Swift 6"*.
- **Attribution**: Use `?ct=dou_ua`.

### 3. dev.ua: Pet-Project & Startup Spotlight
- **Audience**: Broader Ukrainian tech ecosystem (engineers, PMs, tech journalists).
- **Format**: Editorial pitch or blog submission to dev.ua's regular *"Стартапи / Pet-проєкти"* column.
- **Angle**: *"Український iOS-розробник створив утиліту для збереження пам'яті iPhone без підписок за $7/тиждень"*. Emphasize independence, privacy, on-device execution, and European launch.
- **Attribution**: Use `?ct=dev_ua`.

### 4. The Unobvious Play: GitHub Companion Benchmark Repository
- **Concept**: Publish a clean, standalone open-source repository: `ios-video-compression-benchmarks`.
- **Content**:
  - Benchmark code comparing `AVAssetExportSession` vs raw `VTCompressionSession` (VideoToolbox).
  - Implementation sample of Laplacian variance edge detection for photo sharpness scoring.
  - Memory usage and bitrate charts.
  - Header badge: *"Used in production by [Compresso on the App Store](https://apps.apple.com/app/id6790447224?ct=github_benchmarks)"*.
- **Why it works**: Engineers searching Google/GitHub for iOS video compression techniques discover the repo, star it, and download the App Store app as proof-of-concept. Creates perpetual, high-trust organic referral traffic.

### 5. Telegram & Slack iOS Communities
- Channels: *iOS Dev UA*, *CocoaHeads Ukraine*, *iOS Developers Slack* (channel `#showcase`).
- Tone: Humble peer review request: *"Привіт усім! Написав на чистому Swift 6 утиліту для локального стиснення відео. Буду дуже вдячний за тест на ваших медіатеках і фідбек по UX/перформансу"*.


---

## 4. Apple Search Ads (ASA): Beachhead Strategy

Do not spend high bids on broad keywords in the US ($2.50+ CPT). Instead:
- **Markets**: Beachhead locales where your app is already ranking in the Top 10–20:
  - Localized beachhead market A
  - Localized beachhead market B
  - Localized beachhead market C
- **Type**: Exact Match only (no Search Match).
- **Target CPT**: $0.15 – $0.35.
- **Budget**: $15–$25 per campaign to jumpstart download velocity for the App Store algorithm.

---

## 5. Channel Hypothesis Lifecycle (`C001...`)

Every campaign action must have:
1. **Monotonic ID**: `C001`, `C002`, `C003`...
2. **Channel & Type**: `reddit_comment`, `reddit_post`, `threads`, `x_post`, `asa`.
3. **Target Community / Link**: Subreddit URL or target thread search link.
4. **Attribution Campaign Token (`ct`)**: Recorded in `marketing/campaigns.csv`.
5. **Exact Ready-to-Post Copy**: Provided in English and Ukrainian.
6. **Measurable Prediction**: (e.g. 25 clicks, 5 downloads within 7 days).
7. **Kill Criterion**: (e.g. < 3 clicks in 7 days or post removed).

---

## 6. Anti-Collision & Deduplication Protocol (Memory Guard)

The skill must **never re-propose something already queued, live, or recently executed**.

### 1. Mandatory Pre-Flight History Check
Before proposing any external traffic action or running `campaign_link.py`:
- The skill reads `marketing/STATE.md` (section `Active Channel Hypotheses`) and inspects `marketing/hypotheses/C*.md`.
- Or runs `python3 $SKILL_DIR/scripts/campaign_link.py --list`.
- If a vector is already queued (e.g., `C001` for Reddit Contextual Help or `C002` for `r/iosapps`), the skill reminds the user that this action is **already planned and waiting for execution**, instead of generating a duplicate proposal.

### 2. Strict Community Cooldowns
- **r/iosapps**: Enforce a mandatory **30-day cooldown** between posts from the same developer. If a hypothesis targeting `r/iosapps` is queued or went live < 30 days ago, refuse to generate a new post for `r/iosapps` and report days remaining.
- **General Subreddit Comments**: Max 2–3 comments/week across different subreddits. Do not propose spamming multiple comments into the same thread.

### 3. Campaign Token Uniqueness
Every `campaign_token` (`ct`) is strictly unique across all time. Reusing a token cross-contaminates App Store Connect attribution data and is rejected by `campaign_link.py`.

---

## 7. Directory & Launchpad Indexing Strategy (94 Platforms)

For off-store web directory submissions, see the dedicated reference:
- **[directory-launch-strategy.md](directory-launch-strategy.md)** — Master matrix of 94 startup directories, launchpads, and product indexing platforms evaluated by Domain Rating (DR), relevance to Compresso, copy angles, and a 3-wave execution plan.


