CREATE SCHEMA IF NOT EXISTS thesis_ledger;
REVOKE ALL ON SCHEMA thesis_ledger FROM PUBLIC, anon, authenticated, service_role;

CREATE TABLE thesis_ledger.records (
    workspace text NOT NULL,
    kind text NOT NULL CHECK (kind IN ('run', 'memory', 'revision')),
    id text NOT NULL,
    created text NOT NULL,
    payload jsonb NOT NULL,
    PRIMARY KEY (workspace, kind, id)
);
CREATE INDEX records_by_creation
    ON thesis_ledger.records (workspace, kind, created DESC);
ALTER TABLE thesis_ledger.records ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON thesis_ledger.records FROM PUBLIC, anon, authenticated, service_role;

CREATE ROLE thesis_ledger_app NOLOGIN;
GRANT USAGE ON SCHEMA thesis_ledger TO thesis_ledger_app;
GRANT SELECT, INSERT, UPDATE ON thesis_ledger.records TO thesis_ledger_app;
CREATE POLICY application_records ON thesis_ledger.records
    FOR ALL TO thesis_ledger_app USING (true) WITH CHECK (true);
