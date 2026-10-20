// Editing prepares explicit commands. Only the authenticated API can write a Draft.
let editorDraft=null;
const editorTextNodes=new Map();
const draftId=document.getElementById('draftId'),draftRevision=document.getElementById('draftRevision'),
draftTexts=document.getElementById('draftTexts'),draftStatus=document.getElementById('draftStatus');
const reviewChecks={facts:'Fakty',evidence:'Dowody',legal_basis:'Podstawy prawne',procedure:'Procedura',
 contradictions:'Sprzeczności',language:'Język',adversarial:'Ocena krytyczna'};
function buildDraftAssessments(){
document.getElementById('draftAssessments').replaceChildren();
for(const [check,title] of Object.entries(reviewChecks)){
 const label=document.createElement('label');label.textContent=title;
 const select=document.createElement('select');select.id='draftCheck_'+check;
 for(const [value,text] of [['UNKNOWN','Nie oceniono'],['PASS','Spełnione'],['FAIL','Niespełnione']]){
  const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);
 }
 label.append(select);document.getElementById('draftAssessments').append(label);
}
}
function clearDraftEditor(){
 editorDraft=null;editorTextNodes.clear();draftTexts.replaceChildren();draftStatus.textContent='';
 draftId.value='';draftRevision.value='2';document.getElementById('previousDraft').disabled=true;
 for(const id of ['amendRationale','draftReviewRationale'])document.getElementById(id).value='';
 for(const check of Object.keys(reviewChecks)){const field=document.getElementById('draftCheck_'+check);if(field)field.value='UNKNOWN';}
}
function loadEditorDraft(){
 const revision=Number(draftRevision.value);
 if(!knownCase()||!idReady(draftId.value)||!Number.isSafeInteger(revision)||revision<1)return;
 editorDraft=null;editorTextNodes.clear();draftTexts.replaceChildren();
 query('query_draft',{contract:'urn:lukart:work:DraftEditorQuery:1.0.0',operation:'GetDraftForEditing',
 tenant_id:tenant.value.trim(),case_id:caseId.value.trim(),draft:{kind:'Draft',id:draftId.value.trim(),revision}});
}
document.getElementById('loadDraft').onclick=loadEditorDraft;
function handleDraftEditorResult(service,body,value){
 if(service==='query_draft'&&value.result_type==='DRAFT_EDITOR'){
  if(value.draft.tenant_id!==tenant.value.trim()||value.draft.case_id!==caseId.value.trim())return;
  editorDraft=value;caseSequence.value=String(value.case_sequence);draftTexts.replaceChildren();editorTextNodes.clear();
  buildDraftAssessments();
  draftId.value=value.draft.id;draftRevision.value=String(value.draft.revision);
  draftStatus.textContent='Projekt '+value.draft.id+' — rewizja '+value.draft.revision+' — '+value.draft.status+
    (value.draft.supersedes?' — poprzednik: '+value.draft.supersedes.id:'');
  document.getElementById('previousDraft').disabled=!value.draft.supersedes;
  for(const section of value.draft.sections){
   const heading=document.createElement('h3');heading.textContent='Sekcja '+section.section.id;draftTexts.append(heading);
   for(const statement of section.statements){
    const label=document.createElement('label');label.textContent=statement.statement_type+' — '+statement.id;
    const textarea=document.createElement('textarea');textarea.rows=4;textarea.value=statement.text;
    textarea.disabled=!value.editable;
    label.append(textarea);draftTexts.append(label);editorTextNodes.set(statement.id,textarea);
    const sources=document.createElement('p');sources.textContent='Odwołania: '+statement.refs.map(r=>r.kind+' '+r.id+' / '+r.revision).join(', ');
    draftTexts.append(sources);
   }
  }
  for(const check of Object.keys(reviewChecks))document.getElementById('draftCheck_'+check).value='UNKNOWN';
  document.getElementById('draftReviewRationale').value='';
  if(value.validation_run_id)validationId.value=value.validation_run_id;
  if(value.render_id)render.value=value.render_id;
 }
 if(['APPLIED','REPLAYED'].includes(value.state)&&
    ['AmendDraft','RecordValidationReview','ValidateDraft','RenderDraft'].includes(body.operation)){
  const target=(value.refs||[]).find(r=>r.kind==='Draft');
  if(target){draftId.value=target.id;draftRevision.value=String(target.revision);}
  // Refresh only through the read boundary; never dispatch another mutation.
  loadEditorDraft();
 }
}
document.getElementById('previousDraft').onclick=()=>{
 const previous=editorDraft&&editorDraft.draft.supersedes;if(!previous)return;
 draftId.value=previous.id;draftRevision.value=String(previous.revision);loadEditorDraft();
};
function editorMeta(){return {command_id:crypto.randomUUID(),tenant_id:tenant.value.trim(),case_id:caseId.value.trim(),
 idempotency_key:crypto.randomUUID(),expected_case_sequence:editorDraft.case_sequence,correlation_id:crypto.randomUUID()};}
function editorReady(){return editorDraft&&knownCase()&&editorDraft.draft.tenant_id===tenant.value.trim()&&editorDraft.draft.case_id===caseId.value.trim();}
function editorTarget(){return {kind:'Draft',id:editorDraft.draft.id,revision:editorDraft.draft.revision};}
function prepareEditorCommand(service,body,message){
 route.value=service;request.value=JSON.stringify(body,null,2);advanced.open=true;result.textContent=message;
}
document.getElementById('prepareAmend').onclick=()=>{
 if(!editorReady()||!editorDraft.editable)return;
 const rationale=document.getElementById('amendRationale').value.trim();
 const edits=editorDraft.draft.sections.flatMap(section=>section.statements).filter(s=>editorTextNodes.get(s.id).value!==s.text)
 .map(s=>({statement_id:s.id,text:editorTextNodes.get(s.id).value}));
 if(!rationale||!edits.length||edits.some(e=>!e.text.trim())){draftStatus.textContent='Zmień tekst i podaj uzasadnienie poprawki.';return;}
 prepareEditorCommand('execute_core',{contract:'urn:lukart:work:CoreRequest:1.0.0',operation:'AmendDraft',
 meta:editorMeta(),target:editorTarget(),data:{contract:'urn:lukart:work:AmendDraft:1.0.0',draft_hash:editorDraft.draft_hash,edits},rationale},
 'Poprawka przygotowana. Sprawdź treść i osobno zatwierdź zapis jako uprawniony HUMAN.');
};
document.getElementById('confirmAmend').onclick=()=>{
 try{const body=JSON.parse(request.value);
 if(!editorReady()||route.value!=='execute_core'||body.operation!=='AmendDraft'||body.data.draft_hash!==editorDraft.draft_hash||
 body.meta.tenant_id!==tenant.value.trim()||body.meta.case_id!==caseId.value.trim())throw new Error();
 query('execute_core',body);
 }catch{draftStatus.textContent='Najpierw przygotuj i sprawdź poprawkę projektu.';}
};
function validationEnvelope(operation){return {contract:'urn:lukart:work:ValidationRequest:1.0.0',operation,
 meta:editorMeta(),target:editorTarget(),draft_hash:editorDraft.draft_hash,snapshot_hash:editorDraft.draft.snapshot_hash,
 validation_policy:editorDraft.validation_policy,rationale:document.getElementById('draftReviewRationale').value.trim()};}
document.getElementById('prepareDraftReview').onclick=()=>{
 if(!editorReady())return;
 const body=validationEnvelope('RecordValidationReview');if(!body.rationale)return;
 body.assessments=Object.keys(reviewChecks).map(check=>({check,outcome:document.getElementById('draftCheck_'+check).value,rationale:body.rationale}));
 prepareEditorCommand('execute_validation',body,'Sprawdź własne oceny HUMAN i jawnie zatwierdź wysłanie przeglądu.');
};
document.getElementById('prepareDraftValidation').onclick=()=>{
 if(!editorReady())return;
 const body=validationEnvelope('ValidateDraft');if(!body.rationale)return;
 body.review_id=editorDraft.review_id;
 prepareEditorCommand('execute_validation',body,'Walidacja przygotowana. Brak aktualnego przeglądu lub inne braki zablokują akceptację.');
};
document.getElementById('prepareDraftRender').onclick=()=>{
 if(!editorReady()||editorDraft.draft.status!=='VALIDATED'||!editorDraft.validation_run_id)return;
 prepareEditorCommand('execute_finalization',{contract:'urn:lukart:work:FinalizationRequest:1.0.0',operation:'RenderDraft',
 meta:editorMeta(),target:editorTarget(),draft_hash:editorDraft.draft_hash,snapshot_hash:editorDraft.draft.snapshot_hash,
 validation_run_id:editorDraft.validation_run_id,semantic_profile:editorDraft.semantic_profile,
 rationale:'Jawne żądanie DOCX/PDF zwalidowanego projektu; bez zatwierdzenia FINAL'},
 'Render przygotowany. Sprawdź i jawnie zatwierdź wysłanie. Podgląd i pobieranie będą dostępne po udanym zapisie.');
};
