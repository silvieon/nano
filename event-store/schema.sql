CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    timestamp_unix_ms INTEGER NOT NULL,
    producer TEXT NOT NULL,
    schema_version INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    payload BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_task_sequence
ON events(task_id, sequence);
