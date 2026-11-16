CREATE TABLE units (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    unit_id INTEGER NOT NULL REFERENCES units,
    role TEXT NOT NULL CHECK(role IN ('ADMIN','SETTING','STERILIZATION','QC','WAREHOUSE','BORROWER','DECONTAMINATION','SUPERVISOR'))
);
CREATE TABLE instruments (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE templates (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    version INTEGER NOT NULL CHECK(version > 0),
    UNIQUE(name, version)
);
CREATE TABLE template_items (
    template_id INTEGER NOT NULL REFERENCES templates,
    instrument_id INTEGER NOT NULL REFERENCES instruments,
    expected INTEGER NOT NULL CHECK(expected >= 0),
    PRIMARY KEY(template_id, instrument_id)
) STRICT;
CREATE TABLE containers (
    id INTEGER PRIMARY KEY,
    label TEXT NOT NULL UNIQUE,
    qr TEXT NOT NULL UNIQUE,
    template_id INTEGER NOT NULL REFERENCES templates
);
CREATE TABLE cycles (
    id INTEGER PRIMARY KEY,
    container_id INTEGER NOT NULL REFERENCES containers,
    template_id INTEGER NOT NULL REFERENCES templates,
    sequence INTEGER NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('DRAFT','VERIFIED','PACKAGED','PROCESSING','QC_PENDING','AVAILABLE','REJECTED','QUARANTINED','EXPIRED','BORROWED','DIRTY_RECEIVED','DISCREPANCY','DECONTAMINATED')),
    created_by INTEGER NOT NULL REFERENCES users,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_by INTEGER REFERENCES users,
    verified_at TEXT,
    closed_at TEXT,
    UNIQUE(container_id, sequence),
    UNIQUE(id, container_id)
);
CREATE UNIQUE INDEX one_open_cycle ON cycles(container_id) WHERE closed_at IS NULL;
CREATE TABLE cycle_items (
    cycle_id INTEGER NOT NULL REFERENCES cycles,
    instrument_id INTEGER NOT NULL REFERENCES instruments,
    name TEXT NOT NULL,
    expected INTEGER NOT NULL CHECK(expected >= 0),
    verified INTEGER NOT NULL CHECK(verified >= 0),
    condition_note TEXT NOT NULL,
    PRIMARY KEY(cycle_id, instrument_id)
) STRICT;
CREATE TRIGGER no_snapshot_insert_after_verify BEFORE INSERT ON cycle_items
WHEN (SELECT state FROM cycles WHERE id = NEW.cycle_id) <> 'DRAFT'
BEGIN SELECT RAISE(ABORT, 'Snapshot is immutable'); END;
CREATE TRIGGER no_snapshot_update BEFORE UPDATE ON cycle_items
BEGIN SELECT RAISE(ABORT, 'Snapshot is immutable'); END;
CREATE TRIGGER no_snapshot_delete BEFORE DELETE ON cycle_items
BEGIN SELECT RAISE(ABORT, 'Snapshot is immutable'); END;
CREATE TRIGGER no_template_update_after_use BEFORE UPDATE ON template_items
WHEN EXISTS (SELECT 1 FROM cycles WHERE template_id = OLD.template_id OR template_id = NEW.template_id)
BEGIN SELECT RAISE(ABORT, 'Create a new template version'); END;
CREATE TRIGGER no_template_delete_after_use BEFORE DELETE ON template_items
WHEN EXISTS (SELECT 1 FROM cycles WHERE template_id = OLD.template_id)
BEGIN SELECT RAISE(ABORT, 'Create a new template version'); END;
CREATE TRIGGER no_template_insert_after_use BEFORE INSERT ON template_items
WHEN EXISTS (SELECT 1 FROM cycles WHERE template_id = NEW.template_id)
BEGIN SELECT RAISE(ABORT, 'Create a new template version'); END;
CREATE TABLE batches (
    id INTEGER PRIMARY KEY,
    reference TEXT NOT NULL UNIQUE,
    cycle_id INTEGER NOT NULL UNIQUE REFERENCES cycles,
    operator_id INTEGER NOT NULL REFERENCES users,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
CREATE TABLE qc_decisions (
    cycle_id INTEGER PRIMARY KEY REFERENCES cycles,
    outcome TEXT NOT NULL CHECK(outcome IN ('RELEASE','REJECT','QUARANTINE')),
    evidence TEXT NOT NULL,
    officer_id INTEGER NOT NULL REFERENCES users,
    decided_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE loans (
    id INTEGER PRIMARY KEY,
    unit_id INTEGER NOT NULL REFERENCES units,
    requester INTEGER NOT NULL REFERENCES users,
    state TEXT NOT NULL CHECK(state IN ('REQUESTED','PICKING','HANDED_OVER','RECEIVED','PARTIALLY_RETURNED','RETURNED','CANCELLED')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    handed_over_by INTEGER REFERENCES users,
    handed_over_at TEXT,
    received_by INTEGER REFERENCES users,
    received_at TEXT
);
CREATE TABLE loan_items (
    id INTEGER PRIMARY KEY,
    loan_id INTEGER NOT NULL REFERENCES loans,
    container_id INTEGER NOT NULL REFERENCES containers,
    cycle_id INTEGER NOT NULL,
    handed_at TEXT,
    returned_at TEXT,
    FOREIGN KEY(cycle_id, container_id) REFERENCES cycles(id, container_id),
    UNIQUE(loan_id, container_id),
    UNIQUE(id, loan_id, cycle_id)
);
CREATE UNIQUE INDEX one_active_loan ON loan_items(container_id) WHERE handed_at IS NOT NULL AND returned_at IS NULL;
CREATE TABLE returns (
    id INTEGER PRIMARY KEY,
    loan_id INTEGER NOT NULL REFERENCES loans,
    loan_item_id INTEGER NOT NULL UNIQUE,
    cycle_id INTEGER NOT NULL,
    received_by INTEGER NOT NULL REFERENCES users,
    received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(loan_item_id, loan_id, cycle_id) REFERENCES loan_items(id, loan_id, cycle_id),
    UNIQUE(id, cycle_id)
);
CREATE TABLE return_items (
    return_id INTEGER NOT NULL,
    cycle_id INTEGER NOT NULL,
    instrument_id INTEGER NOT NULL,
    expected INTEGER NOT NULL CHECK(expected >= 0),
    actual INTEGER NOT NULL CHECK(actual >= 0),
    condition_note TEXT NOT NULL,
    FOREIGN KEY(return_id, cycle_id) REFERENCES returns(id, cycle_id),
    FOREIGN KEY(cycle_id, instrument_id) REFERENCES cycle_items(cycle_id, instrument_id),
    PRIMARY KEY(return_id, instrument_id)
) STRICT;
CREATE TABLE discrepancy_cases (
    id INTEGER PRIMARY KEY,
    return_id INTEGER NOT NULL UNIQUE REFERENCES returns,
    status TEXT NOT NULL CHECK(status IN ('OPEN','INVESTIGATING','RESOLVED')),
    resolution TEXT,
    resolved_by INTEGER REFERENCES users,
    resolved_at TEXT
);
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY,
    case_id INTEGER NOT NULL UNIQUE REFERENCES discrepancy_cases,
    target_role TEXT NOT NULL DEFAULT 'SUPERVISOR',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE audit_events (
    id INTEGER PRIMARY KEY,
    actor_id INTEGER NOT NULL REFERENCES users,
    action TEXT NOT NULL,
    entity TEXT NOT NULL,
    entity_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    details TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'Audit is append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'Audit is append-only'); END;
CREATE TABLE idempotency (
    actor_id INTEGER NOT NULL REFERENCES users,
    idem_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    redirect_to TEXT NOT NULL,
    PRIMARY KEY(actor_id, idem_key)
);

