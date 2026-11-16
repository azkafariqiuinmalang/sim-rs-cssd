ALTER TABLE users DROP CONSTRAINT users_role_check;
ALTER TABLE users ADD COLUMN can_release_qc INTEGER NOT NULL DEFAULT 0 CHECK(can_release_qc IN (0,1));
UPDATE users
SET can_release_qc = CASE WHEN role = 'QC' THEN 1 ELSE 0 END,
    role = CASE role WHEN 'ADMIN' THEN 'admin' WHEN 'BORROWER' THEN 'petugas_unit'
                     WHEN 'SUPERVISOR' THEN 'supervisor' ELSE 'petugas_cssd' END;
ALTER TABLE users ADD CONSTRAINT users_role_check CHECK(role IN ('admin','petugas_cssd','petugas_unit','supervisor'));
ALTER TABLE users ADD CONSTRAINT users_qc_role_check CHECK(can_release_qc = 0 OR role = 'petugas_cssd');
UPDATE notifications SET target_role = 'supervisor' WHERE target_role = 'SUPERVISOR';
ALTER TABLE notifications ALTER COLUMN target_role SET DEFAULT 'supervisor';
ALTER TABLE audit_events ADD COLUMN actor_username TEXT;
