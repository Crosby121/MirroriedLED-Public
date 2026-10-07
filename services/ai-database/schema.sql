PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    locator TEXT NOT NULL,
    basis TEXT NOT NULL CHECK (basis IN ('user_statement','document','repository','imported_snapshot','manual')),
    observed_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL CHECK (kind IN ('knowledge','product','component','build','task','decision','sponsor','advertising','customer','device','media','show','connection')),
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    metadata_json TEXT NOT NULL CHECK (json_valid(metadata_json)),
    source_id TEXT NOT NULL REFERENCES sources(id),
    confidence TEXT NOT NULL CHECK (confidence IN ('user_reported','source_observed','proposed','needs_verification','historical')),
    status TEXT NOT NULL CHECK (status IN ('active','draft','blocked','archived')),
    version INTEGER NOT NULL CHECK (version > 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS records_kind_status ON records(kind,status);
CREATE INDEX IF NOT EXISTS records_source ON records(source_id);
CREATE TABLE IF NOT EXISTS record_revisions (
    record_id TEXT NOT NULL REFERENCES records(id),
    version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL CHECK (json_valid(snapshot_json)),
    changed_at TEXT NOT NULL,
    PRIMARY KEY (record_id,version)
);
CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
    id UNINDEXED, title, body, metadata_json, tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS records_insert_search AFTER INSERT ON records BEGIN
    INSERT INTO records_fts(id,title,body,metadata_json) VALUES(new.id,new.title,new.body,new.metadata_json);
END;
CREATE TRIGGER IF NOT EXISTS records_update_search AFTER UPDATE ON records BEGIN
    DELETE FROM records_fts WHERE id = old.id;
    INSERT INTO records_fts(id,title,body,metadata_json) VALUES(new.id,new.title,new.body,new.metadata_json);
END;
CREATE TRIGGER IF NOT EXISTS records_delete_search AFTER DELETE ON records BEGIN
    DELETE FROM records_fts WHERE id = old.id;
END;
CREATE TABLE IF NOT EXISTS activity (
    id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL UNIQUE,
    payload_sha256 TEXT NOT NULL,
    application TEXT,
    application_identity TEXT NOT NULL CHECK (application_identity IN ('declared','unknown')),
    action TEXT NOT NULL,
    summary TEXT NOT NULL,
    task_id TEXT,
    source_id TEXT NOT NULL REFERENCES sources(id),
    occurred_at TEXT,
    recorded_at TEXT NOT NULL,
    details_json TEXT NOT NULL CHECK (json_valid(details_json))
);
CREATE INDEX IF NOT EXISTS activity_time ON activity(recorded_at);
CREATE TABLE IF NOT EXISTS workflow_snapshots (
    id TEXT PRIMARY KEY,
    content_sha256 TEXT NOT NULL UNIQUE,
    source_id TEXT NOT NULL REFERENCES sources(id),
    imported_at TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    state_json TEXT NOT NULL CHECK (json_valid(state_json)),
    queue_json TEXT NOT NULL CHECK (json_valid(queue_json))
);
CREATE TABLE IF NOT EXISTS workflow_tasks (
    snapshot_id TEXT NOT NULL REFERENCES workflow_snapshots(id),
    task_id TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    owner_session_id TEXT,
    next_action TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    PRIMARY KEY (snapshot_id,task_id)
);
PRAGMA user_version = 1;
