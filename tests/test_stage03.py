"""Synthetic storage acceptance on real PostgreSQL, including upgrade and restore."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from tests import test_stage02 as core
from lukart_work.core.postgres import PostgresRepository
from lukart_work.core.security import Principal, TokenAuthority
from lukart_work.core.service import CommandService
from lukart_work.domain.models import Actor
from lukart_work.contracts.messages import DomainError
from lukart_work.storage.migrations import migrate, grant_runtime
from lukart_work.storage.objects import ObjectStore, RetentionPolicies, ArtifactRecord, CATEGORIES
from lukart_work.storage.service import StorageService
from lukart_work.storage.backup import backup, restore_test_database
from lukart_work.validation.rules import Violation

ROOT = Path(__file__).resolve().parents[1]
ADMIN = core.ADMIN
STORAGE_ACTIONS = frozenset(('StorageRead','StorageWrite','StorageHold','StorageDelete'))


def fresh_database():
    name = 'lukart_stage03_test_' + uuid4().hex
    with psycopg.connect(ADMIN, autocommit=True) as c:
        c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    return make_conninfo(ADMIN, dbname=name), make_conninfo(core.DSN, dbname=name)


def raw_state(dsn):
    result = {}
    with psycopg.connect(dsn) as c:
        for schema in ('lw_core', 'lw_storage', 'lw_migrations'):
            tables = c.execute('SELECT tablename FROM pg_tables WHERE schemaname=%s ORDER BY tablename', (schema,)).fetchall()
            for (table,) in tables:
                rows = c.execute(sql.SQL('SELECT * FROM {}.{}').format(sql.Identifier(schema),sql.Identifier(table))).fetchall()
                result[schema + '.' + table] = sorted(rows, key=repr)
    return result


@unittest.skipUnless(ADMIN and core.DSN, 'PostgreSQL storage acceptance requires isolated admin/runtime DSNs')
class Stage03Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.admin, cls.dsn = fresh_database()
        with psycopg.connect(cls.admin) as c:
            migrate(c)
            grant_runtime(c, 'lw_core_runtime')

    def setUp(self):
        self.tenant, self.case_id = uuid4(), uuid4()
        self.actor = Actor(id=uuid4(), kind='HUMAN')
        self.authority = TokenAuthority()
        self.principal = Principal(self.actor, self.tenant, self.case_id, core.ACTIONS | STORAGE_ACTIONS)
        self.token = self.authority.provision(self.principal)
        self.repo = PostgresRepository(self.dsn, storage=True, retention_policies=RetentionPolicies([(core.PIN, 0)]))
        self.service = CommandService(self.repo, self.authority)
        self.storage = StorageService(self.repo, self.authority)
        self.sequence = 0
        self.create_case()

    def put(self, category='raw_output', name='synthetic', version='1', data=b'\x00raw\r\n\xff'):
        result = self.storage.put(self.token, category, name, version, data, core.PIN)
        self.assertIsInstance(result, ArtifactRecord, result)
        return result

    def test_versions_original_bytes_and_process_restart(self):
        for category in sorted(CATEGORIES):
            one = self.put(category)
            self.assertEqual(self.storage.read(self.token, one.artifact_id), b'\x00raw\r\n\xff')
            self.assertEqual(one, self.put(category))
            two = self.put(category, version='2', data=b'new')
            self.assertNotEqual(one.artifact_id, two.artifact_id)
            error = self.storage.put(self.token, category, 'synthetic', '1', b'changed', core.PIN)
            self.assertEqual(error.code, 'CONFLICT')
        env = dict(os.environ, LUKART_RESTART_DSN=self.dsn, LUKART_RESTART_TENANT=str(self.tenant),
                   LUKART_RESTART_CASE=str(self.case_id), LUKART_RESTART_ARTIFACT=str(one.artifact_id))
        script = "import os; from uuid import UUID; from lukart_work.core.postgres import PostgresRepository; from lukart_work.storage.objects import ObjectStore; r=PostgresRepository(os.environ['LUKART_RESTART_DSN']);\nwith r.transaction(UUID(os.environ['LUKART_RESTART_TENANT']),UUID(os.environ['LUKART_RESTART_CASE'])) as tx: assert ObjectStore(tx).read(UUID(os.environ['LUKART_RESTART_ARTIFACT'])) == b'\\x00raw\\r\\n\\xff'"
        run = subprocess.run([sys.executable, '-B', '-c', script], env=env, cwd=ROOT, capture_output=True)
        self.assertEqual(run.returncode, 0, 'Restart probe failed (output suppressed to protect DSN)')

    def test_isolation_authorization_and_sql_rls(self):
        item = self.put()
        alien = self.authority.provision(Principal(self.actor, uuid4(), uuid4(), STORAGE_ACTIONS))
        self.assertIsInstance(self.storage.read(alien, item.artifact_id), DomainError)
        denied = self.authority.provision(Principal(self.actor, self.tenant, self.case_id, frozenset()))
        for result in (self.storage.read(denied,item.artifact_id), self.storage.delete(denied,item.artifact_id), self.storage.hold(denied,item.artifact_id,True)):
            self.assertEqual(result.code, 'FORBIDDEN')
        with self.repo.transaction(uuid4(), uuid4()) as tx:
            self.assertEqual(tx.connection.execute('SELECT * FROM lw_storage.artifacts').fetchall(), [])
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                tx.connection.execute('INSERT INTO lw_storage.blobs VALUES (%s,%s,%s,%s)', (self.tenant,self.case_id,uuid4(),b'foreign'))

    def test_retention_hold_tombstone_and_no_resurrection(self):
        item = self.put()
        self.storage.hold(self.token,item.artifact_id,True)
        self.assertEqual(self.storage.delete(self.token,item.artifact_id).code,'GATE_DENIED')
        self.storage.hold(self.token,item.artifact_id,False)
        deleted = self.storage.delete(self.token,item.artifact_id)
        self.assertEqual(deleted.availability,'DELETED')
        self.assertEqual(deleted.content_hash,item.content_hash)
        self.assertEqual(self.storage.read(self.token,item.artifact_id).code,'PROVENANCE_MISSING')
        self.assertEqual(self.storage.put(self.token,'raw_output','synthetic','1',b'\x00raw\r\n\xff',core.PIN).code,'PROVENANCE_MISSING')
        self.assertEqual(self.storage.delete(self.token,item.artifact_id),deleted)
        with self.repo.transaction(self.tenant,self.case_id) as tx:
            with self.assertRaises(psycopg.IntegrityError):
                tx.connection.execute('INSERT INTO lw_storage.blobs VALUES (%s,%s,%s,%s)',(*tx.scope,item.artifact_id,b'resurrect'))

    def test_unknown_policy_and_future_deadline_fail_closed(self):
        self.repo.retention_policies = RetentionPolicies()
        item = self.put()
        self.assertEqual(self.storage.delete(self.token,item.artifact_id).code,'GATE_DENIED')
        self.repo.retention_policies = RetentionPolicies([(core.PIN,1)])
        future = self.put(name='future')
        self.assertEqual(self.storage.delete(self.token,future.artifact_id).code,'GATE_DENIED')

    def test_exact_version_pin_limits_and_revoked_capability(self):
        item = self.put('prompt')
        pin = dict(id=item.name,version=item.version,content_hash=item.content_hash)
        self.assertEqual(self.storage.resolve(self.token,'prompt',pin),b'\x00raw\r\n\xff')
        self.assertEqual(self.storage.resolve(self.token,'prompt',dict(pin,content_hash='0'*64)).code,'INVALID_HASH')
        self.assertEqual(self.storage.resolve(self.token,'model',pin).code,'BROKEN_REFERENCE')
        self.assertEqual(self.storage.put(self.token,'unknown','x','1',b'x',core.PIN).code,'SCHEMA_INVALID')
        self.assertEqual(self.storage.put(self.token,'raw_output','big','1',b'x'*(16*1024*1024+1),core.PIN).code,'SCHEMA_INVALID')
        self.authority.revoke(self.token)
        self.assertEqual(self.storage.read(self.token,item.artifact_id).code,'FORBIDDEN')

    def test_atomic_rollback_and_concurrent_version_conflict(self):
        target = uuid4()
        with self.assertRaises(RuntimeError):
            with self.repo.transaction(self.tenant,self.case_id) as tx:
                ObjectStore(tx).put(target,'raw_input','rollback','1',b'bytes',core.PIN,self.actor.id,datetime.now(timezone.utc),RetentionPolicies())
                raise RuntimeError('injected failure')
        self.assertEqual(self.storage.metadata(self.token,target).code,'BROKEN_REFERENCE')
        def save(data):
            authority = TokenAuthority()
            token = authority.provision(self.principal)
            return StorageService(self.repo,authority).put(token,'raw_output','race','1',data,core.PIN)
        with ThreadPoolExecutor(2) as pool:
            result = list(pool.map(save,(b'first',b'second')))
        self.assertEqual(sum(isinstance(r,ArtifactRecord) for r in result),1)
        self.assertEqual([r.code for r in result if isinstance(r,DomainError)],['CONFLICT'])

    def test_corruption_and_runtime_immutability(self):
        item = self.put()
        with self.repo.transaction(self.tenant,self.case_id) as tx:
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                tx.connection.execute('UPDATE lw_storage.artifacts SET version=%s',('tampered',))
        with psycopg.connect(self.admin) as c:
            c.execute('ALTER TABLE lw_storage.blobs DISABLE TRIGGER guarded_blob')
            c.execute('UPDATE lw_storage.blobs SET data=%s WHERE artifact_id=%s',(b'corrupt',item.artifact_id))
            c.execute('ALTER TABLE lw_storage.blobs ENABLE TRIGGER guarded_blob')
        self.assertEqual(self.storage.read(self.token,item.artifact_id).code,'INVALID_HASH')
        with psycopg.connect(self.admin) as c:
            c.execute('ALTER TABLE lw_storage.blobs DISABLE TRIGGER guarded_blob')
            c.execute('UPDATE lw_storage.blobs SET data=%s WHERE artifact_id=%s',(b'\x00raw\r\n\xff',item.artifact_id))
            c.execute('ALTER TABLE lw_storage.blobs ENABLE TRIGGER guarded_blob')

    def test_golden_source_snapshot_acceptance_and_retention(self):
        fact, party, source, plan, decision = self.approved_plan()
        before = self.get(plan)
        with self.repo.transaction(self.tenant,self.case_id) as tx:
            self.assertEqual(tx.source_bytes(source),b'Synthetic payment receipt.')
            self.assertIsNone(tx.connection.execute("SELECT original_bytes FROM lw_core.objects WHERE tenant_id=%s AND case_id=%s AND object_id=%s",(*tx.scope,source)).fetchone()[0])
        self.assertEqual(self.storage.delete(self.token,source).availability,'DELETED')
        self.assertEqual(self.get(plan),before)
        with self.repo.transaction(self.tenant,self.case_id) as tx:
            with self.assertRaises(Violation): tx.source_bytes(source)

    def test_backup_restore_preserves_raw_history_and_replay(self):
        self.approved_plan()
        item = self.put()
        erased = self.put(name='erased')
        self.storage.delete(self.token,erased.artifact_id)
        self.storage.hold(self.token,item.artifact_id,True)
        request = self.request('EditCase', {'title':'Synthetic backup case'},self.case_ref)
        result = self.run_request(request)
        self.assertNotIsInstance(result,DomainError)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'synthetic.dump'
            expected = raw_state(self.admin)
            checksum = backup(self.admin,path)
            restored = restore_test_database(ADMIN,path,checksum,'lukart_stage03_test_restore_'+uuid4().hex)
            self.assertEqual(raw_state(restored),expected)
            with psycopg.connect(restored) as c: grant_runtime(c,'lw_core_runtime')
            name = psycopg.conninfo.conninfo_to_dict(restored)['dbname']
            repo = PostgresRepository(make_conninfo(core.DSN,dbname=name),storage=True)
            self.assertEqual(CommandService(repo,self.authority).execute(json.dumps(request),self.token),result)
            self.assertEqual(StorageService(repo,self.authority).read(self.token,item.artifact_id),b'\x00raw\r\n\xff')
            self.assertEqual(StorageService(repo,self.authority).read(self.token,erased.artifact_id).code,'PROVENANCE_MISSING')
            self.assertEqual(StorageService(repo,self.authority).delete(self.token,item.artifact_id).code,'GATE_DENIED')
            with self.assertRaises(ValueError):
                restore_test_database(ADMIN,path,'0'*64,'lukart_stage03_test_bad_'+uuid4().hex)

    def test_upgrade_preserves_legacy_payloads_and_detects_ledger_drift(self):
        admin, dsn = fresh_database()
        with psycopg.connect(admin) as c:
            c.execute((ROOT/'lukart_work/core/migration.sql').read_text())
            c.execute('GRANT USAGE ON SCHEMA lw_core TO lw_core_runtime')
            c.execute('GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA lw_core TO lw_core_runtime')
            c.execute('GRANT UPDATE ON lw_core.cases,lw_core.heads TO lw_core_runtime')
            c.execute('GRANT USAGE ON ALL SEQUENCES IN SCHEMA lw_core TO lw_core_runtime')
        self.repo = PostgresRepository(dsn)
        self.service = CommandService(self.repo,self.authority)
        self.sequence = 0
        self.create_case()
        self.approved_plan()
        old = raw_state(admin)
        with psycopg.connect(admin) as c:
            migrate(c)
            grant_runtime(c,'lw_core_runtime')
            migrate(c)
        upgraded = raw_state(admin)
        self.assertEqual({k:v for k,v in upgraded.items() if k.startswith('lw_core.')},old)
        with psycopg.connect(admin) as c:
            c.execute("UPDATE lw_migrations.ledger SET checksum='drift' WHERE version=2")
        with psycopg.connect(admin) as c:
            with self.assertRaises(Violation): migrate(c)

    def test_migration_rollback_and_unknown_version(self):
        from unittest.mock import patch
        from lukart_work.storage import migrations
        admin, _ = fresh_database()
        with tempfile.TemporaryDirectory() as folder:
            broken = Path(folder)/'broken.sql'
            broken.write_text('CREATE TABLE public.must_rollback (id integer); SELECT missing_function();',encoding='utf-8')
            with psycopg.connect(admin) as c:
                with patch.object(migrations,'MIGRATIONS',((1,broken),)):
                    with self.assertRaises(psycopg.errors.UndefinedFunction): migrate(c)
                self.assertIsNone(c.execute("SELECT to_regclass('public.must_rollback')").fetchone()[0])
                self.assertIsNone(c.execute("SELECT to_regclass('lw_migrations.ledger')").fetchone()[0])
                migrate(c)
                c.execute("INSERT INTO lw_migrations.ledger VALUES (99,'unknown')")
            with psycopg.connect(admin) as c:
                with self.assertRaises(Violation): migrate(c)


# Reuse setup helpers only, not Stage 02 test methods or expectations.
for _name in ('request','run_request','apply','query','get','create_case','party','decision','fact','snapshot','accept','approved_plan'):
    setattr(Stage03Tests,_name,getattr(core.Stage02Tests,_name))
