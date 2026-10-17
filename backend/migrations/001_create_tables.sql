-- Step 1.4 data model. Written to run on PostgreSQL (production) and on SQLite (tests and local work).
-- IDs are random UUIDs made by the app. Statuses and roles are checked by the database.

CREATE TABLE users (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('importer', 'clearing_agent', 'reviewer', 'admin')),
    failed_logins INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE shipments (
    id UUID PRIMARY KEY,
    reference TEXT NOT NULL,
    country TEXT NOT NULL DEFAULT 'TZ',
    owner_id UUID NOT NULL REFERENCES users (id),
    assigned_agent_id UUID REFERENCES users (id),
    status TEXT NOT NULL DEFAULT 'created' CHECK (status IN (
        'created', 'documents_uploaded', 'extracting', 'fields_ready',
        'confirmed', 'analysed', 'in_review', 'approved')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_shipments_owner ON shipments (owner_id);

CREATE TABLE documents (
    id UUID PRIMARY KEY,
    shipment_id UUID NOT NULL REFERENCES shipments (id),
    doc_type TEXT NOT NULL CHECK (doc_type IN ('commercial_invoice', 'packing_list', 'bill_of_lading')),
    file_path TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    uploaded_by UUID NOT NULL REFERENCES users (id),
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (shipment_id, doc_type)
);
CREATE INDEX idx_documents_shipment ON documents (shipment_id);

CREATE TABLE extractions (
    id UUID PRIMARY KEY,
    document_id UUID NOT NULL UNIQUE REFERENCES documents (id),
    schema_version TEXT NOT NULL,
    fields_extracted JSONB NOT NULL,
    fields_confirmed JSONB,
    confirmed_by UUID REFERENCES users (id),
    confirmed_at TIMESTAMPTZ,
    evolus_execution_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (fields_confirmed IS NULL AND confirmed_by IS NULL AND confirmed_at IS NULL)
        OR (fields_confirmed IS NOT NULL AND confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL))
);

CREATE TABLE analysis_runs (
    id UUID PRIMARY KEY,
    shipment_id UUID NOT NULL REFERENCES shipments (id),
    started_by UUID NOT NULL REFERENCES users (id),
    rule_pack_version TEXT NOT NULL,
    results JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_runs_shipment ON analysis_runs (shipment_id);

-- Note: the Step 1.4 column "values" is called values_json here, because VALUES is an SQL keyword.
CREATE TABLE findings (
    id UUID PRIMARY KEY,
    shipment_id UUID NOT NULL REFERENCES shipments (id),
    run_id UUID NOT NULL REFERENCES analysis_runs (id),
    check_id TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('high', 'medium', 'low')),
    document_a TEXT NOT NULL,
    document_b TEXT,
    field TEXT NOT NULL,
    values_json JSONB NOT NULL,
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'accepted')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_findings_shipment ON findings (shipment_id);
CREATE INDEX idx_findings_run ON findings (run_id);

CREATE TABLE agent_results (
    id UUID PRIMARY KEY,
    shipment_id UUID NOT NULL REFERENCES shipments (id),
    run_id UUID NOT NULL UNIQUE REFERENCES analysis_runs (id),
    summary TEXT,
    fix_list JSONB NOT NULL,
    needs_human BOOLEAN NOT NULL,
    reason TEXT,
    model_name TEXT,
    reply_valid BOOLEAN NOT NULL,
    retries INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE review_actions (
    id UUID PRIMARY KEY,
    shipment_id UUID NOT NULL REFERENCES shipments (id),
    finding_id UUID REFERENCES findings (id),
    user_id UUID NOT NULL REFERENCES users (id),
    action TEXT NOT NULL CHECK (action IN ('resolve', 'accept', 'reopen', 'approve')),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- approving a whole case has no finding; every other action is about one finding
    CHECK ((action = 'approve' AND finding_id IS NULL) OR (action <> 'approve' AND finding_id IS NOT NULL)),
    -- resolving or accepting needs a note
    CHECK (action NOT IN ('resolve', 'accept') OR (note IS NOT NULL AND length(trim(note)) > 0))
);
CREATE INDEX idx_review_finding ON review_actions (finding_id);

CREATE TABLE audit_events (
    id UUID PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    user_id UUID REFERENCES users (id),
    action TEXT NOT NULL,
    object_type TEXT,
    object_id TEXT,
    details JSONB
);
CREATE INDEX idx_audit_created ON audit_events (created_at);

CREATE TABLE evolus_calls (
    id UUID PRIMARY KEY,
    called_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    method TEXT NOT NULL,
    endpoint TEXT NOT NULL,
    shipment_id UUID REFERENCES shipments (id),
    document_id UUID REFERENCES documents (id),
    http_status INTEGER,
    duration_ms INTEGER NOT NULL,
    ok BOOLEAN NOT NULL,
    execution_id TEXT,
    error TEXT
);
CREATE INDEX idx_calls_shipment ON evolus_calls (shipment_id);
