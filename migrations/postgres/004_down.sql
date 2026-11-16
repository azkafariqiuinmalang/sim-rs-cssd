DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM batches b LEFT JOIN batch_cycles bc ON bc.batch_id=b.id
        GROUP BY b.id HAVING COUNT(bc.cycle_id)<>1 OR MAX(b.process_evidence) IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'Batch bersama atau bukti proses tidak dapat disimpan di skema lama';
    END IF;
END $$;
ALTER TABLE batches ADD COLUMN cycle_id INTEGER UNIQUE REFERENCES cycles(id);
UPDATE batches b SET cycle_id=bc.cycle_id FROM batch_cycles bc WHERE bc.batch_id=b.id;
ALTER TABLE batches ALTER COLUMN cycle_id SET NOT NULL;
ALTER TABLE batches DROP COLUMN process_evidence;
DROP TABLE batch_cycles;
