ALTER TABLE users DROP CONSTRAINT users_role_check, DROP CONSTRAINT users_qc_role_check;
UPDATE users SET role = CASE role WHEN 'admin' THEN 'ADMIN' WHEN 'petugas_unit' THEN 'BORROWER'
    WHEN 'supervisor' THEN 'SUPERVISOR' ELSE CASE can_release_qc WHEN 1 THEN 'QC' ELSE 'SETTING' END END;
ALTER TABLE users DROP COLUMN can_release_qc;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK(role IN ('ADMIN','SETTING','STERILIZATION','QC','WAREHOUSE','BORROWER','DECONTAMINATION','SUPERVISOR'));
UPDATE notifications SET target_role = 'SUPERVISOR' WHERE target_role = 'supervisor';
ALTER TABLE notifications ALTER COLUMN target_role SET DEFAULT 'SUPERVISOR';
ALTER TABLE audit_events DROP COLUMN actor_username;
