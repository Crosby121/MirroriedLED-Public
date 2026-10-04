# Mirroried LED shared workflow

Read the root AGENTS.md, docs/ai-workflow/CURRENT_STATUS.md, state.json, tasks.json
and recent session records before implementation. Refresh actual GitHub state;
the status files are dated snapshots.

Identify this application as GitHub Copilot when that is the application in use.
Record a session, claim the selected task, work on an isolated branch, publish
the claim, and check the queue plus open PRs for another session's claim.
Use tools/ai_workflow.py or equivalent JSON records. At handoff, record changed
files, actual tests, fixes, failed attempts, blockers and the next action.
Run the workflow validator before pushing. Its CLI is documented in
docs/ai-workflow/README.md.

Keep application declarations distinct from authenticated GitHub accounts.
Preserve unknown historical attribution. Keep source verification and live
Hostinger deployment verification separate. Apply the existing product,
privacy, quote and release rules in AGENTS.md and the relevant feature docs.
