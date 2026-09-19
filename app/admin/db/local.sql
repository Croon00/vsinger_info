PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS import_batches (
 id TEXT PRIMARY KEY,
 name TEXT NOT NULL,
 batch_kind TEXT NOT NULL,
 status TEXT NOT NULL,
 target_catalog_id TEXT,
 notes TEXT,
 revision INTEGER NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS input_files (
 id TEXT PRIMARY KEY,
 batch_id TEXT NOT NULL,
 relative_path TEXT NOT NULL,
 file_hash TEXT NOT NULL,
 byte_size INTEGER NOT NULL,
 schema_version TEXT,
 snapshot_path TEXT NOT NULL,
 parse_status TEXT NOT NULL,
 error_message TEXT,
 imported_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(batch_id) REFERENCES import_batches(id),
 UNIQUE(batch_id,file_hash)
);
CREATE TABLE IF NOT EXISTS draft_entities (
 id TEXT PRIMARY KEY,
 batch_id TEXT NOT NULL,
 input_file_id TEXT,
 client_ref TEXT NOT NULL,
 entity_type TEXT NOT NULL,
 operation TEXT NOT NULL,
 target_id INTEGER,
 expected_version INTEGER,
 original_payload TEXT NOT NULL,
 current_payload TEXT NOT NULL,
 provenance TEXT NOT NULL,
 revision INTEGER NOT NULL,
 status TEXT NOT NULL,
 approved_revision INTEGER,
 approved_hash TEXT,
 approved_at TEXT,
 review_note TEXT,
 ai_confidence REAL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(batch_id) REFERENCES import_batches(id),
 FOREIGN KEY(input_file_id) REFERENCES input_files(id),
 UNIQUE(batch_id,client_ref)
);
CREATE TABLE IF NOT EXISTS draft_relations (
 id TEXT PRIMARY KEY,
 source_draft_id TEXT NOT NULL,
 field_path TEXT NOT NULL,
 target_type TEXT NOT NULL,
 target_draft_id TEXT,
 target_catalog_id TEXT,
 target_entity_id INTEGER,
 unresolved_ref TEXT,
 is_required INTEGER NOT NULL,
 source_revision INTEGER NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(source_draft_id) REFERENCES draft_entities(id),
 FOREIGN KEY(target_draft_id) REFERENCES draft_entities(id),
 UNIQUE(source_draft_id,field_path)
);
CREATE TABLE IF NOT EXISTS review_events (
 id TEXT PRIMARY KEY,
 draft_id TEXT NOT NULL,
 action TEXT NOT NULL,
 actor_label TEXT NOT NULL,
 revision INTEGER NOT NULL,
 payload_hash TEXT,
 change_data TEXT NOT NULL,
 note TEXT,
 created_at TEXT NOT NULL,
 FOREIGN KEY(draft_id) REFERENCES draft_entities(id)
);
CREATE TABLE IF NOT EXISTS validation_issues (
 id TEXT PRIMARY KEY,
 batch_id TEXT NOT NULL,
 draft_id TEXT,
 input_file_id TEXT,
 checked_revision INTEGER,
 field_path TEXT,
 severity TEXT NOT NULL,
 code TEXT NOT NULL,
 message TEXT NOT NULL,
 status TEXT NOT NULL,
 resolution_note TEXT,
 resolved_at TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(batch_id) REFERENCES import_batches(id),
 FOREIGN KEY(draft_id) REFERENCES draft_entities(id),
 FOREIGN KEY(input_file_id) REFERENCES input_files(id)
);
CREATE TABLE IF NOT EXISTS publish_plans (
 id TEXT PRIMARY KEY,
 batch_id TEXT NOT NULL,
 operation_id TEXT NOT NULL,
 target_catalog_id TEXT NOT NULL,
 expected_schema_version TEXT NOT NULL,
 manifest_payload TEXT NOT NULL,
 manifest_hash TEXT NOT NULL,
 status TEXT NOT NULL,
 frozen_at TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(batch_id) REFERENCES import_batches(id),
 UNIQUE(operation_id)
);
CREATE TABLE IF NOT EXISTS publish_attempts (
 id TEXT PRIMARY KEY,
 plan_id TEXT NOT NULL,
 attempt_number INTEGER NOT NULL,
 state TEXT NOT NULL,
 started_at TEXT NOT NULL,
 finished_at TEXT,
 remote_import_id INTEGER,
 error_code TEXT,
 error_message TEXT,
 remote_result TEXT,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(plan_id) REFERENCES publish_plans(id),
 UNIQUE(plan_id,attempt_number)
);
CREATE TABLE IF NOT EXISTS remote_id_map (
 id TEXT PRIMARY KEY,
 draft_id TEXT NOT NULL,
 target_catalog_id TEXT NOT NULL,
 entity_type TEXT NOT NULL,
 entity_id INTEGER NOT NULL,
 remote_version INTEGER,
 operation_id TEXT NOT NULL,
 mapped_at TEXT NOT NULL,
 created_at TEXT NOT NULL,
 updated_at TEXT NOT NULL,
 FOREIGN KEY(draft_id) REFERENCES draft_entities(id),
 UNIQUE(draft_id,target_catalog_id,entity_type,entity_id)
);
CREATE INDEX IF NOT EXISTS draft_batch_status ON draft_entities(batch_id,status,created_at);
CREATE INDEX IF NOT EXISTS review_draft ON review_events(draft_id,created_at);
