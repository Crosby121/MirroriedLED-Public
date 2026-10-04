# Shared website work record

Start with [CURRENT_STATUS.md](CURRENT_STATUS.md). It separates the checked source
from the verified live website and lists the next tasks. GitHub is the common
record for connected apps.

| File | Purpose |
| --- | --- |
| state.json | Dated source, checks, deployment and connection observations |
| tasks.json | Priorities, ownership, blockers and acceptance criteria |
| sessions/ | One explicit work record per AI session |
| history/github-baseline.json | Sourced past GitHub events with unknown AI attribution |
| CURRENT_STATUS.md | Generated readable view of state and tasks |
| ../../AGENTS.md | Shared instructions at the repository root |
| tools/ai_workflow.py (repository root) | Local status, logging and validation helper |

## Start and finish in a Git checkout

Read current GitHub state, fetch the default branch, inspect pending work and
create your own branch/worktree. Python 3.8+ and Git are the only helper
dependencies. Use python instead of python3 on Windows if needed.

    python3 tools/ai_workflow.py status
    python3 tools/ai_workflow.py start --app "GitHub Copilot" --task WF-003

Start prints a session ID and records UTC access time, app declaration, branch
and base commit. It claims the task in this checkout. Commit/push the record and
queue, and link the work PR before coding. Other apps must inspect the shared
queue and open PRs. The local lock prevents simultaneous helper writes in one
checkout; separate checkouts still need coordination. A centralized reservation
service is part of WF-003.

Add --github-account LOGIN only when the authenticated account is known; the
helper does not discover credentials or infer the AI app from a Git author.

After actually executing a check, finish using its printed session ID:

    python3 tools/ai_workflow.py finish --session SESSION_ID --outcome completed \
      --summary "Describe the changes and fix" \
      --next-action "Describe the exact next step" \
      --changed-file relative/path/to/changed-file \
      --passed-check "The exact command you already ran"

Repeat --changed-file and --passed-check as needed. These check results are
agent reports; add links to independent CI evidence in the record when available.
Record failed or skipped checks directly in its checks array. Use --outcome
blocked for unfinished work. Both outcomes end the session and release ownership.
Only name files changed by this session; do not attribute another app's edits.
The helper uses the containing Git history to bind a record to the pushed change,
avoiding a circular requirement to store its own commit hash.

    python3 tools/ai_workflow.py validate
    python3 -m unittest discover -s tests -p 'test_ai_workflow.py' -v

The helper never fetches, commits, pushes, deploys, reads keys or connects hardware.
The consuming app performs authorized GitHub operations after validation.

## Connector-only apps

An app without a shell can read these files using its GitHub connection, create
a session JSON matching an existing record, update tasks.json, and push all
changed records together on its own branch. The app must update CURRENT_STATUS.md
to match the renderer in tools/ai_workflow.py; validation catches drift.

Session fields: schema_version=1; id; application; application_identity=declared;
github_account (known login or null); started_at/ended_at (UTC ISO times);
status (active/completed/blocked); task_ids; branch; base_commit; summary;
next_action; changed_files; checks; findings. A check has name, result
(passed/failed/skipped/not_run), optional command and evidence_url. Findings
include their source and distinguish observation from inference.

Task fields: id, title, status (ready/in_progress/blocked/done), priority,
owner_session_id, last_session_id, depends_on, acceptance, next_action, evidence.
An in-progress task must reference an active owning session. A task claim is
shared only after publication; do not treat a private draft as a global lock.

## Refresh status with evidence

Read the actual default-branch SHA, current PRs, relevant Actions runs and their
job outcomes at session start. Refresh state.json when an observation changes;
keep the original observed commit and timestamp for historical evidence.
Then run:

    python3 tools/ai_workflow.py status --write

Update observed_at when refreshing evidence, not merely when editing a task.
Do not replace a failed deployment with a successful package result. A non-null
deployment.live_commit requires live_verified_at and verification_evidence.
A failed run before upload is recorded separately from the unknown live version.
Record only redacted problem summaries; secret names can be recorded, values cannot.

The generated status is a snapshot. The status command also shows the current
local HEAD and warns when it differs from the observed source. Workflow checks
validate records; they do not certify every claim or automatically refresh
Hostinger state.

## Connection stage

The starting foundation installs shared files, the local logger and CI validation.
Full automatic chat imports, automatic access capture and the common remote
connector are not installed by this change. Each app needs its own authorized
connection and startup/handoff integration. Instruction files guide behavior;
they cannot guarantee every app will report every action.

WF-003 will expose explicit tools such as read_state, start_session,
claim_task and finish_session through a shared authenticated MCP endpoint.
Hostinger Agent uses MCP tools and ignores MCP resources/prompts, so the endpoint
must return the actual work record through tools.

Official references:

- [ChatGPT and Codex MCP connections](https://learn.chatgpt.com/docs/extend/mcp)
- [Copilot MCP connections](https://docs.github.com/en/copilot/how-tos/copilot-in-your-ide/customize-copilot/extend-copilot-with-tools-and-context/extend-copilot-chat-with-mcp)
- [Hostinger Agent custom MCP connections](https://www.hostinger.com/support/connect-apps-and-custom-mcp-servers-to-hostinger-agent/)
- [Codex AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- [Copilot repository instructions](https://docs.github.com/en/copilot/how-tos/copilot-in-your-ide/customize-copilot/configure-custom-instructions/add-repository-instructions-in-your-ide)

Hostinger Agent and Hostinger AI Builder are separate products. Builder code
export has import limitations; Agent can use an authorized GitHub MCP connection.
Use this repository's existing release tooling for its code-managed website.

## History and privacy

This is a public repository. Store relevant public work summaries and evidence
links. Keep private chat exports, credentials, customer identities, recordings,
media, order data and unredacted logs outside it.

The validator detects recognizable private-key and token formats. It is a
best-effort guard; review and redact summaries before publication.

The imported baseline records merged PRs and checked workflow outcomes. GitHub
accounts and merge times are known; AI app identity and earlier access times
remain unknown unless an explicit trustworthy source supplies them. Available
chat exports may be curated later under WF-004. Never invent missing history.
