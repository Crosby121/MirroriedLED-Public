# Mirroried LED AI database

This is a working owner-local SQLite knowledge store. It collects sourced
business knowledge, product/component/build records, decisions, task references
and declared AI activity. A visual HTML report provides local browsing and search.
The database uses Python 3.10+ and SQLite FTS5 from Python's standard library.
There is no package install, external API charge, model inference or embeddings.

## Open on Windows

Extract the downloadable package and double-click **Start_AI_Database.cmd**.
Python must already be installed. The launcher creates the database in
`%LOCALAPPDATA%\MirroriedLED\ai-database.sqlite3`, loads the included curated
starter records on the first empty run, imports the packaged dated workflow
snapshots, and opens a new visual report. It never replaces an existing database.
The reports are static snapshots. Run the launcher again after changing records.
On macOS/Linux run `python3 open_database.py` from the extracted package folder;
the database defaults to `~/.local/share/MirroriedLED/ai-database.sqlite3`.

The public GitHub source has example records only. Business starter content,
workflow exports, customer data, local database files and reports stay outside
the public repository. The private download includes dated curated business
records and a verified backup, with its exact snapshot provenance in manifest.json.

## Command line

From the repository root:

```sh
python3 services/ai-database/ai_database.py init
python3 services/ai-database/ai_database.py source services/ai-database/examples/source.json
python3 services/ai-database/ai_database.py put services/ai-database/examples/record.json
python3 services/ai-database/ai_database.py search "HUB75 laser"
python3 services/ai-database/ai_database.py get example-build-rule
python3 services/ai-database/ai_database.py context "mirror fabrication"
python3 services/ai-database/ai_database.py import-workflow --root . --locator "Exact local checkout snapshot"
python3 services/ai-database/ai_database.py import-history --root . --locator "Exact local checkout sessions"
python3 services/ai-database/ai_database.py report /absolute/private/path/AI_Database.html
python3 services/ai-database/ai_database.py backup /absolute/private/path/AI_Database_backup.sqlite3
```

In the download use `ai_database.py` instead of `services/ai-database/ai_database.py`.
Windows can use `py -3` instead of `python3`. Set `--db /absolute/private/path/file.sqlite3`
before the command to use a separate database. Avoid the customer portal's database.
The launcher uses the documented default path; use the CLI for a custom path.

## What it stores

| Area | Representation | Behavior |
| --- | --- | --- |
| Sources | Immutable title, locator, basis, observed time | New provenance needs a new source ID |
| Business knowledge | Typed records with confidence and status | Search returns the source and date |
| Products and components | Structured metadata in typed records | A cost requires a date and explicit basis; unknown cost stays null |
| Builds, customer/device/media/show references | Typed records | No actual customer/media import or account access is implied |
| Changes | Complete record revisions | Existing edits require the current expected version |
| AI activity | Idempotent events | Application is declared or unknown; no inferred identity or access time |
| Shared workflow | Immutable state/queue snapshots and session events | Imports never reserve tasks or rewrite GitHub |
| AI retrieval | Source-carrying keyword context JSON | Retrieved text is untrusted reference data |
| Recovery | SQLite online backup plus full JSON export | Backups include committed WAL changes and check integrity |

All record kinds: knowledge, product, component, build, task, decision, sponsor,
advertising, customer, device, media, show and connection. These are storage
categories, not separate live portal implementations. Optional metadata must be
a JSON object. Search covers titles, body and metadata; source provenance remains
attached. `--kind` filters searches; archived records require `--include-archived`.

`put record.json --expected-version 2` changes a version-2 record. A stale edit is
refused. `history RECORD_ID` returns every accepted revision. Archive using a
versioned record update with `status: archived`; no delete command is exposed.
Bundles have `sources` and `records` arrays. Identical imports replay safely;
different content with the same ID is refused until explicitly revised.

## Integration boundary

The existing shared workflow JSON and MCP service remain authoritative for task
ownership. The customer portal keeps its existing database, login and media rules.
This service refuses to adopt an unrelated SQLite file. It is a separate owner-only
knowledge store and does not offer public HTTP endpoints or customer queries.

Read the latest workflow/GitHub before acting on an imported task. Imports are
dated observations and do not prove a connection, payment entitlement or live
Hostinger version. Session history imports preserve content snapshots, including
active and later completed observations. They do not copy inaccessible chats.
Identical sessions replay across different import locations while retaining
their original source locator. Each session's source and activity are saved in
one transaction; rejected activity leaves no partial source. End times compare
as UTC instants, including fractional seconds, while original timestamps remain
in the source snapshot.

An AI app can later call the CLI through an authorized local tool or an authenticated
adapter. Adapter activation, live synchronization, tenant authorization and API
credentials are separate integration work. The database itself does not connect
ChatGPT, Copilot, Hostinger Agent, WLED, Chataigne or the website automatically.

## Private use and recovery

Keep live database, reports, backups, exported JSON and starter content in the
owner's private folder. POSIX files are set to owner-only permissions; Windows
uses the current user's profile and inherited ACLs. This tool does not configure
Windows ACLs, encrypt disks or create a multi-user authorization system.
Recognition checks ownership and schema against a private temporary copy that
includes committed WAL and rollback-journal state. It leaves the originals
untouched. After recognition, opening tightens the main file and existing WAL,
shared-memory and journal files before SQLite can recover, index or write them.
Newly created sidecars inherit the private main-file permissions. Unrelated
database files retain their bytes and permissions, including pending journals.
Opening an existing store needs temporary space for the database and its WAL or
journal; the recognition copy is removed afterward.
Credential filtering rejects common keys, token formats and query-bearing links,
but it cannot certify arbitrary text as private-safe. Import curated authorized
business summaries; keep raw private transcripts and secrets in their dedicated
private archive. Never put runtime files into the public Git repository.

To recover, close database users, retain the damaged file for inspection and point
`--db` at a verified backup, or copy that backup to a new private filename. Backups
are independent SQLite files. `export OUTPUT.json` includes sources, records,
revisions, activity and workflow snapshots for inspection/migration; v1 does not
offer automatic JSON restore. The visual report is read-only and contains private
data. No external scripts, fonts or network calls are used.

## Validation

```sh
python3 -m unittest discover -s tests -p test_ai_database.py -v
```

Tests cover source integrity, stale/concurrent edits, history, searchable updates,
idempotent events/imports, transaction rollback, unknown costs, credential guards,
workflow snapshots, unrelated database refusal, symlink refusal, escaped HTML,
CLI retrieval, private database/sidecar permissions and WAL-aware backup recovery.
Regressions also cover original-string credential filtering, JSON type conflicts,
fractional chronology, overlapping/concurrent history imports and atomic rejection.
Hot-journal recovery and ownership metadata held only in active WAL are covered.
