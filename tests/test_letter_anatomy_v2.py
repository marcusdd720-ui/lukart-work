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
        target=Ref(kind="Fact",id=UUID(int=1),revision=1)
        def statement(text,stype="STRUCTURAL",refs=(target,)):
            return SimpleNamespace(text=text,statement_type=stype,refs=refs)
        self.assertEqual(_source_bound_dateline(statement(
            "LUKART_DATELINE_V1:Warszawa, 05.10.2026")),"Warszawa, 05.10.2026")
        self.assertIsNone(_source_bound_dateline(statement("Warszawa, 05.10.2026")))
        with self.assertRaises(Violation):
            _source_bound_dateline(statement(
                "LUKART_DATELINE_V1:Warszawa, 05.10.2026", "FACTUAL"))
        with self.assertRaises(Violation):
            _source_bound_dateline(statement(
                "Tekst LUKART_DATELINE_V1:Warszawa, 05.10.2026"))
        for bad in ["LUKART_DATELINE_V1:Warszawa, 31.02.2026",
                    "LUKART_DATELINE_V1:Warszawa, 5.10.2026",
                    "LUKART_DATELINE_V1:, 05.10.2026",
                    "LUKART_DATELINE_V1:Warszawa\nX, 05.10.2026",
                    "LUKART_DATELINE_V1:Warszawa\t, 05.10.2026",
                    "LUKART_DATELINE_V1: Warszawa, 05.10.2026"]:
            with self.subTest(bad=bad),self.assertRaises(Violation):
                _source_bound_dateline(statement(bad))
        with self.assertRaises(Violation):
            _source_bound_dateline(statement("LUKART_DATELINE_V1:Warszawa, 05.10.2026",refs=()))

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
