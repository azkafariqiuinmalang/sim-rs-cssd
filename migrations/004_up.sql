ALTER TABLE batches RENAME TO batches_legacy;
CREATE TABLE batches (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE,
    operator_id INTEGER NOT NULL REFERENCES users(id),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    process_evidence TEXT
);
INSERT INTO batches(id, reference, operator_id, started_at, completed_at)
SELECT id, reference, operator_id, started_at, completed_at FROM batches_legacy;
CREATE TABLE batch_cycles (
    cycle_id INTEGER PRIMARY KEY REFERENCES cycles(id),
    batch_id INTEGER NOT NULL REFERENCES batches(id)
);
CREATE INDEX batch_cycles_batch ON batch_cycles(batch_id);
INSERT INTO batch_cycles(cycle_id,batch_id) SELECT cycle_id,id FROM batches_legacy;

DROP TABLE batches_legacy;
