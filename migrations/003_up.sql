ALTER TABLE loans ADD COLUMN needed_at TEXT;
ALTER TABLE loans ADD COLUMN prepared_cycle_id INTEGER REFERENCES cycles(id);
CREATE TABLE loan_needs (
    loan_id INTEGER NOT NULL REFERENCES loans(id),
    kind TEXT NOT NULL CHECK(kind IN ('set', 'piece', 'custom')),
    item_name TEXT NOT NULL,
    instrument_id INTEGER REFERENCES instruments(id),
    quantity INTEGER NOT NULL CHECK(quantity > 0 AND quantity <= 99999),
    CHECK((kind = 'set' AND instrument_id IS NULL) OR (kind <> 'set' AND instrument_id IS NOT NULL)),
    PRIMARY KEY(loan_id, kind, item_name)
);
CREATE INDEX loans_unit_history ON loans(unit_id, id);
CREATE INDEX loans_state_queue ON loans(state, id);
CREATE UNIQUE INDEX loans_prepared_cycle ON loans(prepared_cycle_id) WHERE prepared_cycle_id IS NOT NULL;
