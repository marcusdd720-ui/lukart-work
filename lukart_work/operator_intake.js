// Explicit user actions compose existing server-side authorization boundaries.
const caseSequence=document.getElementById('caseSequence'),sourceFile=document.getElementById('sourceFile'),
sourceId=document.getElementById('sourceId'),ingestionId=document.getElementById('ingestionId'),
ingestionStatus=document.getElementById('ingestionStatus');
let latestExtraction=null;
const candidateIndex=document.getElementById('candidateIndex'),candidateQuote=document.getElementById('candidateQuote');
function clearReview(){latestExtraction=null;candidateIndex.replaceChildren();candidateQuote.textContent='';
for(const id of ['candidateDescription','candidateStatement','candidateRationale'])document.getElementById(id).value='';
document.getElementById('reviewRevision').value='0';document.getElementById('candidateDisposition').value='REJECT';}
function clearIntake(){caseSequence.value='';sourceFile.value='';sourceId.value='';ingestionId.value='';ingestionStatus.textContent='';clearReview();}
for(const field of [token,tenant,caseId])field.oninput=()=>{
 generation++;clearIntake();clearArtifact();request.value='{}';result.textContent='';send.disabled=false;
};
function handleIntakeResult(service,body,value){
 if(value.result_type==='CASE_HEAD')caseSequence.value=String(value.case_sequence);
 const registration=value.registration||value;
 if(['APPLIED','REPLAYED'].includes(registration.state))caseSequence.value=String(registration.case_sequence);
 if(service==='execute_core'&&body.operation==='CreateCase'&&['APPLIED','REPLAYED'].includes(value.state)){
   result.textContent='Utworzono sprawę '+body.meta.case_id+'\n'+result.textContent;
 }
 if(service==='upload_source'&&value.source_id){sourceId.value=value.source_id;ingestionId.value=value.run_id;}
 const extraction=value.ingestion||value;
 if(extraction.body){
   clearReview();
   if(extraction.body.status==='EXTRACTED'){
     latestExtraction=extraction;
     extraction.body.candidates.forEach((candidate,index)=>{
       if(!['FACT','EVIDENCE'].includes(candidate.kind))return;
       const option=document.createElement('option');option.value=String(index);
       const fragment=extraction.body.fragments[candidate.fragment];
       option.textContent=index+' — '+candidate.kind+' — '+fragment.unit+' '+fragment.position;
       candidateIndex.append(option);
     });
     showCandidate();
   }
   const statuses={EXTRACTED:'Tekst zapisany. Kandydaci wymagają weryfikacji HUMAN.',
     NEEDS_OCR:'Wymagane OCR. Administrator musi skonfigurować lokalny Tesseract z polskim modelem.',
     FAILED:'Odczyt nie powiódł się: niepoprawny plik, limit, niedostępne OCR lub przekroczony czas.',
     EMPTY:'Nie odczytano tekstu.',UNSUPPORTED:'Nieobsługiwany format dokumentu.'};
   ingestionStatus.textContent=statuses[extraction.body.status]||'Nieznany wynik odczytu.';
 }else if(service==='upload_source'||service==='query_ingestion'){
   ingestionStatus.textContent='Operacja nie została zakończona. Sprawdź wynik i identyfikatory źródła. Kod: '+(extraction.code||value.code||'UNKNOWN');
 }
}
function showCandidate(){
const candidate=latestExtraction&&latestExtraction.body.candidates[Number(candidateIndex.value)];
candidateQuote.textContent=candidate?candidate.quote:'';
}
candidateIndex.onchange=showCandidate;
function canonicalIntake(value){
if(Array.isArray(value))return value.map(canonicalIntake);
if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonicalIntake(value[key])]));
return value;
}
document.getElementById('prepareReview').onclick=async()=>{
 const extraction=latestExtraction,current=generation;
 const index=Number(candidateIndex.value),revision=Number(document.getElementById('reviewRevision').value),
 disposition=document.getElementById('candidateDisposition').value,
 rationale=document.getElementById('candidateRationale').value.trim();
 if(!extraction||!knownCase()||!Number.isSafeInteger(index)||index<0||!Number.isSafeInteger(revision)||revision<0||!rationale||
   !['ADMIT','REJECT'].includes(disposition)||extraction.tenant_id!==tenant.value.trim()||extraction.case_id!==caseId.value.trim())return;
 const candidate=extraction.body.candidates[index];if(!candidate||!['FACT','EVIDENCE'].includes(candidate.kind))return;
 const bytes=new TextEncoder().encode(JSON.stringify(canonicalIntake(extraction)));
 const hash=Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',bytes)),b=>b.toString(16).padStart(2,'0')).join('');
 if(current!==generation)return;
 const data={source_id:extraction.source_id,run_id:extraction.run_id,result_hash:hash,candidate_index:index,
   expected_review_revision:revision,disposition};
 if(disposition==='ADMIT'){
   data.description=document.getElementById('candidateDescription').value.trim();
   if(!data.description)return;
   if(candidate.kind==='FACT'){data.statement=document.getElementById('candidateStatement').value.trim();if(!data.statement)return;}
 }
 const sequence=Number(caseSequence.value);if(!Number.isSafeInteger(sequence)||sequence<1)return;
 const body={contract:'urn:lukart:work:FactEvidenceRequest:1.0.0',operation:'ReviewCandidate',
   meta:{command_id:crypto.randomUUID(),tenant_id:tenant.value.trim(),case_id:caseId.value.trim(),
     idempotency_key:crypto.randomUUID(),expected_case_sequence:sequence,correlation_id:crypto.randomUUID()},data,rationale};
 route.value='execute_fact_evidence';request.value=JSON.stringify(body,null,2);advanced.open=true;
 result.textContent='Ocena przygotowana. Sprawdź szczegóły i osobno zatwierdź wysłanie jako uprawniony HUMAN.';
};
document.getElementById('viewFacts').onclick=()=>{
 if(!knownCase())return;
 query('query_fact_evidence',{contract:'urn:lukart:work:FactEvidenceQuery:1.0.0',operation:'GetFactEvidenceMatrix',
   tenant_id:tenant.value.trim(),case_id:caseId.value.trim()});
};
document.getElementById('confirmCase').onclick=()=>{
 try{
   const command=JSON.parse(request.value);
   if(route.value!=='execute_core'||command.operation!=='CreateCase')throw new Error();
   query('execute_core',command);
 }catch{result.textContent='Najpierw przygotuj i sprawdź żądanie nowej sprawy.';}
};
document.getElementById('uploadSource').onclick=async()=>{
 if(!knownCase())return;
 const sequence=Number(caseSequence.value),file=sourceFile.files&&sourceFile.files[0];
 const policy={id:policyId.value.trim(),version:policyVersion.value.trim(),content_hash:policyHash.value.trim().toLowerCase()};
 if(!Number.isSafeInteger(sequence)||sequence<1||!file||file.size>700*1024||file.size===0||
   !policy.id||!policy.version||!/^[0-9a-f]{64}$/.test(policy.content_hash)){
   ingestionStatus.textContent='Podaj sekwencję sprawy, politykę retencji i plik od 1 bajta do 700 KiB.';return;
 }
 const current=generation,scope=[tenant.value.trim(),caseId.value.trim()],capability=token.value;
 const button=document.getElementById('uploadSource');button.disabled=true;
 try{
   const bytes=new Uint8Array(await file.arrayBuffer());
   if(current!==generation||token.value!==capability||tenant.value.trim()!==scope[0]||caseId.value.trim()!==scope[1])return;
   let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
   const meta={command_id:crypto.randomUUID(),tenant_id:scope[0],case_id:scope[1],
     idempotency_key:crypto.randomUUID(),expected_case_sequence:sequence,correlation_id:crypto.randomUUID()};
   const body={operation:'UploadAndIngest',run_id:crypto.randomUUID(),request:{
     contract:'urn:lukart:work:CoreRequest:1.0.0',operation:'RegisterSource',meta,
     data:{content_base64:btoa(binary),media_type:file.type||(/\.txt$/i.test(file.name)?'text/plain':'application/octet-stream'),retention_policy:policy},
     rationale:'Dodanie dokumentu przez uprawnionego operatora'}};
   ingestionStatus.textContent='Zapis dokumentu i odczyt tekstu w toku (do 60 sekund).';
   // Preserve this exact request for an idempotent retry after transport failure.
   route.value='upload_source';request.value=JSON.stringify(body,null,2);
   await submit('upload_source',body);
 }catch{ingestionStatus.textContent='Nie udało się odczytać dokumentu. Sprawdź połączenie i wynik operacji.';}
 finally{button.disabled=false;}
};
for(const [button,operation] of [['readIngestion','ReadIngestion'],['retryIngestion','IngestSource']]){
 document.getElementById(button).onclick=()=>{
   if(!knownCase()||!idReady(sourceId.value))return;
   if(operation==='IngestSource')ingestionId.value=crypto.randomUUID();
   if(!idReady(ingestionId.value))return;
   ingestionStatus.textContent='Odczyt w toku…';
   query('query_ingestion',{operation,tenant_id:tenant.value.trim(),case_id:caseId.value.trim(),
     source_id:sourceId.value.trim(),run_id:ingestionId.value.trim()});
 };
}
