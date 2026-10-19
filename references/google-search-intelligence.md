# Google search intelligence (Google ↔ App Store)

Google data is **web search**. It can help choose between two synonyms and shows how people phrase a problem. It is not the
App Store's volume, and it is read after the Apple side, never instead of it.

## Evidence order

1. **Apple's autocomplete** for the storefront: `ios-aso-copilot keywords hints --term "<full term>" --country <cc>`. An empty list
   for a full term means no App Store evidence. Serial calls only (about 1.2 s apart; parallel storefronts answer 429).
2. **Rank reads**: `rank_audit.py` / the iTunes Search API (top 200). Take several baseline days: one storefront moved a head key
   from #24 to #10 between two days.
3. **Apple Ads delivery and popularity**: `radar keywords`, `radar report`. Keys of two words or fewer got 932 of 1,041
   keyword-attributed impressions in one 14-campaign week.
4. **Google Trends / Suggest** (`google trends|suggest|batch`): wording and situations.

A phrase becomes a metadata word or an Exact key only after 1–3 say the App Store has it. Google alone never moves a word into the
name, the subtitle or the keyword field.

## What Trends is, and the traps seen in real runs

- **Relative and mixed.** 0–100 against the peak of the same request, over every language a country uses. In Ukraine `память` is
  both "Ukrainian without the apostrophe" and an ordinary Russian word; a Russian-form query can be the largest term in the table
  (for example `очистить память` and `сжать видео`) and say nothing about how Ukrainians type Ukrainian.
- **Phrase shape differs.** In one run Google's biggest term was `зменшити відео`; Apple completes
  `зменшити розмір відео/фото/файлу` and never `зменшити відео`.
- **The anchor decides the precision.** Trends returns whole numbers. A run anchored on an index of ~6 printed `1,307.6` for `очистити пам'ять`,
  `176.4` for `очистити память` and `2,694.0` for the Russian `очистить память`. `google batch` now warns when the anchor's weekly index averages under 8, says the table is only
  an order, and names a mid-volume term to re-run with. Pick a mid-list anchor up front.
- **0 and empty are not "no demand".** A candidate Trends rounds to 0 next to the anchor is "below Trends' floor"; an empty
  (throttled) response is `n/a`. The tool prints both as such.
- **One run is one sample.** The same term moved 431.0 → 427.0 between runs; neighbouring spellings moved far more. Quote an order,
  not a multiplier, and repeat before a decision rests on it.
- **pytrends is an unofficial scraper.** It lives in `<skill>/.venv`; expect 429 on long lists (`--delay 2`). Keyword Planner
  (absolute bands) needs a Google Ads account with spend and is not wired.

## Rules that are easy to write down wrongly

- **No field weights.** Apple publishes none. "Title = 3–5x subtitle" and "10/7/5" were both written as facts in one session and
  contradict each other. A keyword-field word and a title word can rank alike (in one real app's history, `зменшити`/`розмір` in the
  keyword field, `відео` in the name: #6–#15 for `зменшити розмір відео` over a month).
- **Other apps' names stay out of the keyword field** (App Review Guideline 2.3.7) and out of feature claims. A system share sheet is
  not "quick send to Telegram and Viber".
- **Apple does not read the description for store search** (widely reported, not documented). Google reads the product page, so copy
  written for it must still describe real features.
- **Never edit the repo copy of a live version**; new text goes into the next version's folder.
- **Autocomplete is an undocumented endpoint**, not "unthrottled": keep the pacing.

## Commands

```bash
ios-aso-copilot google trends "A" "B" --country US            # up to 5 terms, 12 months; --related, --geo
ios-aso-copilot google suggest "seed" --country US --lang en --matrix
ios-aso-copilot google batch --anchor "<mid-volume term>" --terms "a,b,c" --country US   # or --file terms.txt; --json
ios-aso-copilot keywords hints --term "<full term>" --country us                          # the Apple side
```

## Worked example (pattern, not data)

Pick a mid-volume anchor and set it to 100. Read the Google column as an order, the Apple column as what the autocomplete
returns for the full term, and the rank column as the iTunes Search position for the same storefront. A term that Apple's
autocomplete never returns is not an App Store query, however large its Google index. Keep the full table, the raw files
and the caveats in the app's own `marketing/reports/` folder, not in this skill.
