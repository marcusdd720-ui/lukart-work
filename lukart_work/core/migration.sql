-- Run once as schema owner in a dedicated database. Never as the runtime role.
CREATE SCHEMA lw_core;
REVOKE ALL ON SCHEMA lw_core FROM PUBLIC;
CREATE TABLE lw_core.cases (
    tenant_id uuid NOT NULL, case_id uuid NOT NULL, sequence bigint NOT NULL CHECK (sequence > 0),
    PRIMARY KEY (tenant_id,case_id)
);
CREATE TABLE lw_core.revisions (
    tenant_id uuid NOT NULL, case_id uuid NOT NULL, revision_key text NOT NULL,
    kind text NOT NULL, entity_id uuid NOT NULL, revision bigint NOT NULL CHECK (revision > 0),
    contract text NOT NULL, payload text NOT NULL, content_hash text NOT NULL,
    PRIMARY KEY (tenant_id,case_id,revision_key),
    UNIQUE (tenant_id,case_id,kind,entity_id,revision),
    FOREIGN KEY (tenant_id,case_id) REFERENCES lw_core.cases
);
CREATE TABLE lw_core.heads (
    tenant_id uuid NOT NULL, case_id uuid NOT NULL, kind text NOT NULL, entity_id uuid NOT NULL, revision_key text NOT NULL,
    PRIMARY KEY (tenant_id,case_id,kind,entity_id),
    FOREIGN KEY (tenant_id,case_id,revision_key) REFERENCES lw_core.revisions
);
CREATE TABLE lw_core.objects (
    tenant_id uuid NOT NULL, case_id uuid NOT NULL, category text NOT NULL, object_id uuid NOT NULL,
    contract text NOT NULL, payload text NOT NULL, content_hash text NOT NULL, original_bytes bytea,
    PRIMARY KEY (tenant_id,case_id,category,object_id),
    FOREIGN KEY (tenant_id,case_id) REFERENCES lw_core.cases
);
CREATE TABLE lw_core.commands (
    tenant_id uuid NOT NULL, case_id uuid NOT NULL, idempotency_key uuid NOT NULL,
    input_hash text NOT NULL, contract text NOT NULL, payload text NOT NULL, content_hash text NOT NULL,
    PRIMARY KEY (tenant_id,case_id,idempotency_key),
    FOREIGN KEY (tenant_id,case_id) REFERENCES lw_core.cases
);
CREATE TABLE lw_core.events (
    tenant_id uuid NOT NULL, case_id uuid NOT NULL, event_id uuid NOT NULL, sequence bigint NOT NULL,
    contract text NOT NULL, payload text NOT NULL, content_hash text NOT NULL,
    event_order bigint GENERATED ALWAYS AS IDENTITY,
    PRIMARY KEY (tenant_id,case_id,event_id),
    FOREIGN KEY (tenant_id,case_id) REFERENCES lw_core.cases
);
CREATE TABLE lw_core.outbox (
    tenant_id uuid NOT NULL, case_id uuid NOT NULL, event_id uuid NOT NULL,
    PRIMARY KEY (tenant_id,case_id,event_id),
    FOREIGN KEY (tenant_id,case_id,event_id) REFERENCES lw_core.events
);
CREATE FUNCTION lw_core.immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'immutable record' USING ERRCODE='23000'; END $$;
DO $$ DECLARE name text; BEGIN
    FOREACH name IN ARRAY ARRAY['revisions','objects','commands','events'] LOOP
        EXECUTE format('CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON lw_core.%I FOR EACH ROW EXECUTE FUNCTION lw_core.immutable()',name);
    END LOOP;
    FOREACH name IN ARRAY ARRAY['cases','revisions','heads','objects','commands','events','outbox'] LOOP
        EXECUTE format('ALTER TABLE lw_core.%I ENABLE ROW LEVEL SECURITY', name);
        EXECUTE format('ALTER TABLE lw_core.%I FORCE ROW LEVEL SECURITY', name);
        EXECUTE format('CREATE POLICY scoped ON lw_core.%I USING (tenant_id::text=current_setting(''lw.tenant'',true) AND case_id::text=current_setting(''lw.case'',true)) WITH CHECK (tenant_id::text=current_setting(''lw.tenant'',true) AND case_id::text=current_setting(''lw.case'',true))',name);
    END LOOP;
END $$;
