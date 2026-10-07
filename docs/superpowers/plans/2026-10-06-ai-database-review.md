# AI database review repair implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Integrate the pending owner-local AI database after repairing the six PR 16 review defects.

**Architecture:** Port PR 16 onto current main while preserving the authoritative workflow records. Validate original string values, compare normalized records with canonical JSON, protect recognized SQLite files before WAL writes, and import each session with atomic immutable provenance and chronological UTC validation.

**Tech Stack:** Python 3.10+, standard-library SQLite/FTS5, existing GitHub Actions. No new dependency or live service.

**Spec:** Six review findings at https://github.com/Crosby121/MirroriedLED-Public/pull/16 and the source integration boundary in `docs/AI_DATABASE.md` from `caf12c902c2e98fa31e370e34915fc33f8333bce`.

## Global constraints

- Preserve current product images, storefront source, private customer data and deferred payment setup.
- Use artificial data and temporary databases. Do not import private customer data or raw chat into GitHub.
- Python 3.10+ and SQLite FTS5; no third-party dependency.
- Sources and session provenance remain immutable; replay must preserve original source locators and refuse changed JSON content.
- Refuse unrelated SQLite databases and symlinks before writing or changing their permissions.
- Keep current main task/source/deployment observations; preserve distinct prior task/session history.
- Publish the claim before editing source; verify final code, CI and completed handoff receipts.

## Review focus

- Credential patterns separated by tab/newline and mixed-case URL schemes must be rejected before persistence or export.
- Nested boolean/numeric differences must cause replay conflicts without accepting invalid costs or modifying revisions.
- Existing recognized POSIX main/WAL/SHM/journal files must become owner-only before WAL or application writes; unrelated files remain unchanged.
- Fractional UTC timestamps must compare as instants in both directions; original source timestamps remain available.
- Re-imports from different locators, overlapping new sessions and concurrent requests must preserve immutable provenance and detect request-ID conflicts.

### Task 1: Payload and replay validation

**Files:** `services/ai-database/ai_database.py`, `tests/test_ai_database.py`; retain PR 16 docs, examples, schema, launcher and CI coverage.

**Interfaces:** `safe_payload(value)`, `Database.put(value, expected_version=None)`, `Database.bundle(value)`.

- [ ] Port the pending PR 16 source after the published claim; retain main workflow state and import distinct WF-011 history.
- [ ] Add failing regressions for Bearer tab/newline values in record bodies/nested metadata and signed/user-info URLs with uppercase/mixed-case schemes. Assert rejected writes leave records/export free of artificial credentials; retain a safe mixed-case URL positive case.
- [ ] Add a failing bundle replay case changing nested `cost_usd: 1` to `true`, plus nested numeric/boolean metadata. Assert conflict, unchanged stored record and one revision.
- [ ] Run `python3 -m unittest discover -s tests -p 'test_ai_database.py' -v`; observe the intended failures.
- [ ] Match secrets against each original string and URL schemes case-insensitively; compare normalized replay content using canonical `dumps()`.
- [ ] Run the database suite; require the new cases and existing behavior to pass. Commit.

### Task 2: SQLite private file permissions

**Files:** `services/ai-database/ai_database.py`, `tests/test_ai_database.py`, `docs/AI_DATABASE.md`.

**Interfaces:** `Database(path, create=False)`, `private_file(path)`; recognized database ownership/schema checks precede permission changes to existing unrelated files.

- [ ] Add a POSIX regression reopening a recognized 0644 database and existing WAL/SHM files, then performing a write. Assert all existing/new sidecars and the database are 0600 before WAL/application writes. Retain unrelated database bytes/permissions and symlink refusal cases.
- [ ] Run the test; observe permissive sidecars on the pending source.
- [ ] Tighten recognized main/existing sidecar permissions before enabling WAL or writing schema/data; ensure newly created sidecars inherit private main permissions.
- [ ] Run database concurrency, WAL backup/recovery and permissions tests; require all to pass. Commit.

### Task 3: History chronology and provenance

**Files:** `services/ai-database/ai_database.py`, `tests/test_ai_database.py`, `docs/AI_DATABASE.md`.

**Interfaces:** `Database.import_history(root, locator)`, `Database.event(value)`. A private `_event(value)` may provide event validation/insertion inside a caller-owned transaction.

- [ ] Add failing forward half-second and reversed half-second session tests, with no imports for invalid chronology.
- [ ] Add a failing overlapping history replay from the CLI locator to the packaged-launcher locator; assert old event/source locator retained and only new content added.
- [ ] Cover concurrent same-content imports and conflicting pre-existing request IDs; require one event/source, atomic per-session writes and explicit conflicts.
- [ ] Run the database suite and observe the fractional/replay failures.
- [ ] Compare validated parsed UTC datetimes; transact replay detection, optional source creation and event insertion together, preserving event checksum conflict checks.
- [ ] Run the complete database and repository suites, checking all failures/skips. Obtain one independent whole-branch review, fix any important finding with RED-to-GREEN coverage, verify native GitHub checks, integrate under existing publication authorization, and publish the completed handoff.
