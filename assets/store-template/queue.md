# Queue

Pending approvals — actions the approval fence stopped. Every entry carries an exact runnable
command, its effect in plain language, and its preconditions. A review reply runs only against its entry (`reviews respond --queue-id`)
and is then recorded in decisions.md; remove abandoned entries.

Fence rules: `references/commands.md`. Entry format: `references/state-store.md`. Both in the
`ios-aso-copilot` skill.

_none queued_
