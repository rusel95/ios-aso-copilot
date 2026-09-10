# Storefront Expansion & iOS Localization Playbook

Localization is not a mere translation task — it is a primary driver of international organic growth and subscription revenue. In utility and consumer subscription apps, expanding into an affluent, under-served storefront with 100% native in-app localization, zero-waste App Store metadata, and localized screenshot captions regularly outperforms domestic keyword tweaking by an order of magnitude.

Launching storefront metadata without complete in-app localization causes severe onboarding drop-off, negative 1-star reviews, and destroyed conversion. Conversely, translating in-app strings without optimizing App Store Connect metadata leaves the app invisible to local organic search.

This playbook unifies both into an **end-to-end 5-step storefront expansion pipeline**.

---

## 1. The 5-Step Unified Storefront Expansion Pipeline

```
[ Step 1: Market Selection & Yield Analysis ]
  ↳ GDP per capita, subscription ARPU/net, iPhone penetration, keyword search vacancy.
       │
[ Step 2: In-App String Catalog (.xcstrings) & Pluralization ]
  ↳ 100% string coverage, native Apple HIG vocabulary, strict CLDR plural forms, Xcode knownRegions.
       │
[ Step 3: Zero-Waste App Store Metadata ]
  ↳ Title (≤30), Subtitle (≤30), Keywords (≤100) — 0 duplicate tokens, localized Description & What's New.
       │
[ Step 4: Screenshot Framing & Captions ]
  ↳ Localized card headlines, subs, and handwritten annotations in card.html / copy.md.
       │
[ Step 5: Launch Hypothesis & Rank Tracking ]
  ↳ Create H0xx hypothesis, register local query basket in ranks.csv, enforce 21-day kill criteria.
```

---

## 2. Storefront Economics & Prioritization

Not all App Store markets yield equal return. Prioritize storefront expansion using four concrete criteria:

1. **Net Revenue per Subscriber**: High-GDP Eurozone and tier-1 markets (e.g. Portugal netting $29.38/sub vs Brazil $12.73/sub) offer vastly superior ROI even on moderate download volumes.
2. **Local Dialect vs Regional Fallback Sensitivity**: Users in countries like Portugal (`pt-PT`), Austria (`de-AT`), French Canada (`fr-CA`), and Mexico (`es-MX`) show high drop-off when served fallback translations (`pt-BR`, `de-DE`, `fr-FR`, `es-ES`) due to vocabulary and cultural disconnects.
3. **Organic Competitor Vacancy**: Audit local search hints using `itunes-search-api`. If competitors in the target country only offer English or automated fallback translations, a 100% native localized title and app will immediately seize top-5 organic rankings.
4. **Keyword Token Economy**: In agglutinative and compound languages (German, Finnish, Hungarian), keyword tokens consume characters rapidly; in CJK languages, each character carries high semantic density without spaces.

---

## 3. In-App String Catalogs (`.xcstrings`) & Apple HIG Standards

Compresso uses Xcode 15+ String Catalogs (`.xcstrings`). When adding a new locale:

### Required Actions
1. **Catalog Completeness**: All user-facing keys must have a translated entry. Never leave empty values.
2. **CLDR Plural Rules**: Provide all mandatory plural categories for the language family (see Section 4).
3. **Xcode Project Configuration**: Register the locale identifier in `knownRegions` in `project.pbxproj`.
4. **Format Specifiers**: Positional specifiers (`%1$@`, `%2$@`, `%1$lld`) must match across all languages to prevent crashes or reordering bugs.
5. **No Hardcoded Values**:
   - Dates: Use `Date.formatted()` or system styles (`.dateStyle`, `.timeStyle`), never custom `dateFormat` strings.
   - Numbers & Currencies: Use `NumberFormatter` or `.formatted(.currency(code:))`.
   - Layout: Use `leading`/`trailing` constraints and `.natural` text alignment (critical for RTL languages like Arabic and Hebrew).

---

## 4. Complete CLDR Pluralization Rules Matrix

AI assistants systematically default to English `one` + `other` rules, causing broken grammar, missing keys, and crashes in non-English locales. String Catalogs require exact CLDR plural category coverage:

| Category Pattern | Locales | Required Plural Keys | Example & Verification Counts |
|---|---|---|---|
| **1-form** (Other only) | `ja`, `ko`, `zh-Hans`, `zh-Hant`, `tr`, `th`, `vi`, `id` | `other` | Count has no grammatical inflection: `1 foto`, `5 foto`. Counts: `[0, 1, 2, 5, 10]` |
| **2-form** (Standard) | `en`, `de`, `fr`, `es`, `it`, `pt-PT`, `nl`, `da`, `sv`, `no`, `fi`, `el`, `hu` | `one`, `other` | `one` (n = 1), `other` (n ≠ 1). *Note: French (`fr`) and Brazilian Portuguese (`pt-BR`) also treat 0 as `one` in spoken language, but standard String Catalogs accept `one`/`other`.* |
| **4-form Slavic** | `ru`, `uk` | `one`, `few`, `many`, `other` | `one`: 1, 21, 31... (ends in 1, except 11); `few`: 2-4, 22-24...; `many`: 0, 5-20, 25-30...; `other`: fractions. |
| **4-form West Slavic** | `pl` | `one`, `few`, `many`, `other` | `one`: 1; `few`: 2-4, 22-24 (ends in 2-4, except 12-14); `many`: 0, 5-21, 25-31; `other`: fractions. *(Different from Russian!)* |
| **4-form Czech/Slovak** | `cs`, `sk` | `one`, `few`, `many`, `other` | `one`: 1; `few`: 2-4; `many`: fractions; `other`: 0, 5+. |
| **6-form Semitic** | `ar` | `zero`, `one`, `two`, `few`, `many`, `other` | Full 6-category inflection. Missing any category causes runtime key fallback in Arabic. |

---

## 5. Top 30 Localization Anti-Patterns & AI Failure Traps

Every localized PR and string update must be audited against these 30 patterns:

1. **Hardcoded User-Facing Strings**: String literals directly in UI without `String(localized:)` or `LocalizedStringKey`.
2. **String Concatenation**: `"Found " + count + " files"` instead of `String(localized: "found_files_count")`. Word order differs across languages.
3. **Missing Positional Specifiers**: Using `%@ %@` instead of `%1$@ %2$@`. Translators must be able to swap argument order.
4. **Missing Slavic / Semitic Plural Categories**: Providing only `one` and `other` for `ru`, `uk`, `pl`, `cs`, `sk`, or `ar`.
5. **Copying Polish Plural Rules from Russian**: Polish treats 21, 31, 41 as `many`, whereas Russian treats them as `one`.
6. **Hardcoded Left / Right Alignment**: Using `.leading` / `.trailing` is mandatory; `.left` / `.right` shatters Arabic/Hebrew RTL layouts.
7. **Custom Date Formatting**: `yyyy-MM-dd` in user-facing UI breaks for non-Gregorian calendars (Buddhist calendar in Thailand, Hijri in Saudi Arabia).
8. **Currency String Interpolation**: `"$\(price)"` instead of `price.formatted(.currency(code: "USD"))`.
9. **Missing `knownRegions`**: Adding `.xcstrings` translations without registering the locale in `project.pbxproj`.
10. **Untranslated Accessibility Elements**: Leaving accessibility labels and hints in English while the visual UI is localized.
11. **Fixed-Width Containers**: Localized German, Finnish, or Russian text is 30–50% longer than English and gets truncated if frames are rigid.
12. **Duplicate ASO Keywords**: Repeating Title or Subtitle words in the 100-character Keywords field.
13. **Spaces After Commas in Keywords**: `foto, video, limpar` wastes 2 valuable characters out of 100. Always use `foto,video,limpar`.
14. **Unlocalized Screenshot Captions**: Submitting localized metadata with English screenshot cards.
15. **Untranslated Release Notes**: Leaving *What's New* in English for localized storefront versions.
16. **Missing CLDR Verification Set**: Failing to test plural strings against `[0, 1, 2, 3, 5, 11, 21, 22, 25, 100]`.
17. **Using Brazilian Portuguese in Portugal**: Words like *arquivo* (should be *ficheiro*), *tela* (*ecrã*), *excluir* (*eliminar*), *salvar* (*guardar*).
18. **Using Castilian Spanish in Latin America**: Ignoring local terms in Mexico, Argentina, Colombia.
19. **Ambiguous Short Keys**: Using "Back" for both navigation button and spine/body context.
20. **Missing Translator Comments**: No context explaining what `%1$@` represents.
21. **Unescaped Quotes in Metadata JSON**: Breaking JSON parsing with raw unescaped double quotes.
22. **Exceeding App Store 30-Character Limits**: Title or Subtitle with 31+ characters will be rejected at upload.
23. **Exceeding 100-Character Keyword Limit**: Keywords field with 101+ characters fails validation.
24. **Promotional Text Over 170 Characters**: Apple rejects promotional text exceeding 170 UTF-8 characters.
25. **Untranslated In-App Purchase / Paywall Titles**: Showing English subscription terms inside a localized app.
26. **Assuming 1 Month = 30 Days in UI**: Formatting durations without `DateComponentsFormatter`.
27. **Capitalization Rules Violation**: German capitalizes all nouns; French and Spanish only capitalize sentence starts.
28. **Punctuation Style Inconsistency**: French requires a non-breaking space before colons (` : `), Spanish requires inverted marks (`¿`, `¡`).
29. **Assuming Search Popularity in Small Markets Equals Big Traffic**: A score of 40 in Ukraine is a fraction of the search volume of 40 in the US.
30. **Unchecked House Rules**: Skipping `./scripts/verify-house-rules.sh` before committing localized strings.

---

## 6. Zero-Waste ASO Metadata Protocol

When generating metadata for a new locale:

1. **Title (≤ 30 characters)**:
   - Pattern: `Compresso: <Primary Local High-Intent Keyword Phrase>`
   - Must contain the brand and the #1 search query for the market.
2. **Subtitle (≤ 30 characters)**:
   - Pattern: `<Secondary Benefit / Action Phrase>`
   - **Zero Token Overlap**: Must NOT repeat any root token from the Title.
3. **Keywords (≤ 100 characters)**:
   - Zero spaces after commas (`term1,term2,term3`).
   - Must NOT contain any token already present in Title or Subtitle (Apple indexes Title + Subtitle + Keywords collectively).
   - Must NOT contain stop words, punctuation, or generic filler.
   - Maximize character utilization to 95–100 / 100.
4. **Description (≤ 4000 characters)**:
   - Structured with localized headings, bullet points, honest on-device privacy guarantees, and Terms of Use URL.
5. **Promotional Text (≤ 170 characters)**:
   - Short, punchy hook editable between App Store releases without a new binary.
6. **What's New (≤ 4000 characters)**:
   - Explicitly highlight full native language support for the new market.

---

## 7. Automated Storefront Localization Tooling

Use `scripts/localization_tool.py` to audit and scaffold storefront expansions:

```bash
# Audit repository localization coverage across metadata, xcstrings, and Xcode
python3 "$SKILL_DIR/scripts/localization_tool.py" --store "$STORE" --project "." audit

# Scaffold a new market expansion (metadata, hypothesis, screenshot copy)
python3 "$SKILL_DIR/scripts/localization_tool.py" --store "$STORE" --project "." scaffold --locale pt-PT --market pt
```
