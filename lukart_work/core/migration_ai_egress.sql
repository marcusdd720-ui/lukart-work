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
    revoked_by uuid,
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
    consumed_by uuid,
    revoked_at timestamptz,
    revoked_by uuid,
    PRIMARY KEY (tenant_id,case_id,request_id),
    UNIQUE (tenant_id,reservation_id),
    FOREIGN KEY (tenant_id,provider_id,account_hash)
        REFERENCES lw_core.ai_egress_budgets(tenant_id,provider_id,account_hash),
    FOREIGN KEY (tenant_id,case_id) REFERENCES lw_core.cases(tenant_id,case_id),
    CHECK ((consumed_at IS NULL) = (consumed_by IS NULL)),
    CHECK ((revoked_at IS NULL) = (revoked_by IS NULL))
);

-- Runtime can only perform monotonic, one-way state transitions. The
-- original consent/pricing identities and issuance remain immutable.
CREATE FUNCTION lw_core.ai_egress_immutable_identity()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'ai_egress_budgets' THEN
        IF ROW(NEW.tenant_id,NEW.provider_id,NEW.account_hash,
               NEW.maximum_free_calls,NEW.free_evidence_hash,
               NEW.verified_until,NEW.approved_by)
           IS DISTINCT FROM
           ROW(OLD.tenant_id,OLD.provider_id,OLD.account_hash,
               OLD.maximum_free_calls,OLD.free_evidence_hash,
               OLD.verified_until,OLD.approved_by)
           OR NEW.used_calls < OLD.used_calls
           OR NEW.used_calls > OLD.used_calls + 1
           OR NEW.reserved_calls NOT BETWEEN OLD.reserved_calls - 1
                                         AND OLD.reserved_calls + 1
           OR (NEW.used_calls = OLD.used_calls + 1
               AND NEW.reserved_calls <> OLD.reserved_calls - 1)
           OR (NEW.used_calls = OLD.used_calls
               AND NEW.reserved_calls = OLD.reserved_calls
               AND NEW.revoked_at IS NOT DISTINCT FROM OLD.revoked_at)
        THEN
            RAISE EXCEPTION 'immutable egress budget' USING ERRCODE='23000';
        END IF;
        IF OLD.revoked_at IS NOT NULL AND
           ROW(NEW.revoked_at,NEW.revoked_by)
           IS DISTINCT FROM ROW(OLD.revoked_at,OLD.revoked_by)
        THEN
            RAISE EXCEPTION 'revocation immutable' USING ERRCODE='23000';
        END IF;
        IF (NEW.revoked_at IS NULL) <> (NEW.revoked_by IS NULL) OR
           (NEW.revoked_at IS NOT NULL AND NEW.revoked_by IS NULL)
        THEN
            RAISE EXCEPTION 'invalid revocation' USING ERRCODE='23000';
        END IF;
    ELSE
        IF ROW(NEW.tenant_id,NEW.case_id,NEW.request_id,NEW.reservation_id,
               NEW.provider_id,NEW.account_hash,NEW.grant_json,NEW.grant_hash,
               NEW.consent_evidence_hash,NEW.free_evidence_hash,
               NEW.issued_by,NEW.issued_at)
           IS DISTINCT FROM
           ROW(OLD.tenant_id,OLD.case_id,OLD.request_id,OLD.reservation_id,
               OLD.provider_id,OLD.account_hash,OLD.grant_json,OLD.grant_hash,
               OLD.consent_evidence_hash,OLD.free_evidence_hash,
               OLD.issued_by,OLD.issued_at)
        THEN
            RAISE EXCEPTION 'immutable egress grant' USING ERRCODE='23000';
        END IF;
        IF OLD.consumed_at IS NOT NULL AND
           ROW(NEW.consumed_at,NEW.consumed_by)
           IS DISTINCT FROM ROW(OLD.consumed_at,OLD.consumed_by)
        THEN
            RAISE EXCEPTION 'consumption immutable' USING ERRCODE='23000';
        END IF;
        IF OLD.revoked_at IS NOT NULL AND
           ROW(NEW.revoked_at,NEW.revoked_by)
           IS DISTINCT FROM ROW(OLD.revoked_at,OLD.revoked_by)
        THEN
            RAISE EXCEPTION 'revocation immutable' USING ERRCODE='23000';
        END IF;
        IF (NEW.consumed_at IS NULL) <> (NEW.consumed_by IS NULL) OR
           (NEW.revoked_at IS NULL) <> (NEW.revoked_by IS NULL) OR
           ROW(NEW.consumed_at,NEW.consumed_by,NEW.revoked_at,NEW.revoked_by)
           IS NOT DISTINCT FROM
           ROW(OLD.consumed_at,OLD.consumed_by,OLD.revoked_at,OLD.revoked_by)
        THEN
            RAISE EXCEPTION 'invalid grant transition' USING ERRCODE='23000';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER ai_egress_monotonic_budget
    BEFORE UPDATE ON lw_core.ai_egress_budgets FOR EACH ROW
    EXECUTE FUNCTION lw_core.ai_egress_immutable_identity();
CREATE TRIGGER ai_egress_monotonic_grant
    BEFORE UPDATE ON lw_core.ai_egress_grants FOR EACH ROW
    EXECUTE FUNCTION lw_core.ai_egress_immutable_identity();
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
-- After applying this owner-only migration, use
-- lukart_work.storage.migrations.configure_egress_roles(owner_connection,
-- runtime_role, host_role). The ordinary runtime role gets SELECT only.
-- Only the isolated NOINHERIT host receives INSERT and column-bounded
-- UPDATE on the two egress tables; never grant egress writes to runtime.
