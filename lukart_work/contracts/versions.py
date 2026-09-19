"""Published contract identities. Entity.schema_version versions common metadata only."""

# These contracts tighten stage-01 semantics or embed the changed Decision/Snapshot.
# Old wire data must not be silently interpreted as a newly approved artifact.
REMEDIATED_CONTRACTS = frozenset({
    'Decision', 'ValidationFinding', 'Draft', 'DocumentPlan', 'Proceeding', 'Deadline', 'Section',
    'Snapshot', 'AcceptSnapshot', 'SnapshotResult', 'AIRequest', 'AIResult', 'ReleaseResult',
    'DomainEvent',
    'AppendRevision', 'RevisionResult', 'Entity', 'Command',
})

def contract_version(name: str) -> str:
    return '2.0.0' if name in REMEDIATED_CONTRACTS else '1.0.0'
