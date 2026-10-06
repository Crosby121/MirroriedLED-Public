# AI capture privacy repair implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task. Steps use checkbox syntax for tracking.

**Goal:** Complete the pending PR 15 privacy update without changing storefront images or activating payments.

**Architecture:** Port the reviewed capture changes onto current main, preserving current deployment records and unrelated tasks. Redact plaintext transcripts with whole-text context and redact complete browser message text before calculating UTF-16 deltas. The existing native redactor remains a second filter.

**Tech Stack:** Python 3 standard library; Chrome extension JavaScript; Node's built-in test runner; existing PHP connector and GitHub Actions.

**Spec:** `docs/DEPLOYMENT_READINESS_20261005.md`, independently reproduced PR 15 findings; https://github.com/Crosby121/MirroriedLED-Public/pull/15#discussion_r4179809128 and https://github.com/Crosby121/MirroriedLED-Public/pull/15#discussion_r4179809142.

## Global constraints

- Preserve private configuration, customer records, existing website images and placeholder pricing.
- Use artificial test data only. Do not activate payments or automatic PC capture.
- Preserve JavaScript UTF-16 offsets, Unicode fragment boundaries and durable queue acknowledgement semantics.
- Preserve current main's task/session records; older task IDs must be reconciled without overwriting different work.
- Publish the task claim before editing product code; publish and verify the final handoff.

## Review focus

- Plaintext PEM blocks spanning several lines must not leave key bodies in persisted objects.
- Adjacent JSONL records must retain decoded structured credential filtering and safe message text.
- Empty, incomplete, appended and edited sensitive values must be masked before any browser checkpoint is queued.
- Long values crossing fragment boundaries and emoji must retain reconstruction offsets and safe text.
- Unchanged masked values must not corrupt later visible suffix edits or generate unnecessary checkpoints.

### Task 1: Transcript persistence

**Files:** Modify `tools/ai_capture.py`, `tests/test_ai_capture.py`; preserve supporting PR 15 changes in connector tests and setup docs.

**Interfaces:** `redact_transcript(text: str, known_secrets) -> str`; `capture(config, event, source)` persists only redacted transcript objects.

- [ ] Import the existing PR 15 source/tests after the published claim; retain current workflow records.
- [ ] Add `test_plaintext_private_keys_are_redacted_before_archive_persistence`: capture a synthetic multiline PEM plus surrounding safe text; assert the key body is absent from local objects and an archive double, and safe text remains.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_ai_capture.py' -v`; observe the new case fail on the key body.
- [ ] Apply whole-text plaintext filtering while decoding JSON/JSONL records independently; keep incomplete PEM blocks masked to end of text.
- [ ] Run the capture tests and existing workflow tests; require all runnable cases to pass.
- [ ] Commit the independently verified transcript repair.

### Task 2: Browser checkpoint privacy

**Files:** Modify `tools/browser-ai-capture/content.js`, `tests/browser-ai-capture.test.cjs`, `docs/ai-workflow/AUTO_CAPTURE.md`.

**Interfaces:** `checkpoint(force = false)` queues full/delta messages using length-preserving redacted text; the background queue receives no raw sensitive value from those fragments.

- [ ] Add regressions for a token streamed from an empty field, appending/editing its value, an incomplete value, a long split credential, a PEM block and later visible suffix edits.
- [ ] Run `node --test tests/browser-ai-capture.test.cjs`; observe raw credentials in checkpoint fragments before the fix.
- [ ] Redact complete message text before comparing or slicing it, replacing sensitive spans with one block character per UTF-16 code unit.
- [ ] Verify reconstructed text retains visible content and original offsets while all queued parts exclude synthetic credentials.
- [ ] Run JavaScript syntax checks and browser capture tests, plus the repository's relevant Python workflow suite and CI.
- [ ] Commit, obtain an independent whole-branch review, publish and verify checks, integrate within existing publication authorization, and finish the task record with actual evidence and activation limits.
