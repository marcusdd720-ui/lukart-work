"""Independent package/export smoke checks; this does not validate JSON Schema metaschemas."""
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import tomllib
from pydantic import TypeAdapter, ValidationError
from lukart_work.domain.models import ENTITIES,EntityPayload
from lukart_work.contracts.messages import CONTRACTS,Command
from lukart_work.core.requests import CoreRequest,CoreQuery
from lukart_work.storage.objects import ArtifactRecord
from lukart_work.ingestion.models import IngestionResult
from lukart_work.facts.contracts import FactEvidenceRequest, CandidateReviewRecord, FactEvidenceQuery, FactEvidenceMatrix
from lukart_work.registry.contracts import RegistryRequest, RegistryReceipt, RegistryQuery, FilingRegistryEntry, RegistryProjection
from lukart_work.procedural.contracts import (
    ProceduralRequest, ProceduralRuleBinding, ProceduralQuery, ProceduralFinding, ProceduralAssessment,
)
from lukart_work.planner.contracts import PlannerRequest, PlannerQuery, DocumentPlanProjection
from lukart_work.drafting.contracts import (
    DraftingProfile, DraftingInvocation, DraftingTrace, DraftingRejectionTrace,
    DraftingTerminalResult, ModelExecutionReceipt,
)
from lukart_work.contracts.versions import contract_version
from lukart_work.validation.contracts import STAGE10_CONTRACTS
from lukart_work.finalization.contracts import FINALIZATION_CONTRACTS
from lukart_work.validation.rules import parse_entity
from lukart_work.validation.python_requirements import validated_python_requirement
ROOT=Path(__file__).parent
EXTRA_CONTRACTS=(CoreRequest,CoreQuery,ArtifactRecord,IngestionResult,FactEvidenceRequest,CandidateReviewRecord,
                 FactEvidenceQuery,FactEvidenceMatrix,RegistryRequest,RegistryReceipt,RegistryQuery,
                 FilingRegistryEntry,RegistryProjection,ProceduralRequest,ProceduralRuleBinding,
                 ProceduralQuery,ProceduralFinding,ProceduralAssessment,PlannerRequest,PlannerQuery,
                 DocumentPlanProjection,DraftingProfile,DraftingInvocation,DraftingTrace,
                 DraftingRejectionTrace,DraftingTerminalResult,ModelExecutionReceipt)
checks=[]

pyproject_data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
requires_python = validated_python_requirement(pyproject_data, platform.python_version())

for cls in ENTITIES+CONTRACTS+EXTRA_CONTRACTS+STAGE10_CONTRACTS+FINALIZATION_CONTRACTS:
    schema=json.loads((ROOT/'schemas'/f'{cls.__name__}.schema.json').read_text())
    expected=cls.model_json_schema()
    assert {k:v for k,v in schema.items() if k not in ('$id','$schema')}==expected
    assert schema.get('additionalProperties') is False
    assert schema['$id']==f'urn:lukart:work:{cls.__name__}:{contract_version(cls.__name__)}'
    checks.append({'check':'schema-export:'+cls.__name__,'result':'PASS'})
for name,typ in (('Entity',EntityPayload),('Command',Command)):
    schema=json.loads((ROOT/'schemas'/f'{name}.schema.json').read_text())
    assert {k:v for k,v in schema.items() if k not in ('$id','$schema')}==TypeAdapter(typ).json_schema()
    assert schema['$id']==f'urn:lukart:work:{name}:{contract_version(name)}'
    checks.append({'check':'schema-export:'+name,'result':'PASS'})
for p in (ROOT/'schemas').glob('*.json'):json.loads(p.read_text())
parse_entity((ROOT/'examples/valid-fact.json').read_text())
for name in ('invalid-confirmed-fact.json','invalid-extra-property.json'):
    try:parse_entity((ROOT/'examples'/name).read_text())
    except ValidationError:checks.append({'check':name,'result':'REJECTED_AS_EXPECTED'})
    else:raise AssertionError(name)
for p in (ROOT/'lukart_work/domain').glob('*.py'):
    tree=ast.parse(p.read_text())
    for node in ast.walk(tree):
        if isinstance(node,ast.ImportFrom):assert not any(x in (node.module or '').split('.') for x in ('ui','rendering','openai','anthropic','lukart_ros'))
checks.append({'check':'domain-import-boundaries','result':'PASS'})
# Report v2 keeps compatibility requirements deterministic across supported runtimes.
# `python` is a deprecated alias for the PR #70 spec-shaped report, not runtime proof.
# Historical runtime-shaped reports must be distinguished by report_schema_version.
result={'report_schema_version':2,'requires_python':requires_python,'python':requires_python,'pydantic':importlib.metadata.version('pydantic'),'baseline_sha256':hashlib.sha256((ROOT/'docs/00-baseline.md').read_bytes().replace(b'\r\n', b'\n')).hexdigest(),'checks':checks,'json_files_parsed':len(list((ROOT/'schemas').glob('*.json'))),'independent_json_schema_engine':'NOT_EXECUTED'}
(ROOT/'reports/package-validation.json').write_text(
    json.dumps(result,indent=2)+'\n',
    encoding='utf-8',
    newline='\n',
)
print(json.dumps({'checks':len(checks),'json_files_parsed':result['json_files_parsed'],'result':'PASS','runtime_python_version':platform.python_version()}))
