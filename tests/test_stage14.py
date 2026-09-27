"""Stage 14 synthetic UNIVERSUM regressions."""
from dataclasses import replace
import json
from pathlib import Path
import unittest
from lukart_work.factory.universum import *

A="a"*40;B="b"*40;TA="c"*40;TB="d"*40
OK=ClosureBundle(True,True,True,True,True,True)
def snap(**k): return replace(ExecutionSnapshot(A,TA),**k)
def ev(*,sha=A,tree=TA,workflow=FINAL_CI_WORKFLOW,terminal=True,passed=True,invalidated=False):
    return EvidenceRecord(sha,tree,workflow,terminal,passed,invalidated)

class UniversumTests(unittest.TestCase):
    def test_restore(self):
        self.assertEqual(LiveStateRestore.restore(main_sha=A,main_tree=TA,previous_stage=13,previous_stage_closed=True).previous_stage,13)
        with self.assertRaises(ValueError):LiveStateRestore.restore(main_sha=A,main_tree=TA,previous_stage=13,previous_stage_closed=False)
    def test_delta(self):
        self.assertTrue(DeltaClassifier.classify(["docs/x.md"]).documentation_only)
        self.assertTrue(DeltaClassifier.classify(["reports/manifest.sha256.json"]).manifest_only)
        self.assertTrue(DeltaClassifier.classify(["lukart_work/factory/universum.py"]).semantic)
    def test_closure_bundle_planner(self):
        p=replace(OK,red_team=False)
        self.assertEqual(ClosureBundlePlanner.missing(p),("red_team",));self.assertTrue(ClosureBundlePlanner.ready(OK))
    def test_failure_classification(self):
        self.assertEqual(FailureClassifier.classify(["test","authorization"]),FailureClass.AUTHORIZATION)
        self.assertEqual(FailureClassifier.classify(["runner_unavailable"]),FailureClass.RUNNER)
        self.assertEqual(FailureClassifier.classify(["mystery"]),FailureClass.UNKNOWN)
    def test_focused_fail(self): self.assertEqual(CriticalPathPlanner.plan(snap(focused_tests=GateState.FAIL)).action,NextAction.MINIMUM_SAFE_REPAIR)
    def test_full_fail(self): self.assertEqual(CriticalPathPlanner.plan(snap(focused_tests=GateState.PASS,full_regression=GateState.FAIL)).action,NextAction.MINIMUM_SAFE_REPAIR)
    def test_stale_manifest(self):
        s=snap(focused_tests=GateState.PASS,full_regression=GateState.PASS,closure_bundle=OK,manifest=GateState.STALE)
        self.assertEqual(CriticalPathPlanner.plan(s).action,NextAction.STABILIZE_MANIFEST)
    def test_stale_docs(self):
        s=snap(focused_tests=GateState.PASS,full_regression=GateState.PASS,closure_bundle=replace(OK,implementation_docs=False),manifest=GateState.PASS)
        self.assertEqual(CriticalPathPlanner.plan(s).action,NextAction.BUILD_CLOSURE_BUNDLE)
    def test_unknown_and_authorization_fail_closed(self):
        for f in (FailureClass.UNKNOWN,FailureClass.AUTHORIZATION):
            with self.subTest(f=f):self.assertEqual(CriticalPathPlanner.plan(snap(active_failure=f)).action,NextAction.MINIMUM_SAFE_REPAIR)
    def test_infra_runner(self):
        self.assertEqual(CriticalPathPlanner.plan(snap(active_failure=FailureClass.INFRA)).action,NextAction.RESOLVE_EXECUTION_ENVIRONMENT)
        self.assertEqual(CriticalPathPlanner.plan(snap(runner_available=False)).action,NextAction.RESOLVE_EXECUTION_ENVIRONMENT)
    def test_supersession(self):
        r=WorkflowExecution(1,B,False,False)
        self.assertEqual(SupersessionAnalyzer.classify(r,candidate_sha=A),SupersessionClass.SUPERSEDED)
        self.assertFalse(SupersessionAnalyzer.blocks_candidate(r,candidate_sha=A))
        p=WorkflowExecution(2,B,True,True,True)
        self.assertEqual(SupersessionAnalyzer.classify(p,candidate_sha=A),SupersessionClass.PROTECTED_EVIDENCE)
        failed_current=WorkflowExecution(3,A,True,False,True)
        self.assertEqual(SupersessionAnalyzer.classify(failed_current,candidate_sha=A),SupersessionClass.CURRENT)
        self.assertTrue(SupersessionAnalyzer.blocks_candidate(failed_current,candidate_sha=A))
    def test_evidence_reuse_exact_identity(self):
        r=ev()
        self.assertTrue(EvidenceReusePolicy.can_reuse(r,source_sha=A,tree_sha=TA,workflow=FINAL_CI_WORKFLOW))
        self.assertFalse(EvidenceReusePolicy.can_reuse(r,source_sha=B,tree_sha=TA,workflow=FINAL_CI_WORKFLOW))
        self.assertFalse(EvidenceReusePolicy.can_reuse(r,source_sha=A,tree_sha=TB,workflow=FINAL_CI_WORKFLOW))
    def finalish(self,**k):
        base=dict(focused_tests=GateState.PASS,full_regression=GateState.PASS,closure_bundle=OK,manifest=GateState.PASS,candidate_frozen=True,final_exact_sha_ci=GateState.PASS,final_exact_sha_evidence=ev())
        base.update(k);return snap(**base)
    def test_unbound_final_ci_pass_fails_closed(self):
        s=self.finalish(final_exact_sha_evidence=None)
        self.assertEqual(CriticalPathPlanner.plan(s).action,NextAction.MINIMUM_SAFE_REPAIR)
    def test_wrong_sha_final_ci_pass_fails_closed(self):
        s=self.finalish(final_exact_sha_evidence=ev(sha=B))
        self.assertEqual(CriticalPathPlanner.plan(s).action,NextAction.MINIMUM_SAFE_REPAIR)
    def test_new_sha_requires_review(self): self.assertEqual(CriticalPathPlanner.plan(self.finalish()).action,NextAction.INDEPENDENT_REVIEW_BOUNDARY)
    def test_review_fail(self): self.assertEqual(CriticalPathPlanner.plan(self.finalish(independent_review=GateState.FAIL)).action,NextAction.MINIMUM_SAFE_REPAIR)
    def test_unbound_review_pass_fails_closed(self):
        s=self.finalish(independent_review=GateState.PASS)
        self.assertEqual(CriticalPathPlanner.plan(s).action,NextAction.MINIMUM_SAFE_REPAIR)
    def test_wrong_tree_review_pass_fails_closed(self):
        s=self.finalish(independent_review=GateState.PASS,independent_review_evidence=ev(tree=TB,workflow=INDEPENDENT_REVIEW_WORKFLOW))
        self.assertEqual(CriticalPathPlanner.plan(s).action,NextAction.MINIMUM_SAFE_REPAIR)
    def test_human_gate(self):
        s=self.finalish(independent_review=GateState.PASS,independent_review_evidence=ev(workflow=INDEPENDENT_REVIEW_WORKFLOW))
        self.assertEqual(CriticalPathPlanner.plan(s).action,NextAction.HUMAN_MERGE_GATE)
        self.assertFalse(HumanGateResolver.merge_permitted(independent_review=GateState.PASS,human_merge_required=True,human_merge_authorized=False))
    def test_human_gate_cannot_be_disabled(self):
        with self.assertRaises(ValueError):replace(ExecutionSnapshot(A,TA),human_merge_required=False)
        self.assertFalse(HumanGateResolver.merge_permitted(independent_review=GateState.PASS,human_merge_required=False,human_merge_authorized=True))
    def test_post_landing_fail(self):
        s=self.finalish(independent_review=GateState.PASS,independent_review_evidence=ev(workflow=INDEPENDENT_REVIEW_WORKFLOW),human_merge_authorized=True,landed=True,post_landing=GateState.FAIL)
        self.assertEqual(CriticalPathPlanner.plan(s).action,NextAction.POST_LANDING_REPAIR)
    def test_receipt_eligibility(self):
        s=self.finalish(independent_review=GateState.PASS,independent_review_evidence=ev(workflow=INDEPENDENT_REVIEW_WORKFLOW),human_merge_authorized=True,landed=True,post_landing=GateState.PASS)
        self.assertEqual(CriticalPathPlanner.plan(s).action,NextAction.WRITE_CLOSURE_RECEIPT)
    def test_ci_budget(self):
        b=CIBudget();b.consume();b.consume()
        with self.assertRaises(ValueError):b.consume()
        b.consume(FullCIReason.INFRA_FAILURE);self.assertEqual(b.full_ci_run_count,3)
    def test_freeze(self):
        f=CandidateFreeze();f.freeze(A);self.assertFalse(f.mutation_allowed(None));self.assertTrue(f.mutation_allowed(FrozenMutationReason.P0_P1))
        with self.assertRaises(ValueError):f.freeze(B)

class ReplayTests(unittest.TestCase):
    def test_replay_preserves_unknowns(self):
        p=json.loads((Path(__file__).resolve().parents[1]/"reports/stage14-stage13-replay.json").read_text())
        self.assertEqual(p["observed"]["candidate_sha_count"],24)
        self.assertGreaterEqual(p["observed"]["full_ci_run_count_lower_bound"],7)
        self.assertIsNone(p["observed"]["manual_intervention_count"])
        self.assertLessEqual(p["replay"]["avoidable_candidate_sha_count_lower_bound"],24)
        self.assertLessEqual(p["replay"]["avoidable_full_ci_count_lower_bound"],p["observed"]["full_ci_run_count_lower_bound"])

if __name__=="__main__":unittest.main()
