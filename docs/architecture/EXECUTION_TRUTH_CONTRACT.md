# LUKART WORK / UAOS — Execution Truth Contract
Date: 2026-10-05
Priority: P0
Status: DESIGN INPUT / IMPLEMENT AFTER CURRENT CLOSURE GATE

## Root problem
A scheduler/control plane can report RUNNING while no real executor is doing useful work.
Therefore control-plane state must not be accepted as execution truth.

## Required state machine
QUEUED
LEASED
SPAWN_REQUESTED
PROCESS_VERIFIED
HEARTBEAT_VERIFIED
WORKING
ARTIFACT_PRODUCED
VALIDATION_RUNNING
VALIDATED
COMMITTED
CI_VERIFIED
DONE

Failure/exception states:
STALE
ORPHANED
BLOCKED
QUARANTINED
FAILED
CANCELLED

## Rule
WORKING may only be derived from independent execution evidence.

## Evidence-of-Execution record
- job_id
- run_id
- agent_id
- provider_id
- model_id
- workspace_id
- branch/worktree
- process_id
- process_start_timestamp
- heartbeat
- last_tool_call
- progress evidence
- artifact_hash
- git_diff_hash
- commit_sha
- tree_sha
- test_result
- CI_run_id
- completion_evidence

## Liveness rules
- no heartbeat => never WORKING
- shell waiting with no child/progress => stale candidate
- queued work + zero real executor => P0 mismatch
- process exists but no progress proof => not sufficient
- stale lease must expire deterministically
- orphan recovery must be idempotent
- retries must have bounded attempt semantics
- state transitions must be auditable and replayable

## Workspace isolation
Use adapter interface:
- native git worktree as baseline
- Workmux as optional accelerator
- container/sandbox where isolation requires it

Workmux must never become an irreplaceable dependency.

## Soak evidence
A clean short test is not equivalent to 24h/72h proof.
Long-duration reliability must be separately measured and recorded.

## Integration dependency
This contract is the P0 prerequisite for LSAF provider routing and higher-order autonomy.
Control-plane status must never become an authority without matching execution evidence.
