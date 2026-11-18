# Threads formats

Defaults for a daily series. The app overlay (`marketing/social/`) sets voice, language, limits and which
format leads; where it disagrees, the overlay wins. The channel angles themselves are in `channel-playbooks.md` §2.

## Format A — scoreboard (daily, text only)

A fixed series line, a fixed two-line "who I am, what the app does" block, then a **rank list**: named rivals
with their position for one store query, your app with its position, one closing line that changes each day,
one direct ask for a review. About 450–500 characters, short lines, with a card (a picture of the rank list):
without a link there is no store card to be the visual.

```
<series line>

<who I am, what the app does, one sentence>

<Query «…»> in <storefront> (<date>):
<label>: <rival> — #<rank>
<your app> — #<rank>

<closing line: relief when ahead, honest self-irony when behind>
<ask for a review>
```

Why it works for a small account: repetition makes the series recognisable, the list gives an instant
comparison, the changing line is the human part, and the ask converts a reader into a rating. Why to be
careful: a rival's label ("foreign", "abandoned") must rest on a document, not on a quick guess; the
overlay's content rules say what counts.

## Format B — finding (weekly)

One documented finding per post, a card in two forms (clean and annotated), a first reply naming sources
and method. Heavier to make, so weekly, not daily.

## Format C — the human posts (two or three a week)

Build in public (what shipped, what broke), thanks to people who rated the app, and the **how-to** that the
audience asks for under every other post ("how do I check who is behind an app"). Pin the how-to and answer
each question with the same method. Business numbers only if the owner chooses to share them.

## Links

Default: no link to the app in the post body. Small accounts report that Threads cuts the reach of a post that carries a link;
treat that as a report, not a measurement. If the owner wants a link, it goes in the first reply with its own campaign token.
The owner may forbid links altogether ("it reads as an ad"); then neither the post nor the reply carries one, and the overlay
says so. Without links, attribution comes from views, likes and followers per post at 24 hours and from branded-search
impressions on the store side before and after a run of posts.

## Hooks

The first sentence should catch a person, not label a series ("you have 100,500 photos and cannot clean them" over "Day 9/30").
Treat the hook as a variable: alternate the two openings, read views at 24 hours, record it as a `C<NNN>` hypothesis. A pain
opening must stay true: it names the reader's problem, never a claim about the owner that he has not told you.

## Cards made of real pages

A scoreboard post is stronger when its image is made of what the store really shows: crop the product page of each tracked app
at phone width, tape the crops on one sheet, badge each with its position, mark the claim by hand. Rules learned the hard way:

- Name each app with the title the reader sees in the storefront of the post (the localized title on its page), not the search
  API's default name. Read the live page: a name the reader cannot find is a mismatch they will catch.
- Check the app is what the board says it is (category, subtitle). A speaker cleaner is not a storage cleaner; leave it out.
- Positions come from the search API. The store's own search (web or app) can list other apps in another order, so say "API" in
  the text and never screenshot a search list as proof of the numbers.
- A private seller's name is hidden on every crop. On evidence images keep only the city and country of the trader address;
  mask street, postcode, phone digits and the mail local part in the page itself, before the screenshot.
- A simulator cannot open store pages (the OS hands the link to the App Store app, which it lacks). Render the page at phone
  width in a desktop browser and say so when asked.

## Cadence

One post a day at a fixed time, A mostly, B weekly, C twice a week. A reserve of finished posts fills gaps and
never replaces a day. When the series falls behind, shift the remaining days one per day; never compress it.
