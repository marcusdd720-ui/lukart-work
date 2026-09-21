"""Reproducible schema/catalog/docs export from typed contracts, no external services."""
import json
from pathlib import Path
from pydantic import TypeAdapter
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
from lukart_work.validation.contracts import STAGE10_CONTRACTS\nfrom lukart_work.rendering.contracts import STAGE11_CONTRACTS
from lukart_work.domain.lifecycle import TRANSITIONS,INITIAL
from lukart_work.validation.rules import RELATIONS
from tests.fixtures import case,party,evidence,fact,source
ROOT=Path(__file__).parent

EXTRA_CONTRACTS=(CoreRequest,CoreQuery,ArtifactRecord,IngestionResult,FactEvidenceRequest,CandidateReviewRecord,
                 FactEvidenceQuery,FactEvidenceMatrix,RegistryRequest,RegistryReceipt,RegistryQuery,
                 FilingRegistryEntry,RegistryProjection,ProceduralRequest,ProceduralRuleBinding,
                 ProceduralQuery,ProceduralFinding,ProceduralAssessment,PlannerRequest,PlannerQuery,
                 DocumentPlanProjection,DraftingProfile,DraftingInvocation,DraftingTrace,
                 DraftingRejectionTrace,DraftingTerminalResult,ModelExecutionReceipt)

def write(path,obj):
    (ROOT/path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
for cls in ENTITIES+CONTRACTS+EXTRA_CONTRACTS+STAGE10_CONTRACTS+STAGE11_CONTRACTS:
    schema=cls.model_json_schema();schema['$schema']='https://json-schema.org/draft/2020-12/schema';schema['$id']='urn:lukart:work:'+cls.__name__+':'+contract_version(cls.__name__)
    write('schemas/'+cls.__name__+'.schema.json',schema)
for name,typ in [('Entity',EntityPayload),('Command',Command)]:
    schema=TypeAdapter(typ).json_schema();schema['$schema']='https://json-schema.org/draft/2020-12/schema';schema['$id']='urn:lukart:work:'+name+':'+contract_version(name);write('schemas/'+name+'.schema.json',schema)
write('schemas/lifecycle.json',{'initial':INITIAL,'transitions':TRANSITIONS})
write('schemas/relations.json',RELATIONS)
write('examples/valid-fact.json',fact().model_dump(mode='json'))
x=fact().model_dump(mode='json');x['status']='CONFIRMED';write('examples/invalid-confirmed-fact.json',x)
x=case().model_dump(mode='json');x['ui_state']='FINAL';write('examples/invalid-extra-property.json',x)
write('tests/golden_cases/source_to_fact.json',{'description':'Synthetic source-backed candidate, never automatically confirmed','entities':[x.model_dump(mode='json') for x in (case(),party(),evidence(),fact())],'sources':[source().model_dump(mode='json')],'expected_fact_status':'CANDIDATE','forbidden':['CONFIRMED_WITHOUT_HUMAN_DECISION','FINAL']})
lines=['# 01 — Katalog encji i pól','', 'Kontrakt normatywny: lukart_work/domain/models.py. Schematy JSON są eksportem. Wszystkie encje dziedziczą Entity; wspólne value objects są rozwinięte w $defs każdego schematu. Pole wymagane musi wystąpić; typ nullable może jawnie zawierać null. Kolekcje są wymagane także wtedy, gdy dopuszczają pustą listę.','', 'Każda rewizja jest niezmienna. Aktualizacja to nowa rewizja z previous_hash, CAS i audytem. Ownership: tenant_id + case_id; Case.id = case_id. Pełne wymagania wykraczające poza schemat: docs/01-specification.md.']
for cls in ENTITIES:
    schema=cls.model_json_schema()
    lines += ['', '## '+cls.__name__, '', '| Pole | Typ/schemat | Wymagane |', '|---|---|---|']
    for name,prop in schema['properties'].items():
        clean={k:v for k,v in prop.items() if k not in ('title','default')}
        lines.append('| '+name+' | `'+json.dumps(clean,ensure_ascii=False).replace('|','\\|')+'` | '+('tak' if name in schema.get('required',[]) else 'nie')+' |')
    lines += ['', 'Stan początkowy: `'+INITIAL[cls.__name__]+'`. Dozwolone przejścia:', '', '; '.join('`'+a+' → '+b+'`' for a,b in TRANSITIONS[cls.__name__])+'.', '', 'Inne przejścia są zabronione. Same-state revision wymaga zachowania ograniczeń immutable content i pełnej walidacji.']
(ROOT/'docs/02-entity-catalog.md').write_text('\n'.join(lines)+'\n')
