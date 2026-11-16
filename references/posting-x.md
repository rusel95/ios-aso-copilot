# X (Twitter) — not validated yet

Nothing here has been run. Treat every line as a plan to confirm on the first real post, then replace it
with what actually worked (selectors, limits, traps), the way `posting-runbook.md` was written for Threads.

## Before the first post

1. Ask the owner for the handle and whether Chrome is signed in. Never ask for a password and never use an API
   key from chat; the browser session the owner signed in is the only credential.
2. Confirm the account type: the character limit differs between account types. Do not assume it.
3. Decide with the owner what goes first, and check the owner's existing public profile copy before writing a bio.

## Plan, to confirm

- The same loop as Threads: slot, draft, gate with the overlay's rules, approval, publish through Claude in
  Chrome (`find` the compose box, `find` the hidden file input, `file_upload`), verify on the profile, first
  reply with the tracked link, record.
- Formats: the scoreboard shortened to the limit (rank lines only); findings as a thread of two to four posts
  with the card on the first; the how-to as a pinned post.
- A separate campaign token per network (for example `x_<campaign>`), so downloads can be told apart.
- The overlay's content rules apply unchanged.

## To record after the first run

Selectors that worked; the real limit; whether link cards render; how threads are composed; what broke.
