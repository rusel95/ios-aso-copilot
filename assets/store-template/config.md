# App config

This repo's own App Store Connect identity. Static — unlike `STATE.md`, Step 8 of `auto` mode never
rewrites this file. Bump `**Version**:` by hand when a new version starts (same moment
`MARKETING_VERSION` gets bumped in the Xcode project).

**App ID**: TODO — this repo's App Store Connect app id (`asc apps list` if unsure which one)
**Version**: TODO — the version currently being worked on, e.g. "1.0"
**GA4 Property ID**: TODO — optional numeric property ID; set only if this app uses GA4/Firebase
**GA4 Credentials**: TODO — optional path to this app's service account JSON; leave unset when runtime ADC is configured

App ID or Version still reading `TODO` → the skill refuses to guess and names this file as the fix.
If GA4 is configured, its property must be explicit here or passed as a one-off `--property-id`; no
cross-app mapping, environment property, or saved-state fallback is used.
