"""CASE-first coverage through existing generic services, without type templates."""
import tempfile
from pathlib import Path
import unittest
from tests import test_finalization as final
from lukart_work.operator import GeneratorPismOperator

@unittest.skipUnless(final.core.ADMIN_RUNTIME and final.core.DSN, "Requires isolated PostgreSQL")
class GeneratorPismCaseE2ETests(unittest.TestCase):
    def test_case_reaches_persisted_render_and_local_preview(self):
        final.FinalizationTests.setUpClass()
        h = final.FinalizationTests("test_public_happy_path_persists_exact_bytes_approval_and_release_chain")
        h.setUp()
        operator = GeneratorPismOperator(repository=h.repo, authority=h.authority,
            case_profile=h.final_profile, drafting_profiles={"QUICK": h.profile},
            provider=h.provider, package_profile=h.package_profile)
        h.service, h.planner, h.procedural = operator.core, operator.planner, operator.procedural
        h.drafting, h.validation, h.finalization = operator.drafting, operator.validation, operator.finalization
        draft, run_id = h.validated()
        render_id, _, _ = h.render(draft, run_id)
        with tempfile.TemporaryDirectory() as tmp:
            preview = operator.export_local(tenant_id=h.tenant, case_id=h.case_id,
                render_id=render_id, token=h.token, output=Path(tmp) / "export")
            self.assertTrue(preview.is_file())
            self.assertEqual((preview.parent / "document.pdf").read_bytes(),
                h.final_query("ReadFinalArtifact", render_id, format="PDF"))
