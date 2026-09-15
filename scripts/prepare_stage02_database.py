"""Create the dedicated local test database/role. Never accepts a production DSN."""
import json
import argparse
import re
from pathlib import Path
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / '.local-stage02/connection.json').read_text(encoding='utf-8-sig'))
parser = argparse.ArgumentParser()
parser.add_argument('--database', default=psycopg.conninfo.conninfo_to_dict(config['runtime_dsn'])['dbname'])
database = parser.parse_args().database
if not re.fullmatch(r'lukart_stage02_test(?:_[a-z0-9]+)?', database):
    raise SystemExit('Only dedicated lukart_stage02_test database names are allowed.')
with psycopg.connect(config['admin_dsn'], autocommit=True) as connection:
    if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname='lw_core_runtime'").fetchone():
        connection.execute(sql.SQL('CREATE ROLE lw_core_runtime LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}').format(sql.Literal(config['runtime_password'])))
    if not connection.execute('SELECT 1 FROM pg_database WHERE datname=%s', (database,)).fetchone():
        connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    print('PostgreSQL:', connection.execute('SHOW server_version').fetchone()[0])
admin = psycopg.conninfo.make_conninfo(config['admin_dsn'], dbname=database)
with psycopg.connect(admin) as connection:
    if not connection.execute("SELECT 1 FROM pg_namespace WHERE nspname='lw_core'").fetchone():
        connection.execute((ROOT / 'lukart_work/core/migration.sql').read_text())
    connection.execute('GRANT USAGE ON SCHEMA lw_core TO lw_core_runtime')
    connection.execute('GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA lw_core TO lw_core_runtime')
    connection.execute('GRANT UPDATE ON lw_core.cases,lw_core.heads TO lw_core_runtime')
    connection.execute('GRANT USAGE ON ALL SEQUENCES IN SCHEMA lw_core TO lw_core_runtime')
config['runtime_dsn'] = psycopg.conninfo.make_conninfo(config['runtime_dsn'], dbname=database)
(ROOT / '.local-stage02/connection.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
print('Dedicated test database and non-owner runtime role ready.')
