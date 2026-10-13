"""Letter anatomy v2 focused security/format tests — no external service or secrets."""
from __future__ import annotations
import unittest
from types import SimpleNamespace
from uuid import UUID

from lukart_work.domain.models import Ref
from lukart_work.rendering.contracts import LayoutBlock
from lukart_work.rendering.service import (
    _source_bound_dateline, _identical_authoritative_request, _display_text,
)
from lukart_work.type_packs.pl_pre_payment_1.fixture import positive_fixture
from lukart_work.validation.rules import Violation
from scripts.run_generator_pism_operator_e2e import (
    synthetic_dateline, synthetic_payment_body,
)

class LetterAnatomyV2(unittest.TestCase):
    def test_source_bound_date_and_place(self):
        fixture=positive_fixture()
        self.assertEqual(synthetic_dateline(fixture),
                         "LUKART_DATELINE_V1:Warszawa, 05.10.2026")
        copy=fixture.model_copy(update={"document_date_iso":"not-a-date"})
        with self.assertRaises(ValueError): synthetic_dateline(copy)
        badplace=fixture.model_copy(update={"document_place":"A, B"})
        with self.assertRaises(ValueError): synthetic_dateline(badplace)

    def test_structural_marker_and_calendrical_validation(self):
        from tests.fixtures import fact as sample_fact, ref as sample_ref
        from lukart_work.domain.models import Decision
        from tests.fixtures import common, ACTOR
        dateline = "LUKART_DATELINE_V1:Warszawa, 05.10.2026"
        f = sample_fact().model_copy(update={
            "statement": dateline, "status": "CONFIRMED", "revision": 3,
            "acceptance": Ref(kind="Decision", id=UUID(int=50), revision=1),
        })
        target = sample_ref(f)
        approval = Decision(
            **common(50), kind="Decision", status="RECORDED",
            decision_type="FACT_ACCEPTANCE", targets=(
                Ref(kind="Fact", id=f.id, revision=f.revision - 1),
            ), outcome="ACCEPT", rationale="Synthetic explicit approval",
            decided_by=ACTOR,
        )
        records = {target: f, sample_ref(approval): approval}
        scope = (f.tenant_id, f.case_id)
        def statement(text, stype="FACTUAL", refs=(target,), support="SOURCE_BACKED"):
            return SimpleNamespace(text=text,statement_type=stype,refs=refs,support=support)
        self.assertEqual(_source_bound_dateline(statement(dateline), records, scope),
                         "Warszawa, 05.10.2026")
        self.assertIsNone(_source_bound_dateline(statement("Warszawa, 05.10.2026"), records, scope))
        with self.assertRaises(Violation):
            _source_bound_dateline(statement(dateline, "STRUCTURAL"), records, scope)
        with self.assertRaises(Violation):
            _source_bound_dateline(statement(dateline, support="INFERRED"), records, scope)
        with self.assertRaises(Violation):
            _source_bound_dateline(statement(dateline, refs=()), records, scope)
        for bad in ["LUKART_DATELINE_V1:Warszawa, 31.02.2026",
                    "LUKART_DATELINE_V1:Warszawa, 5.10.2026",
                    "LUKART_DATELINE_V1:, 05.10.2026",
                    "LUKART_DATELINE_V1:Warszawa\nX, 05.10.2026",
                    "LUKART_DATELINE_V1:Warszawa\t, 05.10.2026",
                    "LUKART_DATELINE_V1: Warszawa, 05.10.2026"]:
            with self.subTest(bad=bad), self.assertRaises(Violation):
                _source_bound_dateline(statement(bad), records, scope)
        mismatched = f.model_copy(update={"statement": "Not the dated source"})
        with self.assertRaises(Violation):
            _source_bound_dateline(statement(dateline), {target: mismatched, sample_ref(approval): approval}, scope)
        unconfirmed = f.model_copy(update={"status": "REVIEWED"})
        with self.assertRaises(Violation):
            _source_bound_dateline(statement(dateline), {target: unconfirmed, sample_ref(approval): approval}, scope)
        with self.assertRaises(Violation):
            _source_bound_dateline(statement(dateline), {target: f}, scope)

    def test_only_exact_source_bound_duplicate_is_suppressed(self):
        req=Ref(kind="Request",id=UUID(int=2),revision=1)
        other=Ref(kind="Request",id=UUID(int=3),revision=1)
        wanted={req:"Wzywam do zapłaty 100 zł"}
        def stmt(text,refs,kind="REQUEST",support="SOURCE_BACKED",citations=()):
            return SimpleNamespace(statement_type=kind,text=text,refs=refs,
                                   support=support,citations=citations)
        self.assertTrue(_identical_authoritative_request(
            stmt("Wzywam do zapłaty 100 zł", (req,)), wanted))
        self.assertFalse(_identical_authoritative_request(
            stmt("Wzywam do zapłaty 200 zł", (req,)), wanted))
        self.assertFalse(_identical_authoritative_request(
            stmt("Wzywam do zapłaty 100 zł", (other,)), wanted))
        self.assertFalse(_identical_authoritative_request(
            stmt("Wzywam do zapłaty 100 zł", (req,), "FACTUAL"), wanted))
        self.assertFalse(_identical_authoritative_request(
            stmt("Wzywam do zapłaty 100 zł", (req,other)), wanted))
        self.assertFalse(_identical_authoritative_request(
            stmt("Wzywam do zapłaty 100 zł", (req,), support="INFERRED"), wanted))
        self.assertFalse(_identical_authoritative_request(
            stmt("Wzywam do zapłaty 100 zł", (req,), citations=(other,)), wanted))

    def test_signature_affordance_is_not_signed_artifact(self):
        obj = LayoutBlock(
            role="SIGNATURE", style_token="document.signature",
            text="Wierzyciel testowy")
        display=_display_text(obj)
        self.assertIn("_______________________________",display)
        self.assertTrue(display.endswith("Wierzyciel testowy"))
        self.assertNotIn("PODPISANO",display)

    def test_sample_no_longer_embeds_dateline_in_prose(self):
        request,sections,_=synthetic_payment_body(positive_fixture())
        self.assertNotIn("05.10.2026",sections["HEADER_AND_PARTIES"])
        self.assertNotIn("Wierzyciel testowy", sections["HEADER_AND_PARTIES"])
        self.assertIn("Wzywam do zapłaty",request)

if __name__=='__main__':unittest.main()
