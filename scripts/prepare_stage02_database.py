"""Create the dedicated local test database/role. Never accepts a production DSN."""
import json
from pathlib import Path
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / '.local-stage02/connection.json').read_text(encoding='utf-8-sig'))
with psycopg.connect(config['admin_dsn'], autocommit=True) as connection:
    if not connection.execute("SELECT 1 FROM pg_roles WHERE rolname='lw_core_runtime'").fetchone():
        connection.execute(sql.SQL('CREATE ROLE lw_core_runtime LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}').format(sql.Literal(config['runtime_password'])))
    if not connection.execute("SELECT 1 FROM pg_database WHERE datname='lukart_stage02_test'").fetchone():
        connection.execute('CREATE DATABASE lukart_stage02_test')
    print('PostgreSQL:', connection.execute('SHOW server_version').fetchone()[0])
admin = psycopg.conninfo.make_conninfo(config['admin_dsn'], dbname='lukart_stage02_test')
with psycopg.connect(admin) as connection:
    if not connection.execute("SELECT 1 FROM pg_namespace WHERE nspname='lw_core'").fetchone():
        connection.execute((ROOT / 'lukart_work/core/migration.sql').read_text())
    connection.execute('GRANT USAGE ON SCHEMA lw_core TO lw_core_runtime')
    connection.execute('GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA lw_core TO lw_core_runtime')
    connection.execute('GRANT UPDATE ON lw_core.cases,lw_core.heads TO lw_core_runtime')
    connection.execute('GRANT USAGE ON ALL SEQUENCES IN SCHEMA lw_core TO lw_core_runtime')
print('Dedicated test database and non-owner runtime role ready.')
