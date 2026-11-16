DROP INDEX loans_prepared_cycle;
DROP INDEX loans_state_queue;
DROP INDEX loans_unit_history;
DROP TABLE loan_needs;
ALTER TABLE loans DROP COLUMN prepared_cycle_id;
ALTER TABLE loans DROP COLUMN needed_at;
