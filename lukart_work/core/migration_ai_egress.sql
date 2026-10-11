-- Explicit additive migration for bounded, zero-cost AI egress authority.
-- Apply once as lw_core schema owner, never as the runtime role.
-- The only durable egress truth is reservation state; no CASE bytes or API keys.
CREATE TABLE lw_core.ai_egress_budgets (
    tenant_id uuid NOT NULL,
    provider_id text NOT NULL,
    account_hash text NOT NULL CHECK (account_hash ~ '^[0-9a-f]{64}$'),
    maximum_free_calls integer NOT NULL CHECK (maximum_free_calls BETWEEN 1 AND 10000),
    used_calls integer NOT NULL DEFAULT 0 CHECK (used_calls >= 0),
    reserved_calls integer NOT NULL DEFAULT 0 CHECK (reserved_calls >= 0),
    free_evidence_hash text NOT NULL CHECK (free_evidence_hash ~ '^[0-9a-f]{64}$'),
    verified_until timestamptz NOT NULL,
    revoked_at timestamptz,
    approved_by uuid NOT NULL,
    PRIMARY KEY (tenant_id,provider_id,account_hash),
    CHECK (used_calls + reserved_calls <= maximum_free_calls)
);
CREATE TABLE lw_core.ai_egress_grants (
    tenant_id uuid NOT NULL,
    case_id uuid NOT NULL,
    request_id uuid NOT NULL,
    reservation_id uuid NOT NULL,
    provider_id text NOT NULL,
    account_hash text NOT NULL,
    grant_json text NOT NULL,
    grant_hash text NOT NULL CHECK (grant_hash ~ '^[0-9a-f]{64}$'),
    consent_evidence_hash text NOT NULL CHECK (consent_evidence_hash ~ '^[0-9a-f]{64}$'),
    free_evidence_hash text NOT NULL CHECK (free_evidence_hash ~ '^[0-9a-f]{64}$'),
    issued_by uuid NOT NULL,
    issued_at timestamptz NOT NULL,
    consumed_at timestamptz,
    revoked_at timestamptz,
    PRIMARY KEY (tenant_id,case_id,request_id),
    UNIQUE (tenant_id,reservation_id),
    FOREIGN KEY (tenant_id,provider_id,account_hash)
        REFERENCES lw_core.ai_egress_budgets(tenant_id,provider_id,account_hash),
    FOREIGN KEY (tenant_id,case_id) REFERENCES lw_core.cases(tenant_id,case_id)
);
CREATE TRIGGER ai_egress_no_delete_budgets BEFORE DELETE
    ON lw_core.ai_egress_budgets FOR EACH ROW EXECUTE FUNCTION lw_core.immutable();
CREATE TRIGGER ai_egress_no_delete_grants BEFORE DELETE
    ON lw_core.ai_egress_grants FOR EACH ROW EXECUTE FUNCTION lw_core.immutable();
ALTER TABLE lw_core.ai_egress_budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE lw_core.ai_egress_budgets FORCE ROW LEVEL SECURITY;
CREATE POLICY ai_egress_budget_tenant ON lw_core.ai_egress_budgets
    USING (tenant_id::text=current_setting('lw.tenant',true))
    WITH CHECK (tenant_id::text=current_setting('lw.tenant',true));
ALTER TABLE lw_core.ai_egress_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE lw_core.ai_egress_grants FORCE ROW LEVEL SECURITY;
CREATE POLICY ai_egress_grant_scope ON lw_core.ai_egress_grants
    USING (tenant_id::text=current_setting('lw.tenant',true)
       AND case_id::text=current_setting('lw.case',true))
    WITH CHECK (tenant_id::text=current_setting('lw.tenant',true)
            AND case_id::text=current_setting('lw.case',true));
-- The existing migration runner grants SELECT/INSERT globally and
-- UPDATE only to the two narrow egress tables. Production requires the
-- same explicitly owner-applied grants before enabling this adapter.
