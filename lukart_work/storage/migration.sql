CREATE SCHEMA lw_storage;
REVOKE ALL ON SCHEMA lw_storage FROM PUBLIC;
CREATE TABLE lw_storage.artifacts (
 tenant_id uuid NOT NULL, case_id uuid NOT NULL, artifact_id uuid NOT NULL,
 category text NOT NULL, name text NOT NULL, version text NOT NULL,
 content_hash text NOT NULL, byte_length bigint NOT NULL CHECK (byte_length >= 0),
 policy text NOT NULL, retain_until timestamptz NOT NULL,
 created_at timestamptz NOT NULL, actor_id uuid NOT NULL,
 PRIMARY KEY (tenant_id,case_id,artifact_id),
 UNIQUE (tenant_id,case_id,category,name,version),
 FOREIGN KEY (tenant_id,case_id) REFERENCES lw_core.cases
);
CREATE TABLE lw_storage.blobs (
 tenant_id uuid NOT NULL, case_id uuid NOT NULL, artifact_id uuid NOT NULL, data bytea NOT NULL,
 PRIMARY KEY (tenant_id,case_id,artifact_id),
 FOREIGN KEY (tenant_id,case_id,artifact_id) REFERENCES lw_storage.artifacts
);
CREATE TABLE lw_storage.holds (
 tenant_id uuid NOT NULL, case_id uuid NOT NULL, artifact_id uuid NOT NULL,
 held boolean NOT NULL, recorded_at timestamptz NOT NULL, actor_id uuid NOT NULL,
 entry_order bigint GENERATED ALWAYS AS IDENTITY,
 PRIMARY KEY (tenant_id,case_id,artifact_id,entry_order),
 FOREIGN KEY (tenant_id,case_id,artifact_id) REFERENCES lw_storage.artifacts
);
CREATE TABLE lw_storage.tombstones (
 tenant_id uuid NOT NULL, case_id uuid NOT NULL, artifact_id uuid NOT NULL,
 deleted_at timestamptz NOT NULL, actor_id uuid NOT NULL, content_hash text NOT NULL,
 PRIMARY KEY (tenant_id,case_id,artifact_id),
 FOREIGN KEY (tenant_id,case_id,artifact_id) REFERENCES lw_storage.artifacts
);
CREATE FUNCTION lw_storage.guard_blob() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' THEN RAISE EXCEPTION 'immutable bytes' USING ERRCODE='23000'; END IF;
 IF NOT EXISTS (SELECT 1 FROM lw_storage.tombstones t WHERE
  (t.tenant_id,t.case_id,t.artifact_id)=(OLD.tenant_id,OLD.case_id,OLD.artifact_id)) THEN
  RAISE EXCEPTION 'retention tombstone required' USING ERRCODE='23000';
 END IF;
 RETURN OLD;
END $$;
CREATE TRIGGER guarded_blob BEFORE UPDATE OR DELETE ON lw_storage.blobs
 FOR EACH ROW EXECUTE FUNCTION lw_storage.guard_blob();
CREATE FUNCTION lw_storage.guard_delete() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item lw_storage.artifacts; active_hold boolean;
BEGIN
 SELECT * INTO STRICT item FROM lw_storage.artifacts WHERE
  (tenant_id,case_id,artifact_id)=(NEW.tenant_id,NEW.case_id,NEW.artifact_id);
 SELECT held INTO active_hold FROM lw_storage.holds WHERE
  (tenant_id,case_id,artifact_id)=(NEW.tenant_id,NEW.case_id,NEW.artifact_id)
  ORDER BY entry_order DESC LIMIT 1;
 IF item.retain_until > clock_timestamp() OR coalesce(active_hold,false)
  OR NEW.content_hash <> item.content_hash THEN
  RAISE EXCEPTION 'retention denied' USING ERRCODE='23000';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER retention_gate BEFORE INSERT ON lw_storage.tombstones
 FOR EACH ROW EXECUTE FUNCTION lw_storage.guard_delete();
CREATE FUNCTION lw_storage.guard_insert_blob() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS (SELECT 1 FROM lw_storage.tombstones WHERE
  (tenant_id,case_id,artifact_id)=(NEW.tenant_id,NEW.case_id,NEW.artifact_id)) THEN
  RAISE EXCEPTION 'deleted artifact' USING ERRCODE='23000';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER no_resurrection BEFORE INSERT ON lw_storage.blobs
 FOR EACH ROW EXECUTE FUNCTION lw_storage.guard_insert_blob();
DO $$ DECLARE name text; BEGIN
 FOREACH name IN ARRAY ARRAY['artifacts','holds','tombstones'] LOOP
  EXECUTE format('CREATE TRIGGER immutable_record BEFORE UPDATE OR DELETE ON lw_storage.%I FOR EACH ROW EXECUTE FUNCTION lw_core.immutable()',name);
 END LOOP;
 FOREACH name IN ARRAY ARRAY['artifacts','blobs','holds','tombstones'] LOOP
  EXECUTE format('ALTER TABLE lw_storage.%I ENABLE ROW LEVEL SECURITY',name);
  EXECUTE format('ALTER TABLE lw_storage.%I FORCE ROW LEVEL SECURITY',name);
  EXECUTE format('CREATE POLICY scoped ON lw_storage.%I USING (tenant_id::text=current_setting(''lw.tenant'',true) AND case_id::text=current_setting(''lw.case'',true)) WITH CHECK (tenant_id::text=current_setting(''lw.tenant'',true) AND case_id::text=current_setting(''lw.case'',true))',name);
 END LOOP;
END $$;
