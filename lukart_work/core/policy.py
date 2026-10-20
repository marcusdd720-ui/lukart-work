"""Pin the actual versioned rule implementation, not a label standing for it."""
from hashlib import sha256
from pathlib import Path
from lukart_work.domain.models import VersionPin
from lukart_work.validation.rules import digest

POLICY_FILES = (
    'core/policy.py', 'core/service.py', 'core/security.py', 'core/requests.py',
    'core/postgres.py', 'core/migration.sql', 'domain/models.py', 'domain/lifecycle.py',
    'validation/rules.py', 'contracts/messages.py', 'contracts/versions.py',
    'storage/objects.py', 'storage/service.py', 'storage/migration.sql', 'storage/migrations.py',
    'facts/contracts.py', 'facts/service.py',
    'drafting/amendments.py',
)


def policy_artifact(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    return {
        'profile': 'SHA-256 of source bytes with CRLF normalized to LF',
        'files': {name: sha256((root / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() for name in POLICY_FILES},
    }


def rule_pin(root=None):
    return VersionPin(id='lukart-work-case-core', version='1.0.4', content_hash=digest(policy_artifact(root)))
