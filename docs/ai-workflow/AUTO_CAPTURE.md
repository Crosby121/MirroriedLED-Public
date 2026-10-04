# Save AI chat and work to GitHub

The capture implementation is present and tested locally. It is not installed on
your PC and no full-chat archive upload has been verified. Complete setup and
receipt checks before relying on it.

| Information | Destination | Save trigger |
| --- | --- | --- |
| Task, app declaration, access time, files, fixes, checks, blockers and next action | Public MirroriedLED-Public work records | Successful start_session and finish_session, or a verified published local handoff |
| Website source changes | MirroriedLED-Public work branch and PR | App's verified code commit/push before the completed handoff |
| Available prompts/tool payloads and authorized native transcript text | PRIVATE Crosby121/MirroriedLED-AI-History | Supported local hooks plus a background file watcher |
| Visible messages from selected ChatGPT/Hostinger Agent chats | Same private archive | Continuous browser checkpoints, visibility/pagehide attempts and tab-close event |

Do not store full chats in the public website repository. The worker checks
the account and repository visibility before every batch. A missing or public
archive is refused; pending records remain local.

## One-time PC setup

1. Create **MirroriedLED-AI-History** as a private repository under Crosby121,
   initialized with a README. Create a separate fine-grained token limited
   to that repository with Contents read/write. Confirm it stays private.
2. In a persistent local checkout, with Python 3.9+ installed, run:

       python tools/setup_ai_capture.py

   Enter the token in the hidden prompt. The alternative
   `--create-private-repository` creates the private repository if the token
   has account permission; precreating it with a narrow token is simpler.
   Do not paste the token into a chat.
3. On Windows, setup registers a Chrome native-messaging host for this user and
   starts the `MirroriedLED-AICapture` scheduled task. It restarts at login and
   watches/uploads every 30 seconds while the PC runs, including after Chrome
   or VS Code closes. Windows registry, task execution and native communication
   still need verification on the actual PC; they were not run in the Linux
   test environment. Keep the checkout and Python at their registered paths,
   or rerun setup after moving them.
4. For local Codex, review and trust .codex/hooks.json in the app's hook settings.
   For Copilot, review .github/hooks/ai-capture.json and confirm your harness
   runs those hooks. They execute a local script and cannot register themselves
   in hosted ChatGPT Work.
5. In Chrome's Extensions page, enable developer mode, choose **Load unpacked**,
   and select tools/browser-ai-capture. Its fixed extension ID is
   `hdecleonacegadhfjjnlioafnamnljkg`. It stores no GitHub credential in Chrome.
   Reload existing chat tabs after installation. Open the website conversation,
   click the extension and select **Track this chat**. Tracking follows that
   conversation URL. Enable it for each new conversation after its permanent
   URL appears; unrelated chats are not automatically read.

Generated config and queues are ignored by Git and protected by private directory
permissions. Default allowed transcript roots are ~/.codex/sessions,
~/.copilot/session-state and, on Windows, VS Code workspaceStorage. If an app
supplies transcripts elsewhere, use `--transcript-root PATH` during initial
setup or edit the private config to allow that exact trusted root. Outside-root
files are never read. Do not authorize an entire home directory.

On macOS/Linux, setup writes config but does not register Chrome or a login
service. Run `python tools/ai_capture.py watch` on a persistent computer and
configure the native-messaging/login integration for that platform before relying
on browser capture. Automatic registration in this change targets Windows.

## Completion and closing

At each completed or blocked task, the AI app must publish finish_session and
verify its GitHub receipt before reporting completion. Repository instructions
require this. Supported Stop hooks checkpoint chat and can request one handoff
if a confirmed MCP session is still active; they avoid an infinite Stop loop.
This assist does not replace checking the receipt.

The app must also commit/push its source changes and include the actual commit/PR
evidence before claiming the task is completed. The capture worker archives chat;
it does not commit arbitrary files, save editor buffers or deploy the website.

Local Codex supplies SessionEnd in supported versions. Copilot CLI/SDK documents
sessionEnd, while VS Code Local does not document that event. VS Code can still
checkpoint through supported prompt/tool/Stop hooks. The background worker follows
registered transcript files and catches final writes after the UI disappears.
Actual transcript_path availability depends on the app/version. Each record says
whether it contains a native transcript or only the hook payload.

The Chrome helper reads rendered text in tracked tabs and checkpoints during
streaming. Each part goes to persistent browser storage before forwarding to the
PC helper. Tab removal adds a close event linked to the last checkpoint.
Unacknowledged parts retry while Chrome runs or at the next startup. The PC worker
independently retries records already acknowledged on disk.

Closing all browser windows can stop the extension before a final event finishes.
Power loss, crashes, unloaded/virtualized messages, hidden context, attachments
and unsupported selectors cannot be guaranteed. Periodic saves reduce loss but
do not recover content never captured. No universal cross-app full-chat or
reliable browser-exit API is available. Past chats need a separate authorized
export/import; this setup does not automatically import them.

Native transcript text is limited to 20 MiB per capture and split into immutable
content-addressed objects. Events preserve UTC time, configured source,
session/conversation key, trigger, coverage and object IDs. Credential redaction
happens before PC queue persistence/upload. It removes known tokens and
recognizable formats but is best effort. Browser retry copies contain rendered
text in the local Chrome profile until acknowledged. Only authorized apps with
private GitHub access can read full archives. The shared public MCP connector
serves redacted work records, not these raw files.

## Confirm uploads

    python tools/ai_capture.py status
    python tools/ai_capture.py flush

The popup distinguishes queued records and GitHub receipts. A browser
acknowledgment means **saved on the PC**, not uploaded. Private spool/uploaded
receipts include the actual GitHub URL and upload time. Check that URL in the
private repository; its event points to any transcript objects. Record counts
represent checkpoints, not completed tasks or complete conversations.

Test a harmless message and real task handoff from each app. Confirm the public
handoff commit and separate private event. Close the tracked tab, then VS Code;
check close/final-file events and upload receipts. Test an offline save, restore
connectivity and confirm upload once. If private worker-status.json says
retry_pending, inspect token access and repository visibility locally. Never
mark a missing upload as successful.

Official references:

- [Codex local hooks, trust and SessionEnd limits](https://learn.chatgpt.com/docs/hooks)
- [VS Code hooks and harness differences](https://code.visualstudio.com/docs/agent-customization/hooks)
- [Copilot events and payloads](https://docs.github.com/en/copilot/reference/hooks-reference)
- [Chrome native messaging](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging)
- [Chrome tab removal](https://developer.chrome.com/docs/extensions/reference/api/tabs)
