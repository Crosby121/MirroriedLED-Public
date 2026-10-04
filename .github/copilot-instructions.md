# Mirroried LED shared workflow

Read the root AGENTS.md, docs/ai-workflow/CURRENT_STATUS.md, state.json, tasks.json
and recent session records before implementation. Refresh actual GitHub state;
the status files are dated snapshots.

Identify this application as GitHub Copilot when that is the application in use.
Record a session, claim the selected task, work on an isolated branch, publish
the claim, and check the queue plus open PRs for another session's claim.
Prefer read_state, start_session, claim_task and finish_session through the
configured mirroriedLedWorkflow MCP server. Verify the returned GitHub receipt
before reporting completion. Without that connection, use tools/ai_workflow.py
or equivalent JSON records and verify their publication. At handoff, record changed
files, actual tests, fixes, failed attempts, blockers and the next action.
Run the workflow validator before pushing. Its CLI is documented in
docs/ai-workflow/README.md.

When installed locally, .github/hooks/ai-capture.json checkpoints available
Copilot chat/tool events to a private queue. The background worker retries
GitHub uploads after the editor closes. This does not certify support in every
Copilot harness or export unavailable internal context. Setup and receipt checks
are in docs/ai-workflow/AUTO_CAPTURE.md.

Keep application declarations distinct from authenticated GitHub accounts.
Preserve unknown historical attribution. Keep source verification and live
Hostinger deployment verification separate. Apply the existing product,
privacy, quote and release rules in AGENTS.md and the relevant feature docs.
