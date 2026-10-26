"""Case-centric LEGAL OS page, served by the existing authenticated WORK host.

No separate process, database, or GENERATOR user interface. This is the
first read-only integration increment; all document mutations remain with WORK.
"""
from __future__ import annotations

from typing import Any
from lukart_work.embedded_document_engine import (
    CaseScope, EmbeddedDocumentEngine, EngineBoundaryError, SavedArtifact,
)
from lukart_work.contracts.messages import DomainError, CaseHeadResult, RevisionResult


CASE_HTML = r'''<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LUKART LEGAL OS — Moja sprawa</title><link rel="stylesheet" href="/case.css"></head>
<body><div class="shell">
<header><div class="brand">LUKART <span>LEGAL OS</span></div><small>Prywatna karta sprawy · silnik dokumentowy działa w tle</small></header>
<main>
  <div class="eyebrow">PRZESTRZEŃ SPRAWY</div>
  <h1>Moja sprawa</h1>
  <p class="lead">Otwieraj zapisane sprawy i dokumenty w jednym miejscu. Oryginały oraz decyzje pozostają w bazie WORK. Ten widok niczego nie zatwierdza ani nie zmienia.</p>
  <section class="panel" aria-labelledby="connect-title">
    <div class="panel-heading"><h2 id="connect-title">Połączenie z prywatną sprawą</h2><span class="pill">Lokalnie</span></div>
    <p class="hint">Sesja WORK automatycznie wskazuje właściwą sprawę. Nie podawaj identyfikatorów technicznych. Wersja lokalna wymaga jeszcze tokenu; docelowo zastąpi go logowanie.</p>
    <div class="fields">
      <label>Token prywatnej sesji WORK <input type="password" id="token" autocomplete="off" spellcheck="false" aria-label="Token sesji WORK"></label>
    </div>
    <div class="actions"><button id="open" type="button">Otwórz sprawę</button><button id="clear" class="secondary" type="button">Wyczyść sesję</button></div>
  </section>
  <section class="panel" aria-labelledby="overview-title">
    <div class="panel-heading"><h2 id="overview-title">Stan sprawy</h2><span class="pill neutral" id="case-state">Nieotwarta</span></div>
    <h3 id="case-title" class="casetitle">Tytuł sprawy pojawi się po odczycie</h3>
    <div class="metricrow"><div><div class="metric" id="case-seq">—</div><div class="small">Wersja sprawy</div></div><div><div class="metric" id="heads">—</div><div class="small">Aktywne rekordy</div></div></div>
    <p class="hint">Ten panel odczytuje stan bezpośrednio z istniejącego Case Core. Nie jest drugą bazą spraw.</p>
  </section>
  <section class="panel" aria-labelledby="intake-title">
    <div class="panel-heading"><h2 id="intake-title">Dodaj materiał do sprawy</h2><span class="pill neutral">OCR lokalny</span></div>
    <p class="hint">Oryginał zostaje zapisany bez zmian. Rozpoznany tekst i dane są kandydatami do sprawdzenia, a nie automatycznie potwierdzonymi faktami.</p>
    <label>Wybierz pismo lub skan <input type="file" id="intake-file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.docx,.txt"></label>
    <div class="actions"><button id="intake-upload" type="button" disabled>Dodaj dokument i odczytaj tekst</button></div>
    <label>Lub wprowadź własny opis sprawy <textarea id="intake-text" rows="5" placeholder="Opisz sytuację własnymi słowami, nawet jeśli nie masz dokumentu."></textarea></label>
    <div class="actions"><button id="intake-text-save" type="button" disabled>Zapisz opis do sprawy</button></div>
    <p id="intake-result" class="hint" role="status" aria-live="polite">Obsługiwane: PDF, JPG, PNG, TIFF, DOCX, TXT i tekst. Obecny limit: 700 KiB na plik. BMP wymaga osobnego adaptera.</p>
    <pre id="intake-preview" class="intake-preview" hidden></pre>
    <div id="intake-proposals" hidden><h3>Wykryte informacje — do weryfikacji</h3><ul id="intake-candidates"></ul></div>
  </section>
  <section class="panel" aria-labelledby="docs-title">
    <div class="panel-heading"><h2 id="docs-title">Dokumenty sprawy</h2><span class="pill neutral">Bez ponownego renderowania</span></div>
    <p class="hint">Wybierz projekt zapisany w tej sprawie. Dokument jest odczytywany z WORK bez regenerowania i bez dodatkowych identyfikatorów.</p>
    <label>Zapisane dokumenty <select id="render" aria-label="Wybierz zapisany dokument"><option value="">Otwórz sprawę, aby wyświetlić dokumenty</option></select></label>
    <p class="hint" id="render-count">Lista dokumentów nie została jeszcze pobrana.</p>
    <div class="actions">
      <button id="check" type="button" class="secondary" disabled>Sprawdź dokument</button>
      <button id="pdf" type="button" disabled>Pobierz PDF</button>
      <button id="docx" type="button" disabled>Pobierz DOCX</button>
    </div>
  </section>
  <p id="status" class="status" role="status" aria-live="polite">Połącz się z istniejącą sprawą.</p>
</main><footer>Generator Pism 2.0: silnik wewnętrzny · HUMAN approvals: wyłącznie przez autoryzowane operacje WORK</footer>
</div><script src="/case.js"></script></body></html>'''.encode("utf-8")

CASE_CSS = r'''*{box-sizing:border-box}body{margin:0;background:#f6f8fa;color:#17243b;font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif}
.shell{max-width:1040px;margin:auto;padding:0 24px}header{display:flex;gap:20px;justify-content:space-between;align-items:center;padding:25px 0;border-bottom:1px solid #dce3ea}
.brand{font-weight:780;letter-spacing:.04em;font-size:19px}.brand span{color:#227c71}header small,footer,.small,.hint{color:#64748b}
main{padding:32px 0 50px}.eyebrow{font-size:11px;font-weight:740;letter-spacing:.18em;color:#227c71}h1{font-size:34px;margin:8px 0}h2{margin:0;font-size:19px}.lead{max-width:760px;line-height:1.6;color:#50617c}
.panel{margin:22px 0;padding:25px;border:1px solid #dae2e9;border-radius:14px;background:#fff;box-shadow:0 2px 9px #15263a08}
.panel-heading{display:flex;justify-content:space-between;align-items:center;gap:12px}.pill{border-radius:20px;background:#e3f3ef;padding:6px 12px;color:#226f65;font-size:12px;font-weight:650}
.pill.neutral{background:#f1f4f8;color:#53647b}.hint{font-size:13px;line-height:1.55}
.fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(225px,1fr));gap:14px}label{display:flex;flex-direction:column;gap:8px;margin-top:12px;font-weight:620;font-size:13px}
input,select{font:inherit;width:100%;padding:12px 13px;border:1px solid #cbd6e1;border-radius:8px;background:#fff;color:#17243b}
input:focus-visible,button:focus-visible{outline:3px solid #a7d5cb;outline-offset:2px}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:17px}button{cursor:pointer;border:0;border-radius:8px;padding:12px 18px;font-weight:660;background:#227c71;color:#fff}
button.secondary{background:#eef3f6;color:#25394d}button:disabled{opacity:.45;cursor:not-allowed}
.casetitle{font-size:16px;font-weight:690;margin:18px 0 4px}.metricrow{display:flex;gap:54px;padding:20px 0}.metric{font-size:29px;font-weight:740}.small{font-size:12px}
.intake-preview{background:#f6f8fa;border:1px solid #dce3ea;border-radius:8px;padding:12px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:340px;overflow:auto;font-size:13px}
textarea{width:100%;font:inherit;border:1px solid #cbd6e1;border-radius:8px;padding:12px;resize:vertical}
.status{padding:15px 19px;border-radius:8px;border:1px solid #d6dfe7;background:#fff;white-space:pre-wrap;overflow-wrap:anywhere}
.status.error{color:#a32035;border-color:#e9bcc4;background:#fff7f8}footer{font-size:12px;padding:18px 0 34px;border-top:1px solid #dce3ea}
@media(max-width:600px){header{align-items:flex-start;flex-direction:column;gap:3px}.shell{padding:0 15px}.panel{padding:18px}.metricrow{gap:28px}}'''.encode("utf-8")

CASE_JS = r'''(() => {
"use strict";
const $=id=>document.getElementById(id);
const state={opened:false,pending:0,revision:0,caseSequence:0};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function status(message,error=false){$("status").textContent=message;$("status").classList.toggle("error",error);}
function refresh(){const busy=state.pending>0;const selected=uuid.test($("render").value);for(const id of ["check","pdf","docx"])$(id).disabled=!state.opened||busy||!selected;$("open").disabled=busy;for(const id of ["intake-upload","intake-text-save"])$(id).disabled=!state.opened||busy;}
function close(){state.revision++;state.opened=false;state.caseSequence=0;$("case-state").textContent="Nieotwarta";$("case-title").textContent="Tytuł sprawy pojawi się po odczycie";$("case-seq").textContent="—";$("heads").textContent="—";$("render").replaceChildren(new Option("Otwórz sprawę, aby wyświetlić dokumenty",""));$("render-count").textContent="Lista dokumentów nie została jeszcze pobrana.";$("intake-preview").hidden=true;$("intake-preview").textContent="";$("intake-candidates").replaceChildren();$("intake-proposals").hidden=true;$("intake-result").textContent="Dodaj dokument lub wpisz opis.";refresh();}
function scope(){
if(!$("token").value)throw new Error("Podaj token autoryzowanej sesji WORK.");
return {};
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
  } else if(action==="case_title"){
    if(json.result_type!=="REVISION"||json.entity?.kind!=="Case")throw new Error("Brak zweryfikowanej wersji sprawy.");
    $("case-title").textContent=json.entity.title||"Sprawa bez tytułu";
    $("case-state").textContent=json.entity.status||"Otwarta";
    status("Pobrano aktualny tytuł i status sprawy bez zmiany danych.");
  } else if(action==="upload_source"){
    if(!json.registration||!["APPLIED","REPLAYED"].includes(json.registration.state))
      throw new Error("Nie potwierdzono zapisu źródła.");
    state.caseSequence=Number(json.registration.case_sequence);
    $("case-seq").textContent=String(state.caseSequence);
    const extraction=json.ingestion?.body;
    const kind=extraction?.status||"NIEPOTWIERDZONY";
    $("intake-result").textContent="Oryginał zapisany. Odczyt: "+kind+". Odczytane informacje wymagają przeglądu.";
    const fragments=Array.isArray(extraction?.fragments)?extraction.fragments:[];
    const preview=fragments.slice(0,12).map(v=>v.text).join("\n\n");
    $("intake-preview").textContent=preview||"Brak rozpoznanego tekstu; oryginał został zachowany.";
    $("intake-preview").hidden=false;
    const container=$("intake-candidates");container.replaceChildren();
    const proposals=Array.isArray(extraction?.candidates)?extraction.candidates:[];
    for(const proposal of proposals.filter(x=>["PARTY","DATE","AMOUNT"].includes(x.kind)).slice(0,15)){
      const item=document.createElement("li");
      item.textContent=proposal.kind+": "+String(proposal.quote||"").slice(0,260);
      container.append(item);
    }
    $("intake-proposals").hidden=container.childElementCount===0;
    $("intake-file").value="";
    status("Materiał dołączony do sprawy. Żadne fakty nie zostały automatycznie zatwierdzone.");
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
$("clear").addEventListener("click",()=>{close();for(const id of ["token","render"])$(id).value="";status("Sesja wyczyszczona.");});
window.addEventListener("pagehide",()=>{close();for(const id of ["token","render"])$(id).value="";});
$("token").addEventListener("input",close);
refresh();
})();'''.encode("utf-8")


def read_case_action(operator: Any, payload: dict[str, Any], token: str):
    """Strict read-only dispatcher for a validated, scoped WORK session."""
    if not isinstance(payload, dict):
        raise EngineBoundaryError("CASE_REQUEST_OBJECT_REQUIRED")
    action = payload.get("action")
    fields = {
        "open_case": {"action", "tenant_id", "case_id"},
        "case_title": {"action", "tenant_id", "case_id", "case_revision"},
        "list_saved": {"action", "tenant_id", "case_id"},
        "get_render": {"action", "tenant_id", "case_id", "render_id"},
        "download": {"action", "tenant_id", "case_id", "render_id", "format"},
    }
    if action not in fields or set(payload) != fields[action]:
        raise EngineBoundaryError("CASE_OPERATION_NOT_ALLOWED")
    scope = CaseScope(payload["tenant_id"], payload["case_id"])
    engine = EmbeddedDocumentEngine(operator)
    if action == "open_case":
        result = engine.open_case(scope, token=token)
    elif action == "list_saved":
        result = engine.list_saved(scope, token=token)
    elif action == "case_title":
        revision = payload["case_revision"]
        if type(revision) is not int or not 1 <= revision <= 1_000_000_000:
            raise EngineBoundaryError("CASE_REVISION_INVALID")
        head = engine.open_case(scope, token=token)
        if not isinstance(head, CaseHeadResult) or len([
            ref for ref in head.heads if ref.kind == "Case"
            and str(ref.id) == scope.case_id and ref.revision == revision
        ]) != 1:
            raise EngineBoundaryError("CASE_REVISION_NOT_CURRENT")
        result = operator.query_core({
            "contract": "urn:lukart:work:CoreQuery:1.0.0",
            "operation": "GetRevision",
            "tenant_id": scope.tenant_id, "case_id": scope.case_id,
            "target": {"kind": "Case", "id": scope.case_id, "revision": revision},
        }, token)
        if not isinstance(result, RevisionResult) or result.entity.kind != "Case":
            raise EngineBoundaryError("CASE_REVISION_READ_REJECTED")
        if str(result.entity.id) != scope.case_id or result.entity.revision != revision:
            raise EngineBoundaryError("CASE_REVISION_MISMATCH")
    elif action == "get_render":
        result = engine.get_render(scope, payload["render_id"], token=token)
    else:
        result = engine.download_saved(scope, payload["render_id"], payload["format"], token=token)
    if isinstance(result, DomainError):
        raise EngineBoundaryError("WORK_READ_DENIED")
    return result


def read_session_case_action(operator: Any, payload: dict[str, Any], token: str):
    """Derive the canonical CASE from a trusted authenticated WORK principal.

    The browser must never select another tenant/case by passing identifiers.
    Native WORK read capability checks remain authoritative in read_case_action.
    """
    if not isinstance(payload, dict):
        raise EngineBoundaryError("SESSION_REQUEST_OBJECT_REQUIRED")
    allowed = {
        "open_case": {"action"},
        "case_title": {"action", "case_revision"},
        "list_saved": {"action"},
        "upload_source": {"action", "media_type", "content_base64", "expected_case_sequence", "command_id", "idempotency_key", "correlation_id", "run_id"},
        "get_render": {"action", "render_id"},
        "download": {"action", "render_id", "format"},
    }
    action = payload.get("action")
    if action not in allowed or set(payload) != allowed[action]:
        raise EngineBoundaryError("SESSION_OPERATION_NOT_ALLOWED")
    with operator.core.authority.session(token) as principal:
        if principal.actor.kind == "AI":
            raise EngineBoundaryError("AI_SESSION_DENIED")
        tenant, case = principal.tenant_id, principal.case_id
    if action == "upload_source":
        from lukart_work.legal_os_intake import upload_case_source
        return upload_case_source(operator, payload, token)
    return read_case_action(
        operator,
        dict(payload, tenant_id=str(tenant), case_id=str(case)),
        token,
    )
