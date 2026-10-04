# Connect the shared AI workflow

Implementation is ready for setup. The endpoint has not been installed or tested
on Hostinger. Verify each app's connection before describing it as active.

Planned endpoint: `https://mirroriedled.com/ai-workflow/mcp.php`.
Repository: `Crosby121/MirroriedLED-Public`, branch `main`.

| Tool | Result |
| --- | --- |
| read_state | Actual GitHub HEAD, dated site observations, task queue and recent sessions |
| read_history | Paginated session records; filename order, not chronological order |
| start_session | Record access time and reserve an available task in one commit |
| claim_task | Reserve another task for the same client's active session |
| finish_session | Publish completed/blocked work, checks and next action; release all claims |

An app credential identifies a configured client. The application name is an
explicit declaration, not proof of which software physically made the request.
The service separately verifies the GitHub token's account. Product files cannot
be written by these tools. Simultaneous claims are checked again after conflicts;
a task claimed by another session cannot silently be taken over.

## Prepare credentials once

1. Create a fine-grained GitHub token for Crosby121 with access only to
   MirroriedLED-Public and Contents read/write. Repository rules must permit
   the service's non-forced record commits to main. Keep protections that apply
   to this repository; if a rule rejects a write, the connector reports the
   rejection and does not report success.
2. In a local checkout, run:

       python tools/configure_ai_workflow.py

   Enter the token in the hidden prompt. This creates private, ignored
   `mirroriedled-private/ai-workflow/config.json` and `client-credentials.json`.
   The server configuration contains hashes of three distinct app credentials.
   Keep plaintext client credentials locally and enter each only in its matching
   app's secure connection settings.
3. Set `AI_WORKFLOW_CONFIG` to the complete contents of config.json in the
   GitHub production environment secrets. Supply the existing main-site
   `HOSTINGER_SSH_PRIVATE_KEY` and independently verified
   `HOSTINGER_SSH_KNOWN_HOSTS`. Those SSH settings were missing in the last
   observed website release. The sponsor VPS is a different destination.

Never paste tokens into a chat or commit either private JSON file. Transcript
archive access uses a separate token and private repository; see
[AUTO_CAPTURE.md](AUTO_CAPTURE.md).

## Install only the connector

Run **Deploy Shared AI Workflow Connector** from GitHub Actions on main. It is
manual only. It tests the source, validates the exact main-site profile and live
homepage checksum, then installs two public endpoint files and private service
configuration. It does not replace the storefront or deploy the full website.

Implementation, token, backups and receipts stay outside public_html. Unowned
existing endpoint files are refused. If the HTTP smoke check fails, the workflow
restores the previous connector files. Keep the production environment's
existing approval settings.

A first-install rollback retains a private ownership marker and backups, allowing
a corrected deployment to retry without treating an arbitrary existing directory
as this service. It restores or removes all executable/configuration files.

The smoke check verifies anonymous HTTP 401 and authenticated GitHub read access.
An ephemeral deployment-check credential is generated for that run; no extra
permanent smoke-check secret is required. App read/write tests remain separate.

## Connect each app

| Application | Configuration | Verification still required |
| --- | --- | --- |
| Local Codex desktop/CLI/VS Code extension | Merge connections/codex.config.toml into the user Codex config; securely set MIRRORIED_WORKFLOW_TOKEN to the chatgpt-codex credential | Trusted hooks, tool discovery, actual start/finish commit receipts |
| Hosted ChatGPT Work | An authorized plugin providing the remote MCP endpoint; local TOML is not read by hosted ChatGPT | Plugin availability/authentication and tool discovery in that hosted chat |
| Copilot in VS Code, Local harness | .vscode/mcp.json supplies the HTTP server and a hidden credential prompt; use the copilot credential | MCP trust/authentication and start/finish receipts |
| Copilot Agent Host | That harness's supported MCP profile and secure environment configuration; interactive Local input prompts are not forwarded | Profile and hooks support for the installed version |
| Hostinger Agent | Custom MCP, Streamable HTTP endpoint above, Authorization header with value `Bearer <hostinger-agent credential>` | Its own tool discovery and read/write receipts |

Hostinger Agent and Hostinger AI Builder are separate products. This setup targets
Agent's custom MCP support. Other apps need supported MCP or authorized GitHub
tools and a separately provisioned credential. Do not share another app's
credential or claim those apps were tested.

For each client, first call read_state. Confirm the repository, actual HEAD and
authenticated client/account. Start a real selected task with the matching
application label and a unique request_id. Inspect the returned GitHub commit.
Use finish_session with an honest completed or blocked outcome, changed paths,
executed checks and next action; inspect that second commit. If a response was
lost, retry the same request/session and parameters: idempotent retries return
the existing record. Changed completion details for a closed session are rejected.

New MCP session IDs include the client and a hash of request_id. Native capture
hooks remember successful start/finish receipts and can request one final handoff
at Stop when a session is still active. A closed window alone does not complete
a task or release ownership. Review stranded sessions explicitly.

## Verification and limits

    python tools/ai_workflow.py validate
    python -m unittest discover -s tests -p 'test_ai*.py' -v
    node --test tests/browser-ai-capture.test.cjs

MCP tests require PHP 8.2+ with curl. They exercise the actual HTTP server against
a GitHub double, including concurrent claims, lost responses and rejected
credentials. Installer tests verify backup/rollback and website preservation.
They do not prove live Hostinger installation or authenticate real apps.

Public records must be redacted. The credential guard is best effort. The
connector does not expose private transcripts; authorized apps can use their
own private GitHub connection for those archives.

Official references:

- [Codex MCP and hosted ChatGPT plugins](https://learn.chatgpt.com/docs/extend/mcp)
- [VS Code MCP configuration](https://code.visualstudio.com/docs/agent-customization/mcp-servers)
- [VS Code MCP reference and harness differences](https://code.visualstudio.com/docs/agents/reference/mcp-configuration)
- [Hostinger Agent custom MCP](https://www.hostinger.com/support/connect-apps-and-custom-mcp-servers-to-hostinger-agent/)
- [MCP Streamable HTTP transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)
- [GitHub non-forced reference updates](https://docs.github.com/en/rest/git/refs)
