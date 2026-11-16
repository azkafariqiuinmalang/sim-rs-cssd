-- The old schema cannot represent a shared batch or its evidence.
CREATE TEMP TABLE batch_rollback_guard (valid INTEGER CHECK(valid=1));
INSERT INTO batch_rollback_guard
SELECT CASE WHEN EXISTS (
    SELECT 1 FROM batches b LEFT JOIN batch_cycles bc ON bc.batch_id=b.id
    GROUP BY b.id HAVING COUNT(bc.cycle_id)<>1 OR MAX(b.process_evidence) IS NOT NULL
) THEN 0 ELSE 1 END;
DROP TABLE batch_rollback_guard;
CREATE TABLE batches_legacy (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE,
    cycle_id INTEGER NOT NULL UNIQUE REFERENCES cycles(id),
    operator_id INTEGER NOT NULL REFERENCES users(id),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
INSERT INTO batches_legacy(id,reference,cycle_id,operator_id,started_at,completed_at)
SELECT b.id,b.reference,bc.cycle_id,b.operator_id,b.started_at,b.completed_at
FROM batches b JOIN batch_cycles bc ON bc.batch_id=b.id;
DROP TABLE batch_cycles;
DROP TABLE batches;
ALTER TABLE batches_legacy RENAME TO batches;
