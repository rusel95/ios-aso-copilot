# Directory Launch Strategy & Rolling Momentum Matrix (94 Platforms)

A rigorous, market-researched evaluation of 94 startup directories, launchpads, and product indexing platforms for **Compresso** (iOS On-Device Media Cleaner & Compressor).

---

## 1. Executive Summary & Strategic Realism: The "Rolling Momentum" Model

The original marketing roadmap hypothesized a "Momentum Blast" (simultaneous 24-hour push across all channels). Practical analysis of platform-specific review queues, moderation rules, and App Store attribution reveals that a 24-hour blast is counterproductive:
1. **Maker Attention Bottleneck**: Product Hunt, Hacker News, and Reddit all require the solo founder to be actively answering comments, debugging edge cases, and replying in real time. Running them simultaneously forces high-value channels to compete for your attention.
2. **Review Queue Realities**: Directories have radically different review pipelines. AlternativeTo and Uneed free backlogs take weeks or months. BetaList requires "recently launched" status. Syncing them to a single day is technically impossible.
3. **The Funnel-Optimization Compounding Loop**: Launching sequentially allows early waves (Reddit/HN) to surface crashes, paywall friction, and onboarding drop-offs *before* burning the massive Product Hunt day.

> **The New Momentum Law**:
> **Momentum is not simultaneity across channels. Momentum is a series of focused, local peaks with cumulative social proof and funnel optimization between waves.**

```text
Attention / Installs
       ╭────╮
       │ PH │          ╭──────╮
 ╭─────╯    ╰──╮ ╭─────╯      ╰───╮
 │  Reddit/HN  │ │   Peerlist     │
─┴─────────────┴─┴────────────────┴─────── directories (background) ───>
Day 0          3 6                10      14
```

---

## 2. Directory Mechanics & Reality Check

### A. The Discovery Engines (Real Humans Searching) vs SEO Backlinks
- **Google Link Spam Reality**: Google's Search Essentials explicitly classify mass directory/bookmark listings as link spam. Domain Rating (DR) is an Ahrefs commercial metric, not Google PageRank.
- **The True Objective**: We do not submit to build "DR 80 link authority". We submit to **be indexed in human discovery databases** where users with acute pain points search for alternatives (AlternativeTo, SaaSHub, Product Hunt).

### B. Platform Queue & Moderation Specifics
- **AlternativeTo (DR 80)**: Free queue backlog is 1–2 months. Priority review ($5) is 1–2 days. **Strategy**: Submit Day 0 immediately so the listing is in review. Do not wait for launch week.
- **BetaList (DR 76)**: Strictly requires unreleased, private beta, or *recently launched* apps. Submitting after weeks of public traction leads to rejection. **Strategy**: Submit Day 0 immediately.
- **Uneed (DR 75)**: Runs daily launch slots (30/day), but free queue stretches up to 5 months. **Strategy**: Submit Day 0 for the free backlog.
- **Peerlist Launchpad (DR 77)**: Runs on a **weekly cycle starting every Monday**. **Strategy**: Do not collide with Product Hunt; dedicate a separate Monday launch to capture the Peerlist weekly leaderboard.
- **Hacker News (Show HN, DR 91)**: Algorithmic front page based on points/gravity `points / (time + 2)^1.8`. Forbids vote asking. Requires technical, humble narrative (Swift 6, VideoToolbox, Metal, zero cloud).
- **Product Hunt (DR 91)**: 24-hour cycle (00:01 PST – 23:59 PST). Requires full-day dedication. Launch only *after* initial Reddit/HN user feedback has calibrated the onboarding and paywall.

---

## 3. The 4-Tier Strategic Classification

```
┌────────────────────────────────────────────────────────────────────────┐
│ TIER 1: CORE VALUE ENGINES (10 Platforms)                              │
│ High intent, direct consumer downloads, community engagement.          │
│ Action: Dedicated launch days or immediate queue submissions.          │
├────────────────────────────────────────────────────────────────────────┤
│ TIER 2: HIGH-AUTHORITY BACKLINK BUILDERS (22 Platforms)                │
│ DR 70+, software/startup general directories.                          │
│ Action: Standardized copy-paste submission for SEO domain rating.      │
├────────────────────────────────────────────────────────────────────────┤
│ TIER 3: ALGORITHMIC / AI DIRECTORIES (25 Platforms)                    │
│ Requires repositioning: "Smart On-Device Perceptual Compression".      │
│ Action: Submit only if 100% free and accepts visual utilities.         │
├────────────────────────────────────────────────────────────────────────┤
│ TIER 4: MISALIGNED OR LOW-VALUE (37 Platforms)                         │
│ B2B SaaS, developer APIs, agency lists, low-DR (<45) link farms.       │
│ Action: SKIP or lowest priority — do not waste time.                   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Tier 1: Core Value Engines (Top 10 — Detailed Strategy)

| # | Platform | DR | Queue Type | Strategy & Actionable Playbook |
|---|---|---|---|---|
| 1 | **AlternativeTo** | 80 | Long Queue (Weeks/Months) | **Submit Day 0 immediately.** List Compresso as an alternative to CleanMyPhone, Gemini Photos, and Smart Cleaner. Emphasize: *100% on-device, zero cloud, private, one-time/monthly*. (Optional: $5 priority review if immediate visibility desired). |
| 2 | **BetaList** | 76 | Time-Sensitive (New Apps Only) | **Submit Day 0 immediately.** Requires "recently launched" status. Free queue. Highlights polished iOS mobile utilities to early tech adopters. |
| 3 | **Uneed** | 75 | Long Queue (Months) | **Submit Day 0 immediately.** Put into free queue. Do not try to sync with launch day. |
| 4 | **Hacker News (Show HN)** | 91 | Real-time (Day 4–5) | **Dedicated Day 1 spike.** Title: *"Show HN: Compresso – Swift 6, hardware-accelerated on-device media compressor for iOS, zero cloud"*. Focus on technical depth: VideoToolbox, Laplacian edge preservation, 10-bit HEVC, zero analytics on photos. Be active in comments for 8 hours. |
| 5 | **Product Hunt** | 91 | 24h Event (Week 2, Day 8–10) | **The Main Momentum Day.** Launch 00:01 PST. Mobilize network, share maker first comment. Run *after* fixing initial bugs reported from HN/Reddit. |
| 6 | **Peerlist Launchpad** | 77 | Weekly (Week 2, Monday) | **Dedicated Weekly Spike.** Starts Monday. Submit to Peerlist Project Spotlight. Focus on UX & interaction design: split-screen slider, fluid card swiping, haptics. |
| 7 | **SaaSHub** | 80 | Evergreen | Submit Day 1. Automatically creates comparison tables (Compresso vs CleanMyPhone). |
| 8 | **Indie Hackers** | 81 | Community Post | Post during Week 1: *"How I built an on-device iOS video compressor with Swift 6"*. Great for founder credibility and early reviews. |
| 9 | **Fazier** | 83 | Daily Competition | Submit Week 2 alongside Peerlist. Growing PH alternative with high authority. |
| 10 | **Microlaunch** | 64 | Weekly/Monthly | Active indie community. Submit Week 2. Good for sustained discovery. |

---

## 5. Tier 2: General Startup & Discovery Directories (22 Platforms, DR 70+)

Submit in a single 90-minute batch during Week 1 to establish Compresso's web footprint:

| # | Platform | DR | Notes |
|---|---|---|---|
| 11 | **Startup Fame** | 83 | DR 83. Standard 100-word blurb and screenshot. |
| 12 | **Findly Tools** | 81 | DR 81. Curated tool discovery platform. Free standard submission. |
| 13 | **Smol Launch** | 74 | DR 74. Clean micro-launchpad. Submit via free tier for daily spotlight. |
| 14 | **LaunchIgniter** | 74 | DR 74. Startup launch aggregator. Quick submit. |
| 15 | **StartupBase** | 73 | DR 73. Early-stage product community. |
| 16 | **Tiny Launch** | 73 | DR 73. Lightweight directory for indie apps. |
| 17 | **Aura++** | 73 | DR 73. Directory of modern web and mobile utilities. |
| 18 | **Software World** | 73 | DR 73. Add under "Mobile Utilities / Multimedia". |
| 19 | **Neeed Directory** | 73 | DR 73. Design-centric tool directory. High aesthetic bar. |
| 20 | **Startup Fast** | 72 | DR 72. Startup index. Standard submission. |
| 21 | **Open Launch** | 72 | DR 72. Open submission launchpad. |
| 22 | **FoundrList** | 72 | DR 72. Directory for founders and creators. |
| 23 | **StartupBlink** | 72 | DR 72. Global startup ecosystem map (list under Ukraine/Kyiv ecosystem). |
| 24 | **TrustMRR** | 71 | DR 71. Bootstrapped indie tech directory. |
| 25 | **Tiny Startups** | 71 | DR 71. Directory of bootstrapped indie tools. |
| 26 | **SideProjectors** | 71 | DR 71. Marketplace & community for side projects. |
| 27 | **OpenHunts** | 71 | DR 71. Community upvote directory. |
| 28 | **Scroll Launch** | 70 | DR 70. Modern launch feed. |
| 29 | **ToolFame** | 75 | DR 75. Tool discovery directory. |
| 30 | **PeerPush** | 75 | DR 75. Community directory and upvoting site. |
| 31 | **PitchWall** | 69 | DR 69. Startup showcase cards. |
| 32 | **Startup Stash** | 65 | DR 65. Directory of resources and tools. |

---

## 6. Tier 3: Algorithmic & AI Aggregators (25 Platforms — Free Queue Only)

**Angle required**: Reposition from "cleaner" to **"Smart Algorithmic Visual Compression & On-Device Vision Processing"** (Laplacian texture preservation, adaptive bitrates, perceptual fidelity).

| # | Platform | DR | Positioning Angle |
|---|---|---|---|
| 33 | **There's an AI for That** | 77 | Tag: *AI Photo Compression / Media Optimization*. Highlight smart edge detection. |
| 34 | **Toolify** | 73 | Category: *Image Processing / Video Tools*. Free queue only. |
| 35 | **Futurepedia** | 72 | Smart on-device visual storage optimization. |
| 36 | **Future Tools** | 69 | Curated by Matt Wolfe. Free queue only. |
| 37 | **Dang AI** | 82 | High authority directory. Submit free if available. |
| 38 | **Twelve Tools** | 82 | Media optimization tool category. |
| 39 | **Turbo0** | 80 | AI & smart tool search engine. |
| 40 | **Tool Pilot** | 78 | Smart media utility. |
| 41 | **Show Me Best AI** | 76 | Media Tools category. |
| 42 | **Open Tools** | 69 | Open AI & utility directory. |
| 43 | **NxGn Tools** | 69 | Next-gen tool directory. |
| 44 | **Versily** | 68 | Automated visual tools. |
| 45 | **AI Tools (aitools.inc)**| 67 | Media processing category. |
| 46 | **UNO Directory** | 66 | Utility apps. |
| 47 | **Top AI Tools** | 64 | Media compression category. |
| 48 | **Huzzler** | 64 | Tech tools directory. |
| 49 | **Dev Hunt** | 63 | Pitch the Swift 6 / Metal / VideoToolbox architecture. |
| 50 | **Startup Ranking** | 61 | Global ranking index. |
| 51 | **AIxploria** | 56 | French/international directory. |
| 52 | **AI Tool Directory** | 52 | Directory backlink. |
| 53 | **Euro Alternative** | 38 | **European Privacy Alternative** to US cloud photo hoarders. 100% on-device, GDPR compliant. |

---

## 7. Tier 4: Misaligned or Low-Value Platforms (SKIP)

Do not spend time on these 37 platforms:
- **Clutch (DR 91)**: Strictly for B2B IT agencies and software dev consultancies.
- **Public APIs (DR 46)**: For public developer APIs. Compresso has no public API.
- **GetApp (DR 85)**, **Software Suggest (DR 77)**, **SaaS Genius (DR 57)**: B2B enterprise software (CRM/ERP).
- **SourceForge (DR 92)** & **OpenAlternative (DR 52)**: Open-source desktop software focus.
- **AI for Developers (DR 21)** & **Dev Resources (DR 40)**: Developer SDKs.
- **Low DR (<45) or Dead Link Farms**: SEO Wins, Startup Buffer, Toolfolio, TinyHunt, Altern, Resource FYI, AI Valley, AI Tools Club, AI Parabellum, MakerHunt, SideHunt, Firsto, Daily Pings, Micro SaaS Examples, Build Voyage, Product Burst, Try Launch, Find Your SaaS, SaaS Hunt, Startup Listing, Promote Project, Idea Kiln, IndieHub, Appscribed, SEOFAI, Powerusers AI, ShipBoost, Launch Vault.

---

## 8. Attribution Protocol: App Store Campaign Links (`ct`)

Never send untracked external traffic to a raw App Store link. Generate separate campaign tokens using `scripts/campaign_link.py`:

```bash
# Example campaign token generation:
python3 .agents/skills/ios-marketing-ops/scripts/campaign_link.py \
  --channel reddit \
  --campaign-name "reddit_sideproject" \
  --destination "https://apps.apple.com/app/id6790447224"
```

### Dedicated Tokens for the Rolling Launch:
- `?ct=ph_launch` → Product Hunt
- `?ct=hn_show` → Hacker News Show HN
- `?ct=reddit_iosapps` → r/iosapps
- `?ct=reddit_sideproject` → r/SideProject
- `?ct=peerlist` → Peerlist Launchpad
- `?ct=alternativeto` → AlternativeTo

In **App Store Connect Analytics → Acquisition → Campaigns**, evaluate:
`Channel → Impressions → Product Page Views → Downloads → Sessions/User → Paywall Views → Trial Starts`.

---

## 9. The 14-Day Rolling Momentum Schedule

```text
Week 1: Foundations, Queues & First Spikes
├── Day 0: Submit AlternativeTo, BetaList, Uneed (start their long review queues)
├── Day 1-2: Batch submit Tier-2 directories (22 sites, 90 mins)
├── Day 3: Reddit Test #1 (r/SideProject or r/ios) — monitor crash reports & first UX friction
├── Day 4-5: Hacker News Show HN (Dedicated Spike) — technical discussion, founder active in thread
└── Day 6: Analyze HN/Reddit telemetry in GA4 + ASC. Patch any onboarding/paywall blocker.

Week 2: The Main Event & Design Showcase
├── Monday (Day 8): Peerlist Launchpad (Dedicated Weekly Spike)
├── Tuesday or Thursday (Day 9/11): PRODUCT HUNT LAUNCH (The 24h Momentum Day)
│   └── Mobilize network, update X/Threads, answer every comment live.
├── Day 12: Reddit Test #2 (r/iosapps with mandatory ABC format & 30-day cooldown)
└── Day 14: Comprehensive Funnel Audit across all `ct` tokens.
```
