# Storefront Conversion Funnel & Analytics Engine

Marketing in the App Store is fundamentally a multi-stage conversion funnel. While keyword rankings (ASO) drive top-of-funnel **Impressions**, the commercial and organic success of an app is determined by **how effectively impressions convert into product page views, downloads, and paying subscribers**.

This document defines conversion benchmarks, leak diagnostic algorithms, territory-level triage rules, and visual reporting specifications for `ios-marketing-ops`.

---

## 1. The 4-Stage Storefront Conversion Funnel

```
[ Stage 1: Search Impressions ]
         │
         │  Tap-Through Rate (TTR / CTR) = Page Views / Impressions
         ▼
[ Stage 2: Product Page Views ]
         │
         │  Page Conversion Rate (Page CVR) = Downloads / Page Views
         ▼
[ Stage 3: First-Time Downloads ]
         │
         │  Paywall Conversion Rate (Paywall CVR) = Trial Starts / First Opens
         ▼
[ Stage 4: Subscriptions & Trials ]
```

### Key Metrics Definition
| Metric | Calculation | What it measures |
|---|---|---|
| **TTR (Tap-Through Rate)** | `product_page_views / impressions` | Search card appeal: Icon, Title, Subtitle, Rating, First 3 screenshots. |
| **Page CVR** | `downloads / product_page_views` | Full page persuasion: Screenshots 4-10, Description, App Preview video, Reviews. |
| **Direct Download Rate** | `direct_downloads / impressions` | Users who tap "Get" directly in search results without opening the product page. |
| **Overall ASO CVR** | `total_downloads / impressions` | End-to-end storefront conversion efficiency. |
| **Paywall CVR** | `trial_starts / first_opens` | In-app monetization efficiency: Paywall UX, pricing, trial terms, localized copy. |

---

## 2. Category Benchmarks (Health & Fitness, Utilities, Audio)

Derived from Apple App Store Peer Group Benchmarks and industry conversion standards:

| Metric | 🔴 Critical / Major Leak | 🟡 Baseline / Fair | 🟢 Healthy / Top Quartile | Primary Root Cause if Low |
|---|---|---|---|---|
| **TTR (Tap Rate)** | `< 1.8%` | `1.8% – 4.2%` | `> 4.2%` (top 10%: `> 6.5%`) | Weak icon contrast; cluttered first 3 screenshots; title/subtitle doesn't match search intent. |
| **Page CVR** | `< 18.0%` | `18.0% – 32.0%` | `> 32.0%` (top 10%: `> 42.0%`) | Untranslated screenshots; low local rating or 0 reviews; app size > 200MB; confusing description. |
| **Overall ASO CVR** | `< 1.2%` | `1.2% – 3.0%` | `> 3.0%` (top 10%: `> 4.5%`) | Combined search-card and product-page failure. |
| **Paywall CVR** | `< 4.0%` | `4.0% – 9.0%` | `> 9.0%` (top 10%: `> 14.0%`) | Untranslated paywall strings; aggressive hard paywall; pricing misaligned with local purchasing power (PPP). |

---

## 3. Automated Diagnostic Rules & Actionable Levers

When evaluating weekly metrics or hypothesis outcomes, evaluate these rules in order to identify the **Single Biggest Conversion Bottleneck**:

### Rule 1: Top-of-Funnel Search Card Leak (`TTR < 1.8%`)
- **Diagnosis**: 🔴 High visibility, low curiosity. Users see the app in search results but skip it.
- **Root Causes**:
  1. The app icon looks generic or lacks contrast against dark/light mode search backgrounds.
  2. The first 3 screenshots fail to convey the core value proposition in < 2 seconds.
  3. Star rating is below 4.2 or shows 0 reviews in that storefront.
- **Actionable Lever**:
  - Launch an App Store Product Page Optimization (PPO) test on App Icon.
  - Redesign Screenshot #1 with a large, legible 3-word hook (e.g. *"Fall Asleep Fast"* / *"Засинай миттєво"*).
  - Check keyword intent: are impressions coming from broad, misaligned queries?

### Rule 2: Product Page Drop-off (`Page CVR < 18.0%`)
- **Diagnosis**: 🔴 High curiosity, low commitment. Users open the full page but bounce.
- **Root Causes**:
  1. English screenshots shown in a non-English storefront (e.g. English UI in Germany, Norway, Japan).
  2. The review section contains negative, unaddressed reviews on the top fold.
  3. Description is a wall of text without clear feature bullets.
- **Actionable Lever**:
  - Localize screenshot captions and UI framing for that specific storefront.
  - Reply to negative reviews via App Store Connect.
  - Punch up the first 3 lines of the description before the "More" cutoff.

### Rule 3: Territory / Storefront Isolation Mismatch
- **Diagnosis**: 🔴 High impressions in a country (> 200/mo) but 0 downloads.
- **Root Causes**:
  1. Country uses English fallback for metadata or screenshots.
  2. Prohibitive US-dollar pricing without PPP adjustments.
- **Actionable Lever**:
  - Localize storefront metadata and screenshots.
  - Implement localized PPP pricing via `asc-ppp-pricing`.

### Rule 4: Monetization Paywall Leak (`Paywall CVR < 4.0%`)
- **Diagnosis**: 🔴 Good organic acquisition, broken revenue bridge. Users install but bounce at paywall.
- **Root Causes**:
  1. Untranslated paywall strings (e.g. English "7-day free trial" in a localized build).
  2. Missing free trial or unclear cancellation terms.
  3. Missing monthly equivalent anchor (e.g. not showing "zsh.83/mo equivalent" next to Annual).
- **Actionable Lever**:
  - Audit `Localizable.xcstrings` for missing keys across all supported languages.
  - Highlight "7-day free trial" and clear trial cancellation policy.

---

## 4. Visual Funnel Rendering Specification

In CLI outputs, markdown reports, and skill summaries, render the conversion funnel using this structured format:

```text
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 🎯 STOREFRONT CONVERSION FUNNEL (Period: [Week / 30-Day])                             │
├──────────────────────────────┬──────────┬──────────┬─────────────┬─────────────────────┤
│ Funnel Stage                 │   Volume │ Conv Rate│  Benchmark  │ Health Status       │
├──────────────────────────────┼──────────┼──────────┼─────────────┼─────────────────────┤
│ 1. Search Impressions        │   12,450 │   100.0% │      —      │                     │
│    │ [████████████████████]  │          │          │             │                     │
│    ▼ Tap-Through Rate (TTR)  │          │     3.3% │  1.8 – 4.2% │ 🟡 FAIR             │
│ 2. Product Page Views        │      410 │     3.3% │      —      │                     │
│    │ [███░░░░░░░░░░░░░░░░░]  │          │          │             │                     │
│    ▼ Page Conversion (CVR)   │          │    28.0% │ 18.0 – 32.0%│ 🟢 HEALTHY          │
│ 3. First-Time Downloads      │      115 │    28.0% │      —      │                     │
│    │ [█░░░░░░░░░░░░░░░░░░░]  │          │          │             │                     │
│    │ (Overall ASO CVR: 0.9%) │          │     0.9% │  1.2 – 3.0% │ 🔴 LEAK (Top-Funnel)│
│    ▼ Paywall Conversion      │          │     9.6% │  4.0 – 9.0% │ 🟢 HEALTHY          │
│ 4. Trial Starts & Subs       │       11 │     9.6% │      —      │                     │
└──────────────────────────────┴──────────┴──────────┴─────────────┴─────────────────────┘

🔍 FUNNEL BOTTLENECK DIAGNOSIS:
  • Primary Bottleneck: Top-of-Funnel Leak (Overall CVR 0.9% < 1.2% baseline).
  • Recommended Lever: A/B test App Icon and first 3 screenshots via App Store PPO.
```
