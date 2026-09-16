"""Owner-only offline backup/restore drill for isolated test databases.

Secrets travel through process environment, never command arguments or output.
Production retention of backup copies and deployment are intentionally separate.
"""
from hashlib import sha256
import os
from pathlib import Path
import re
import shutil
import subprocess


def _run(tool, dsn, args):
    from psycopg.conninfo import conninfo_to_dict
    config = conninfo_to_dict(dsn)
    environment = os.environ.copy()
    for key, variable in (('host','PGHOST'), ('port','PGPORT'), ('user','PGUSER'), ('password','PGPASSWORD'), ('dbname','PGDATABASE')):
        environment.pop(variable, None)
        if key in config:
            environment[variable] = config[key]
    binary = shutil.which(tool)
    if not binary:
        local = Path(__file__).resolve().parents[2] / '.local-stage02/runtime/pgsql/bin' / (tool + '.exe')
        binary = str(local) if local.exists() else None
    if not binary:
        raise RuntimeError('POSTGRES_BACKUP_TOOL_UNAVAILABLE')
    result = subprocess.run([binary, *args], env=environment, capture_output=True)
    if result.returncode:
        raise RuntimeError('POSTGRES_BACKUP_OPERATION_FAILED')


def backup(dsn, path):
    path = Path(path).resolve()
    if path.exists():
        raise ValueError('BACKUP_TARGET_EXISTS')
    _run('pg_dump', dsn, ['--format=custom', '--no-owner', '--no-acl', '--file', str(path)])
    return sha256(path.read_bytes()).hexdigest()


def restore_test_database(admin_dsn, path, expected_hash, database):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import make_conninfo
    path = Path(path).resolve()
    if not re.fullmatch(r'lukart_stage03_test_[a-z0-9_]+', database):
        raise ValueError('ISOLATED_TEST_DATABASE_REQUIRED')
    if sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError('BACKUP_HASH_MISMATCH')
    with psycopg.connect(admin_dsn, autocommit=True) as c:
        # CREATE fails if the database exists; no destructive restore option.
        c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    target = make_conninfo(admin_dsn, dbname=database)
    _run('pg_restore', target, ['--exit-on-error', '--single-transaction', '--no-owner', '--no-acl', '--dbname', database, str(path)])
    return target
