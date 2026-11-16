SET LOCAL search_path TO cssd_app, pg_catalog;

DROP TABLE idempotency;
DROP TABLE notifications;
DROP TABLE discrepancy_cases;
DROP TABLE return_items;
DROP TABLE returns;
DROP TABLE loan_items;
DROP TABLE loans;
DROP TABLE qc_decisions;
DROP TABLE batches;
DROP TABLE cycle_items;
DROP TABLE cycles;
DROP TABLE containers;
DROP TABLE template_items;
DROP TABLE templates;
DROP TABLE instruments;
DROP TABLE audit_events;
DROP TABLE users;
DROP TABLE units;

DROP TABLE schema_migrations;
DROP FUNCTION protect_snapshot();
DROP FUNCTION protect_template();
DROP FUNCTION protect_audit();
DROP SCHEMA cssd_app;
