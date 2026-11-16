CREATE TABLE users_v2 (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    unit_id INTEGER NOT NULL REFERENCES units,
    role TEXT NOT NULL CHECK(role IN ('admin','petugas_cssd','petugas_unit','supervisor')),
    can_release_qc INTEGER NOT NULL DEFAULT 0 CHECK(can_release_qc IN (0,1)),
    CHECK(can_release_qc = 0 OR role = 'petugas_cssd')
);
INSERT INTO users_v2
SELECT id, username, name, password_hash, unit_id,
       CASE role WHEN 'ADMIN' THEN 'admin' WHEN 'BORROWER' THEN 'petugas_unit'
                 WHEN 'SUPERVISOR' THEN 'supervisor' ELSE 'petugas_cssd' END,
       CASE WHEN role = 'QC' THEN 1 ELSE 0 END
FROM users;
DROP TABLE users;
ALTER TABLE users_v2 RENAME TO users;
CREATE TABLE notifications_replacement (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL UNIQUE REFERENCES discrepancy_cases,
    target_role TEXT NOT NULL DEFAULT 'supervisor',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO notifications_replacement
SELECT id, case_id, CASE WHEN target_role = 'SUPERVISOR' THEN 'supervisor' ELSE target_role END, created_at
FROM notifications;
DROP TABLE notifications;
ALTER TABLE notifications_replacement RENAME TO notifications;
ALTER TABLE audit_events ADD COLUMN actor_username TEXT;
