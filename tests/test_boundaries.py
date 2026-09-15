import json
import unittest
from tests.fixtures import *
from lukart_work.validation.rules import *

class BoundaryTests(unittest.TestCase):
    def test_duplicate_json_keys(self):
        with self.assertRaises(Violation):parse_entity('{"kind":"Case","kind":"Draft"}')
    def test_nonfinite_json(self):
        with self.assertRaises(Violation):strict_json('{"confidence":NaN}')
    def test_json_size(self):
        with self.assertRaises(Violation):strict_json(' '*2_000_001)
    def test_finding_omission(self):
        a=gate_inputs();a[1]=a[1].model_copy(update={'findings':(Ref(kind='ValidationFinding',id=uid(66),revision=1),)})
        self.assertIn('FINDINGS_INCOMPLETE',evaluate_release(*a).reasons)
    def test_unknown_freshness(self):
        a=gate_inputs();a[4]=a[4].model_copy(update={'state':'UNKNOWN'})
        self.assertIn('STALE',evaluate_release(*a).reasons)
    def test_wrong_policy(self):
        a=gate_inputs();a[5]=PIN.model_copy(update={'version':'2'})
        self.assertIn('POLICY_MISMATCH',evaluate_release(*a).reasons)
    def test_empty_draft(self):
        a=gate_inputs();a[0]=a[0].model_copy(update={'sections':()})
        self.assertIn('EMPTY_DOCUMENT',evaluate_release(*a).reasons)
    def test_snapshot_missing_closure(self):
        c=case();f=fact()
        snap=Snapshot(schema_version='1.0.0',id=uid(30),tenant_id=c.tenant_id,case_id=c.case_id,case_sequence=1,created_at=NOW,members=(SnapshotMember(ref=ref(c),content_hash=digest(c)),SnapshotMember(ref=ref(f),content_hash=digest(f))),heads=(ref(c),ref(f)),sources=(source(),),knowledge_pins=(),rule_set=PIN,policy=PIN)
        with self.assertRaises(Violation) as err:validate_snapshot(snap,{ref(c):c,ref(f):f})
        self.assertEqual(err.exception.code,'SNAPSHOT_NOT_CLOSED')
    def test_golden_case_source_to_fact(self):
        path=__import__('pathlib').Path(__file__).parent/'golden_cases'/'source_to_fact.json'
        data=json.loads(path.read_text());es=tuple(parse_entity(json.dumps(x)) for x in data['entities'])
        sources={s.id:s for s in (SourceDocument.model_validate_json(json.dumps(x)) for x in data['sources'])}
        self.assertEqual(len(validate_graph(es,sources)),4)
        f=next(e for e in es if e.kind=='Fact');self.assertEqual(f.status,'CANDIDATE')
        self.assertNotEqual(f.status,'CONFIRMED')
