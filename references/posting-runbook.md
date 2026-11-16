# Posting runbook (Threads, through Claude in Chrome)

Why Chrome and not an embedded browser pane: the pane has no file-upload tool, so a picture cannot be
attached without the owner choosing it in the native dialog. Claude in Chrome can set a file on the page's
hidden file input. Proven end to end on a post with its image; X is not validated ([posting-x.md](posting-x.md)).

## 0. Load the tools once

`ToolSearch` with this query (one line):

```
select:mcp__claude-in-chrome__tabs_context_mcp,mcp__claude-in-chrome__navigate,mcp__claude-in-chrome__computer,mcp__claude-in-chrome__find,mcp__claude-in-chrome__file_upload,mcp__claude-in-chrome__javascript_tool,mcp__claude-in-chrome__get_page_text,mcp__claude-in-chrome__read_page
```

Then `tabs_context_mcp {createIfEmpty: true}` and work in that tab; close tabs you opened when done.

## 1. Check the session — stop at a login

Navigate to `https://www.threads.com/@<handle>`. If the URL becomes `instagram.com/threads/sso/…`
("Continue to Threads") or `instagram.com/accounts/login/…`, **stop** and ask the owner to sign in.
Chrome and an embedded pane keep separate sessions; one can be signed in while the other is not.

## 2. Compose

1. `find` "What's new composer field" → the button *Empty text field. Type to compose a new post.* → click.
2. `find` "file input for attaching media" → a `file-input (hidden)` ref → `file_upload` with absolute paths
   (≤ 10 MB per call). Never click the visible "Attach media" button; it opens a native dialog nobody can drive.
3. Click the dialog's text field ref and `type` the text (newlines and emoji are kept).
4. `screenshot` at scale 0.6 and check: text complete, image preview right, account right.
   Screenshot pixels ÷ scale = click coordinates.
5. Approval for this exact content ([posting.md](posting.md), rule 1).
6. Click **Post** (bottom right of the dialog).

## 3. Wait, do not force

A "Posting…" toast shows for 10–15 s. While it shows, or while the composer holds text, navigating raises
Chrome's "Leave site?" dialog: wait and retry; never `force`.

## 4. Verify on the profile — the only proof

Navigate to the profile, wait ~4 s, then run (inspection only):

```js
(() => { const out = [], seen = new Set();
  document.querySelectorAll('a[href*="/@<handle>/post/"]').forEach(a => {
    const m = a.getAttribute('href').match(/post\/([^/?#]+)/); if (!m || seen.has(m[1])) return;
    const t = (a.innerText || '').trim(); if (!t) return; seen.add(m[1]);
    const c = a.closest('[data-pressable-container="true"]') || a.parentElement.parentElement.parentElement.parentElement;
    out.push(m[1] + ' | ' + t + ' | ' + ((c && c.innerText) || '').replace(/\s+/g, ' ').slice(0, 90)); });
  return out.slice(0, 8).join('\n'); })()
```

Find the post by its first words; its time reads `1m` or a date. Open `…/post/<id>` and check the tab title is
the post text and, if there is an image, that `find` "photo" returns an image whose alt starts with "Photo by".
A post that is not in the list is **not posted**, whatever the toast said.

## 5. First reply (tracked link and sources)

On the post page `find` "reply text field" → click → `type` → `screenshot` → click the round send button at
the right end of the reply box → wait ~10 s. Verify with JS: the first words appear exactly once, "No replies
yet" is gone, no "Posting…". The first reply cannot be scheduled. After sending, the reply can be missing from the list for a few seconds while the counter already reads "Replied 1": reload the post page and check again before reporting.

## 6. Record

Hypothesis file: `went_live`, `status: live`. Schedule row done, reminder closed. Report in order: what went
out (link), what did not, what was not checked.

## An embedded pane

Use it to read: scanning, checking what the owner sees, verifying. It cannot attach a file. If it is the only
signed-in browser, type the text, open the attach picker, ask the owner to choose the file, and press Post only
after the owner's approval.
