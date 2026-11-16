CREATE TABLE users_v1 (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    unit_id INTEGER NOT NULL REFERENCES units,
    role TEXT NOT NULL CHECK(role IN ('ADMIN','SETTING','STERILIZATION','QC','WAREHOUSE','BORROWER','DECONTAMINATION','SUPERVISOR'))
);
INSERT INTO users_v1
SELECT id, username, name, password_hash, unit_id,
       CASE role WHEN 'admin' THEN 'ADMIN' WHEN 'petugas_unit' THEN 'BORROWER'
                 WHEN 'supervisor' THEN 'SUPERVISOR'
                 ELSE CASE can_release_qc WHEN 1 THEN 'QC' ELSE 'SETTING' END END
FROM users;
DROP TABLE users;
ALTER TABLE users_v1 RENAME TO users;
CREATE TABLE notifications_replacement (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL UNIQUE REFERENCES discrepancy_cases,
    target_role TEXT NOT NULL DEFAULT 'SUPERVISOR',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO notifications_replacement
SELECT id, case_id, CASE WHEN target_role = 'supervisor' THEN 'SUPERVISOR' ELSE target_role END, created_at
FROM notifications;
DROP TABLE notifications;
ALTER TABLE notifications_replacement RENAME TO notifications;
ALTER TABLE audit_events DROP COLUMN actor_username;
