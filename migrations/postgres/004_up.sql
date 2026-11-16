CREATE TABLE batch_cycles (
    cycle_id INTEGER PRIMARY KEY REFERENCES cycles(id),
    batch_id INTEGER NOT NULL REFERENCES batches(id)
);
CREATE INDEX batch_cycles_batch ON batch_cycles(batch_id);
INSERT INTO batch_cycles(cycle_id,batch_id) SELECT cycle_id,id FROM batches;

ALTER TABLE batches DROP COLUMN cycle_id;
ALTER TABLE batches ADD COLUMN process_evidence TEXT;
