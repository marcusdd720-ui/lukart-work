(() => {
"use strict";
const $=id=>document.getElementById(id);
const state={opened:false,pending:0,revision:0,caseSequence:0,review:null,draft:null,composeDraft:null,composeValidation:null,composeUnknown:false};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function status(message,error=false){$("status").textContent=message;$("status").classList.toggle("error",error);}
function refresh(){const busy=state.pending>0;const selected=uuid.test($("render").value);for(const id of ["check","pdf","docx"])$(id).disabled=!state.opened||busy||!selected;$("open").disabled=busy;for(const id of ["intake-upload","intake-text-save"])$(id).disabled=!state.opened||busy;
const chosen=state.review?.candidates?.find(v=>String(v.index)===$("review-select").value);
for(const id of ["review-admit","review-reject"])$(id).disabled=!state.opened||busy||!chosen||chosen.review_status==="ADMIT";
$("draft-open").disabled=!state.opened||busy||!$("draft-select").value;
$("draft-save").disabled=!state.opened||busy||!state.draft?.editable;
$("compose-refresh").disabled=!state.opened||busy;
const composeBlocked=!state.opened||busy||state.composeUnknown;
$("compose-save").disabled=composeBlocked||!$("compose-type").value;
$("compose-generate").disabled=composeBlocked||!$("compose-plan").value||!$("compose-profile").value;
$("compose-validate").disabled=composeBlocked||!state.composeDraft;
$("compose-render").disabled=composeBlocked||!state.composeDraft||!state.composeValidation;
}
function close(){composeReset();state.revision++;state.opened=false;state.caseSequence=0;state.review=null;state.draft=null;$("draft-editor").hidden=true;$("draft-select").replaceChildren(new Option("Otwórz sprawę, aby zobaczyć projekty",""));$("draft-sections").replaceChildren();$("draft-rationale").value="";$("draft-result").textContent="Nie otwarto projektu.";$("review-panel").hidden=true;$("review-select").replaceChildren();$("review-quote").textContent="";$("review-statement").value="";$("review-description").value="";$("review-rationale").value="";$("review-result").textContent="Brak decyzji.";$("case-state").textContent="Nieotwarta";$("case-title").textContent="Tytuł sprawy pojawi się po odczycie";$("case-seq").textContent="—";$("heads").textContent="—";$("render").replaceChildren(new Option("Otwórz sprawę, aby wyświetlić dokumenty",""));$("render-count").textContent="Lista dokumentów nie została jeszcze pobrana.";$("intake-preview").hidden=true;$("intake-preview").textContent="";$("intake-candidates").replaceChildren();$("intake-proposals").hidden=true;$("intake-result").textContent="Dodaj dokument lub wpisz opis.";refresh();}
function scope(){
if(!$("token").value)throw new Error("Podaj token autoryzowanej sesji WORK.");
return {};
}
async function showUploadedSource(json){
if(!json.registration||!["APPLIED","REPLAYED"].includes(json.registration.state))
  throw new Error("Nie potwierdzono zapisu źródła.");
state.caseSequence=Number(json.registration.case_sequence);
$("case-seq").textContent=String(state.caseSequence);
const extraction=json.ingestion?.body;
$("intake-result").textContent="Oryginał zapisany. Odczyt: "+(extraction?.status||"NIEPOTWIERDZONY")+". Odczytane informacje wymagają przeglądu.";
const fragments=Array.isArray(extraction?.fragments)?extraction.fragments:[];
$("intake-preview").textContent=fragments.slice(0,12).map(v=>v.text).join("\n\n")||"Brak rozpoznanego tekstu; oryginał został zachowany.";
$("intake-preview").hidden=false;
const container=$("intake-candidates");container.replaceChildren();
const proposals=Array.isArray(extraction?.candidates)?extraction.candidates:[];
for(const proposal of proposals.filter(x=>["PARTY","DATE","AMOUNT"].includes(x.kind)).slice(0,15)){
 const item=document.createElement("li");item.textContent=proposal.kind+": "+String(proposal.quote||"").slice(0,260);container.append(item);
}
$("intake-proposals").hidden=container.childElementCount===0;
$("intake-file").value="";
status("Materiał dołączony do sprawy. Żadne fakty nie zostały automatycznie zatwierdzone.");
if(extraction?.status==="EXTRACTED"&&uuid.test(json.source_id)&&uuid.test(json.run_id))
 await invoke("review_context",{source_id:json.source_id,run_id:json.run_id});
}
async function invoke(action,extra={}) {
const args={action,...scope(),...extra};state.pending++;refresh();const generation=state.revision;
try {
  const response=await fetch("/api/embedded_session",{method:"POST",cache:"no-store",credentials:"omit",
    headers:{"Content-Type":"application/json","Authorization":"Bearer "+$("token").value},
    body:JSON.stringify(args)});
  if(generation!==state.revision)return null;
  if(!response.ok)throw new Error("Odmowa dostępu lub błąd operacji ("+response.status+").");
  if(action==="download"){
    const bytes=await response.blob();
    if(generation!==state.revision)return null;
    const url=URL.createObjectURL(bytes);
    const link=document.createElement("a");
    link.href=url;link.download="dokument."+extra.format.toLowerCase();document.body.appendChild(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    status("Pobrano istniejący "+extra.format+". Nie utworzono kolejnego renderu.");
    return true;
  }
  const json=await response.json();
  if(json.error||json.code||json.result_type==="DOMAIN_ERROR")throw new Error("Nie można odczytać danych sprawy.");
  if(action==="open_case"){
    if(json.result_type!=="CASE_HEAD")throw new Error("Nieprawidłowy wynik odczytu sprawy.");
    state.opened=true;state.caseSequence=Number(json.case_sequence);$("case-seq").textContent=String(json.case_sequence ?? "—");
    $("heads").textContent=Array.isArray(json.heads)?String(json.heads.length):"—";
    $("case-state").textContent="Otwarta";
    status("Sprawa odczytana z WORK. Silnik dokumentów działa w tle.");
    const caseRef=Array.isArray(json.heads)?json.heads.find(v=>v.kind==="Case"&&v.id?.toLowerCase()===json.case_id?.toLowerCase()):null;
    if(caseRef&&Number.isInteger(caseRef.revision)&&caseRef.revision>0){
      await invoke("case_title",{case_revision:caseRef.revision});
    }
    await invoke("list_saved");
    await invoke("list_drafts");
    await composeLoad();
  } else if(action==="case_title"){
    if(json.result_type!=="REVISION"||json.entity?.kind!=="Case")throw new Error("Brak zweryfikowanej wersji sprawy.");
    $("case-title").textContent=json.entity.title||"Sprawa bez tytułu";
    $("case-state").textContent=json.entity.status||"Otwarta";
    status("Pobrano aktualny tytuł i status sprawy bez zmiany danych.");
  } else if(action==="upload_source"){
    await showUploadedSource(json);
  } else if(action==="review_context"){
    if(json.result_type!=="REVIEW_CONTEXT"||!Array.isArray(json.candidates))
      throw new Error("Niepotwierdzony wynik przeglądu danych.");
    state.review=json;
    state.caseSequence=Number(json.case_sequence);
    $("case-seq").textContent=String(state.caseSequence);
    const select=$("review-select");select.replaceChildren();
    for(const row of json.candidates){
      select.add(new Option(row.kind+" · "+String(row.quote).slice(0,90)+
        (row.review_status==="PENDING"?"":" · "+row.review_status),String(row.index)));
    }
    $("review-panel").hidden=json.candidates.length===0;
    const selected=json.candidates[0];
    $("review-quote").textContent=selected?.quote||"";
    $("review-statement").value=selected?.kind==="FACT"?selected.quote:"";
    $("review-description").value=selected?.quote||"";
    $("review-result").textContent="Wymaga jawnej decyzji człowieka. Nie zatwierdzono automatycznie.";
    status("Odczytano kandydatów ze źródła. Wybierz i sprawdź dane.");
  } else if(action==="review_candidate"){
    if(json.result_type!=="REVIEW_RECEIPT"||!["APPLIED","REPLAYED"].includes(json.state))
      throw new Error("Brak potwierdzenia decyzji w WORK.");
    state.caseSequence=Number(json.case_sequence);
    $("case-seq").textContent=String(state.caseSequence);
    $("review-result").textContent=json.disposition==="ADMIT"?
      "Zapisano jako kandydata do dalszej weryfikacji — to jeszcze nie jest potwierdzony fakt.":
      "Zapisano odrzucenie kandydata.";
    $("review-rationale").value="";
    status("Decyzja HUMAN zapisana w istniejącej sprawie.");
    if(state.review)await invoke("review_context",{source_id:state.review.source_id,run_id:state.review.run_id});
  } else if(action==="list_drafts"){
    if(json.result_type!=="DRAFT_LIST"||!Array.isArray(json.drafts))throw new Error("Błąd listy projektów pisma.");
    const select=$("draft-select");select.replaceChildren(new Option("Wybierz projekt pisma",""));
    for(const item of json.drafts){
      if(!uuid.test(item.id)||!Number.isInteger(item.revision))continue;
      select.add(new Option("Projekt · rewizja "+item.revision+" · "+item.id.slice(0,8),
        item.id+"|"+item.revision));
    }
    $("draft-result").textContent=select.options.length===1?"Brak zapisanych projektów w tej sprawie.":
      "Znaleziono projektów: "+String(select.options.length-1);
  } else if(action==="open_draft"){
    if(json.result_type!=="DRAFT_FOR_EDITING"||!Array.isArray(json.sections))
      throw new Error("Nie potwierdzono odczytu projektu.");
    state.draft=json;
    state.composeDraft={id:json.draft_id,revision:json.revision};state.composeValidation=null;
    $("draft-editor").hidden=false;
    $("draft-details").textContent="Rewizja "+json.revision+" · "+json.status+
      (json.editable?" · edycja dostępna":" · tylko odczyt");
    const box=$("draft-sections");box.replaceChildren();
    for(const section of json.sections){
      const heading=document.createElement("h3");heading.textContent="Sekcja dokumentu";box.append(heading);
      for(const statement of section.statements){
        const label=document.createElement("label");label.textContent=statement.statement_type;
        const area=document.createElement("textarea");area.rows=5;area.value=statement.text;
        area.dataset.statementId=statement.statement_id;area.disabled=!json.editable;
        label.append(area);box.append(label);
      }
    }
    $("draft-result").textContent="Projekt odczytany. Zmieniaj tekst wyłącznie tam, gdzie jest dostępna edycja.";
  } else if(action==="amend_draft"){
    if(json.result_type!=="DRAFT_AMENDED"||!["APPLIED","REPLAYED"].includes(json.state))
      throw new Error("Nie potwierdzono zapisania zmian.");
    state.draft=null;$("draft-editor").hidden=true;
    state.composeDraft=null;state.composeValidation=null;
    $("draft-result").textContent="Poprawki zapisano jako nową wersję. Nie zatwierdzono ani nie wysłano pisma.";
    await invoke("open_case");
  } else if(action==="list_saved"){
    if(json.result_type!=="SAVED_RENDERS"||!Array.isArray(json.items))throw new Error("Nieprawidłowa lista dokumentów.");
    const select=$("render");select.replaceChildren(new Option("Wybierz zapisany dokument",""));
    for(const item of json.items){
      if(!uuid.test(item.render_id)||typeof item.created_at!=="string")continue;
      const date=new Date(item.created_at);
      const dateLabel=Number.isNaN(date.getTime())?"bez daty":date.toLocaleString("pl-PL");
      select.add(new Option((item.label||"Projekt")+" · "+dateLabel,item.render_id));
    }
    $("render-count").textContent="Znaleziono dokumentów: "+String(select.options.length-1);
    status("Lista dokumentów pobrana z WORK. Wybierz plik do odczytu.");
  } else status("Sprawdzono zapisany render. Status i decyzje pozostają w WORK.");
  return json;
}catch(error){if(generation===state.revision)status(error.message,true);return null;}
finally{state.pending=Math.max(0,state.pending-1);refresh();}
}
$("open").addEventListener("click",()=>{close();invoke("open_case");});
$("render").addEventListener("change",refresh);
function showReviewCandidate(){
const chosen=state.review?.candidates?.find(v=>String(v.index)===$("review-select").value);
$("review-quote").textContent=chosen?.quote||"";
$("review-statement").value=chosen?.kind==="FACT"?chosen.quote:"";
$("review-description").value=chosen?.quote||"";
$("review-result").textContent=chosen?.review_status==="ADMIT"?
  "Już przyjęto jako kandydata; dalsze decyzje w WORK.":"Wymaga decyzji HUMAN.";
refresh();
}
$("review-select").addEventListener("change",showReviewCandidate);
async function submitReview(disposition){
const chosen=state.review?.candidates?.find(v=>String(v.index)===$("review-select").value);
if(!chosen||!state.review||chosen.review_status==="ADMIT")return;
const rationale=$("review-rationale").value.trim();
if(!rationale)return $("review-result").textContent="Uzasadnij decyzję przed zapisaniem.";
if(!globalThis.crypto||typeof crypto.randomUUID!=="function")
  return $("review-result").textContent="Brak bezpiecznego generatora identyfikatorów.";
const decision={
 source_id:state.review.source_id,run_id:state.review.run_id,
 candidate_index:chosen.index,expected_case_sequence:state.caseSequence,
 disposition,rationale,command_id:crypto.randomUUID(),idempotency_key:crypto.randomUUID(),
 correlation_id:crypto.randomUUID(),
 statement:disposition==="ADMIT"&&chosen.kind==="FACT"?$("review-statement").value.trim():"",
 description:disposition==="ADMIT"?$("review-description").value.trim():"",
};
if(disposition==="ADMIT"&&(!decision.description||(chosen.kind==="FACT"&&!decision.statement)))
  return $("review-result").textContent="Wypełnij opis i brzmienie faktu.";
$("review-result").textContent="Zapisywanie jawnej decyzji HUMAN w WORK…";
await invoke("review_candidate",decision);
}
$("review-admit").addEventListener("click",()=>submitReview("ADMIT"));
$("review-reject").addEventListener("click",()=>submitReview("REJECT"));
$("draft-select").addEventListener("change",()=>{state.draft=null;$("draft-editor").hidden=true;refresh();});
$("draft-open").addEventListener("click",()=>{
  const [draft_id,raw] = $("draft-select").value.split("|");
  if(!uuid.test(draft_id)||!Number.isSafeInteger(Number(raw))||Number(raw)<1)
    return $("draft-result").textContent="Wybierz poprawny projekt.";
  invoke("open_draft",{draft_id,revision:Number(raw)});
});
$("draft-save").addEventListener("click",async()=>{
  const draft=state.draft;if(!draft?.editable)return;
  const rationale=$("draft-rationale").value.trim();
  if(!rationale)return $("draft-result").textContent="Podaj uzasadnienie poprawki.";
  const original=new Map(draft.sections.flatMap(s=>s.statements).map(s=>[s.statement_id,s.text]));
  const edits=[...$("draft-sections").querySelectorAll("textarea[data-statement-id]")]
    .filter(e=>e.value!==original.get(e.dataset.statementId))
    .map(e=>({statement_id:e.dataset.statementId,text:e.value}));
  if(!edits.length||edits.some(e=>!e.text.trim()))
    return $("draft-result").textContent="Zmień tekst dokumentu przed zapisaniem.";
  if(!globalThis.crypto||typeof crypto.randomUUID!=="function")
    return $("draft-result").textContent="Brak bezpiecznego generatora identyfikatorów.";
  $("draft-result").textContent="Zapisuję jawnie zatwierdzoną poprawkę w WORK…";
  await invoke("amend_draft",{draft_id:draft.draft_id,revision:draft.revision,
    draft_hash:draft.draft_hash,expected_case_sequence:draft.case_sequence,
    edits,rationale,command_id:crypto.randomUUID(),idempotency_key:crypto.randomUUID(),
    correlation_id:crypto.randomUUID()});
});
const uploadMime=(file)=>{const name=file.name.toLowerCase();if(name.endsWith(".pdf"))return "application/pdf";
  if(name.endsWith(".png"))return "image/png";
  if(name.endsWith(".jpg")||name.endsWith(".jpeg"))return "image/jpeg";
  if(name.endsWith(".tif")||name.endsWith(".tiff"))return "image/tiff";
  if(name.endsWith(".docx"))return "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
  if(name.endsWith(".txt"))return "text/plain";throw new Error("Nieobsługiwany format pliku.");};
function base64Of(bytes){let binary="";for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(binary);}
async function sendMaterial(bytes,mime){
  if(!state.opened||!Number.isSafeInteger(state.caseSequence)||state.caseSequence<1)throw new Error("Najpierw otwórz sprawę.");
  if(!bytes.length||bytes.length>700*1024)throw new Error("Plik jest pusty lub przekracza 700 KiB.");
  if(!globalThis.crypto||typeof crypto.randomUUID!=="function")throw new Error("Brak bezpiecznego generatora identyfikatorów.");
  const request={expected_case_sequence:state.caseSequence,command_id:crypto.randomUUID(),
    idempotency_key:crypto.randomUUID(),correlation_id:crypto.randomUUID(),run_id:crypto.randomUUID(),
    media_type:mime,content_base64:base64Of(bytes)};
  $("intake-result").textContent="Zapisywanie oryginału i odczyt OCR (może trwać do 60 sekund)…";
  return invoke("upload_source",request);
}
$("intake-upload").addEventListener("click",async()=>{
  const selected=$("intake-file").files?.[0];
  if(!selected)return $("intake-result").textContent="Wybierz plik do dodania.";
  try{
    const mime=uploadMime(selected);
    if(selected.size<1||selected.size>700*1024)throw new Error("Limit pliku wynosi 700 KiB.");
    const generation=state.revision;const bytes=new Uint8Array(await selected.arrayBuffer());
    if(generation!==state.revision)return;
    await sendMaterial(bytes,mime);
  }catch(err){$("intake-result").textContent=err.message;}
});
$("intake-text-save").addEventListener("click",async()=>{
  try{const value=$("intake-text").value.trim();
    if(!value)throw new Error("Wpisz opis sprawy.");
    const data=new TextEncoder().encode(value);
    const result=await sendMaterial(data,"text/plain");
    if(result)$("intake-text").value="";
  }catch(err){$("intake-result").textContent=err.message;}
});
$("check").addEventListener("click",()=>{if(!uuid.test($("render").value.trim()))return status("Podaj identyfikator renderu.",true);invoke("get_render",{render_id:$("render").value.trim()});});
for(const format of ["PDF","DOCX"])$(format.toLowerCase()).addEventListener("click",()=>{
  if(!uuid.test($("render").value.trim()))return status("Podaj identyfikator renderu.",true);
  invoke("download",{render_id:$("render").value.trim(),format});
});
function composeReset(){
state.composeDraft=null;state.composeValidation=null;
for(const id of ["compose-description",...['sender','recipient'].flatMap(role=>['name','lines','postal','country'].map(field=>'compose-'+role+'-'+field))])$(id).value='';
for(const id of ['compose-type','compose-plan','compose-profile'])$(id).replaceChildren(new Option('Otwórz autoryzowaną sprawę',''));
$("compose-gate").textContent='Wymagana autoryzowana sesja WORK.';$("compose-result").textContent='Nie rozpoczęto przygotowania pisma.';
}
async function composeRequest(action, extra={}){
const generation=state.revision;state.pending++;refresh();
try{
 const response=await fetch('/api/embedded_session',{method:'POST',cache:'no-store',credentials:'omit',
  headers:{'Content-Type':'application/json','Authorization':'Bearer '+$('token').value},body:JSON.stringify({action,...extra})});
 if(generation!==state.revision)throw new Error('Sesja została zmieniona. Odczytaj stan sprawy.');
 if(!response.ok)throw new Error('WORK odmówił operacji ('+response.status+'). Sprawdź sesję, bieżący plan, dane stron i wymagane decyzje.');
 const data=await response.json();
 if(generation!==state.revision)throw new Error('Sesja została zmieniona. Odczytaj stan sprawy.');
 if(data.error||data.result_type==='DOMAIN_ERROR')throw new Error('Operacja nie została potwierdzona przez WORK.');
 return data;
}finally{state.pending--;refresh();}
}
async function composeLoad(){
try{const data=await composeRequest('composition_context');
 if(data.result_type!=='COMPOSITION_CONTEXT'||!Array.isArray(data.document_types)||!Array.isArray(data.plans)||!Array.isArray(data.profiles))throw new Error('Nieprawidłowe warunki przygotowania pisma.');
 state.caseSequence=data.case_sequence;$('case-seq').textContent=String(data.case_sequence);
 const selected=$('compose-plan').value;
 for(const [id,items] of [['compose-type',data.document_types],['compose-plan',data.plans]]){
  const box=$(id);box.replaceChildren(new Option('Wybierz',''));for(const item of items)box.add(new Option(item.label,item.id));
  if(items.length===1)box.selectedIndex=1;if(id==='compose-plan'&&items.some(v=>v.id===selected))box.value=selected;
 }
 const profiles=$('compose-profile');profiles.replaceChildren();
 const names={QUICK:'Krótki',PROFESSIONAL:'Rozszerzony',FORENSIC:'Szczegółowy'};
 for(const profile of data.profiles)profiles.add(new Option(names[profile]||profile,profile));
 $('compose-plan').dataset.revisions=JSON.stringify(Object.fromEntries(data.plans.map(v=>[v.id,v.revision])));
 $('compose-plan').dataset.forms=JSON.stringify(Object.fromEntries(data.plans.filter(v=>v.form).map(v=>[v.id,v.form])));
 composePrefill();
 $('compose-gate').textContent=data.required_gate?'Brakuje zatwierdzonego planu WORK. Możesz zapisać dane; nie utworzy to akceptacji faktów ani danych stron.':'Odczytano zatwierdzony plan. Formularz musi odpowiadać jego opisowi i zweryfikowanym stronom.';
}catch(error){$('compose-gate').textContent=error.message;}finally{refresh();}
}
function composeForm(){
 const value={description:$('compose-description').value.trim(),document_type:$('compose-type').value,sender:null,recipient:null};
 for(const role of ['sender','recipient'])value[role]={name:$('compose-'+role+'-name').value.trim(),address:{
  country:$('compose-'+role+'-country').value.trim().toUpperCase(),postal_code:$('compose-'+role+'-postal').value.trim(),
  lines:$('compose-'+role+'-lines').value.split(/\r?\n/).map(v=>v.trim()).filter(Boolean)}};
 if(!value.description||!value.document_type||['sender','recipient'].some(role=>!value[role].name||!value[role].address.lines.length||!value[role].address.postal_code||!/^[A-Z]{2}$/.test(value[role].address.country)))throw new Error('Uzupełnij opis, rodzaj pisma oraz pełne nazwy i adresy obu stron.');
 return value;
}
async function composePerform(action){
 if(state.composeUnknown)return;
 let extra={};
 try{
  if(['save_document_brief','generate_document'].includes(action))extra.form=composeForm();
  if(action==='generate_document')Object.assign(extra,{plan_id:$('compose-plan').value,plan_revision:JSON.parse($('compose-plan').dataset.revisions||'{}')[$('compose-plan').value],profile:$('compose-profile').value});
  if(['validate_document','render_document'].includes(action)){
   if(!state.composeDraft)throw new Error('Najpierw przygotuj lub otwórz projekt.');
   Object.assign(extra,{draft_id:state.composeDraft.id,draft_revision:state.composeDraft.revision});
  }
  if(action==='render_document')extra.validation_run_id=state.composeValidation;
  Object.assign(extra,{expected_case_sequence:state.caseSequence,command_id:crypto.randomUUID(),idempotency_key:crypto.randomUUID(),correlation_id:crypto.randomUUID()});
  if(action==='save_document_brief')extra.run_id=crypto.randomUUID();
 }catch(error){$('compose-result').textContent=error.message;return;}
 try{
  const data=await composeRequest(action,extra);
  const wanted={save_document_brief:'DOCUMENT_BRIEF_SAVED',generate_document:'DOCUMENT_GENERATED',validate_document:'DOCUMENT_VALIDATED',render_document:'DOCUMENT_RENDERED'}[action];
  if(data.result_type!==wanted)throw new Error('WORK nie potwierdził oczekiwanego wyniku.');
  if(data.draft){state.composeDraft=data.draft;state.composeValidation=null;}
  if(data.validation_run_id)state.composeValidation=data.validation_run_id;
  $('compose-result').textContent=action==='save_document_brief'?'Zapisano dane jako materiał źródłowy. Wymagane pozostają przegląd i zatwierdzony plan.':action==='generate_document'?'Generator 2.0 przygotował projekt. Możesz otworzyć go w edytorze poniżej.':action==='validate_document'?'Przeprowadzono kontrolę projektu. Renderer niezależnie sprawdzi wymagane bramki; nie zatwierdzono pisma.':'Zapisano DOCX i PDF. Pobierz je w sekcji Dokumenty sprawy.';
  if(action==='save_document_brief')await showUploadedSource(data.native_result);
  await composeLoad();await invoke('list_drafts');
  if(action==='render_document'){await invoke('list_saved');$('render').value=data.render_id;}
 }catch(error){state.composeUnknown=true;$('compose-result').textContent=error.message+' Nie ponawiaj zapisu automatycznie. Sprawdź stan WORK w autoryzowanej sesji.';}
 finally{refresh();}
}
$('compose-refresh').addEventListener('click',composeLoad);
function composePrefill(){
 const form=JSON.parse($('compose-plan').dataset.forms||'{}')[$('compose-plan').value];if(!form){refresh();return;}
 if(!$('compose-description').value.trim())$('compose-description').value=form.description;
 for(const role of ['sender','recipient'])for(const [field,value] of Object.entries({name:form[role].name,lines:form[role].address.lines.join('\n'),postal:form[role].address.postal_code,country:form[role].address.country})){
  const input=$('compose-'+role+'-'+field);if(!input.value.trim())input.value=value||'';
 }
 refresh();
}
$('compose-plan').addEventListener('change',composePrefill);
for(const [id,action] of [['compose-save','save_document_brief'],['compose-generate','generate_document'],['compose-validate','validate_document'],['compose-render','render_document']])$(id).addEventListener('click',()=>composePerform(action));
$("clear").addEventListener("click",()=>{composeReset();close();for(const id of ["token","render"])$(id).value="";status("Sesja wyczyszczona.");});
window.addEventListener("pagehide",()=>{close();for(const id of ["token","render"])$(id).value="";});
$("token").addEventListener("input",close);
refresh();
})();