"""Case-centric LEGAL OS page, served by the existing authenticated WORK host.

No separate process, database, or GENERATOR user interface. This is the
first read-only integration increment; all document mutations remain with WORK.
"""
from __future__ import annotations

from typing import Any
from lukart_work.embedded_document_engine import (
    CaseScope, EmbeddedDocumentEngine, EngineBoundaryError, SavedArtifact,
)
from lukart_work.contracts.messages import DomainError


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
    <p class="hint">Wersja integracyjna korzysta z istniejących danych sesji WORK. Docelowe logowanie zastąpi ręczne identyfikatory.</p>
    <div class="fields">
      <label>Token uprawnienia <input type="password" id="token" autocomplete="off" spellcheck="false" aria-label="Token uprawnienia"></label>
      <label>Identyfikator przestrzeni <input type="text" id="tenant" autocomplete="off" spellcheck="false" placeholder="Tenant UUID"></label>
      <label>Identyfikator sprawy <input type="text" id="case" autocomplete="off" spellcheck="false" placeholder="Case UUID"></label>
    </div>
    <div class="actions"><button id="open" type="button">Otwórz sprawę</button><button id="clear" class="secondary" type="button">Wyczyść sesję</button></div>
  </section>
  <section class="panel" aria-labelledby="overview-title">
    <div class="panel-heading"><h2 id="overview-title">Stan sprawy</h2><span class="pill neutral" id="case-state">Nieotwarta</span></div>
    <div class="metricrow"><div><div class="metric" id="case-seq">—</div><div class="small">Wersja sprawy</div></div><div><div class="metric" id="heads">—</div><div class="small">Aktywne rekordy</div></div></div>
    <p class="hint">Ten panel odczytuje stan bezpośrednio z istniejącego Case Core. Nie jest drugą bazą spraw.</p>
  </section>
  <section class="panel" aria-labelledby="docs-title">
    <div class="panel-heading"><h2 id="docs-title">Dokumenty sprawy</h2><span class="pill neutral">Bez ponownego renderowania</span></div>
    <p class="hint">W tym inkremencie można otworzyć już zapisany render. Lista dokumentów pojawi się po udostępnieniu autoryzowanego katalogu renderów przez WORK.</p>
    <label>Identyfikator zapisanego dokumentu <input type="text" id="render" autocomplete="off" spellcheck="false" placeholder="Render UUID"></label>
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
input{font:inherit;width:100%;padding:12px 13px;border:1px solid #cbd6e1;border-radius:8px;background:#fff;color:#17243b}
input:focus-visible,button:focus-visible{outline:3px solid #a7d5cb;outline-offset:2px}
.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:17px}button{cursor:pointer;border:0;border-radius:8px;padding:12px 18px;font-weight:660;background:#227c71;color:#fff}
button.secondary{background:#eef3f6;color:#25394d}button:disabled{opacity:.45;cursor:not-allowed}
.metricrow{display:flex;gap:54px;padding:20px 0}.metric{font-size:29px;font-weight:740}.small{font-size:12px}
.status{padding:15px 19px;border-radius:8px;border:1px solid #d6dfe7;background:#fff;white-space:pre-wrap;overflow-wrap:anywhere}
.status.error{color:#a32035;border-color:#e9bcc4;background:#fff7f8}footer{font-size:12px;padding:18px 0 34px;border-top:1px solid #dce3ea}
@media(max-width:600px){header{align-items:flex-start;flex-direction:column;gap:3px}.shell{padding:0 15px}.panel{padding:18px}.metricrow{gap:28px}}'''.encode("utf-8")

CASE_JS = r'''(() => {
"use strict";
const $=id=>document.getElementById(id);
const state={opened:false,busy:false,revision:0};
const uuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
function status(message,error=false){$("status").textContent=message;$("status").classList.toggle("error",error);}
function refresh(){for(const id of ["check","pdf","docx"])$(id).disabled=!state.opened||state.busy;$("open").disabled=state.busy;}
function close(){state.revision++;state.opened=false;$("case-state").textContent="Nieotwarta";$("case-seq").textContent="—";$("heads").textContent="—";refresh();}
function scope(){const tenant_id=$("tenant").value.trim(),case_id=$("case").value.trim();
if(!uuid.test(tenant_id)||!uuid.test(case_id))throw new Error("Sprawdź identyfikatory przestrzeni i sprawy.");
if(!$("token").value)throw new Error("Podaj token autoryzowanej sesji WORK.");
return {tenant_id,case_id};}
async function invoke(action,extra={}) {
const args={action,...scope(),...extra};state.busy=true;refresh();const generation=state.revision;
try {
  const response=await fetch("/api/embedded_case",{method:"POST",cache:"no-store",credentials:"omit",
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
    state.opened=true;$("case-seq").textContent=String(json.case_sequence ?? "—");
    $("heads").textContent=Array.isArray(json.heads)?String(json.heads.length):"—";
    $("case-state").textContent="Otwarta";
    status("Sprawa odczytana z WORK. Silnik dokumentów działa w tle.");
  } else status("Sprawdzono zapisany render. Status i decyzje pozostają w WORK.");
  return json;
}catch(error){if(generation===state.revision)status(error.message,true);return null;}
finally{state.busy=false;refresh();}
}
$("open").addEventListener("click",()=>{close();invoke("open_case");});
$("check").addEventListener("click",()=>{if(!uuid.test($("render").value.trim()))return status("Podaj identyfikator renderu.",true);invoke("get_render",{render_id:$("render").value.trim()});});
for(const format of ["PDF","DOCX"])$(format.toLowerCase()).addEventListener("click",()=>{
  if(!uuid.test($("render").value.trim()))return status("Podaj identyfikator renderu.",true);
  invoke("download",{render_id:$("render").value.trim(),format});
});
$("clear").addEventListener("click",()=>{close();for(const id of ["token","tenant","case","render"])$(id).value="";status("Sesja wyczyszczona.");});
window.addEventListener("pagehide",()=>{close();for(const id of ["token","tenant","case","render"])$(id).value="";});
for(const id of ["tenant","case"])$(id).addEventListener("input",close);
refresh();
})();'''.encode("utf-8")


def read_case_action(operator: Any, payload: dict[str, Any], token: str):
    """Strict read-only dispatcher for a validated, scoped WORK session."""
    if not isinstance(payload, dict):
        raise EngineBoundaryError("CASE_REQUEST_OBJECT_REQUIRED")
    action = payload.get("action")
    fields = {
        "open_case": {"action", "tenant_id", "case_id"},
        "get_render": {"action", "tenant_id", "case_id", "render_id"},
        "download": {"action", "tenant_id", "case_id", "render_id", "format"},
    }
    if action not in fields or set(payload) != fields[action]:
        raise EngineBoundaryError("CASE_OPERATION_NOT_ALLOWED")
    scope = CaseScope(payload["tenant_id"], payload["case_id"])
    engine = EmbeddedDocumentEngine(operator)
    if action == "open_case":
        result = engine.open_case(scope, token=token)
    elif action == "get_render":
        result = engine.get_render(scope, payload["render_id"], token=token)
    else:
        result = engine.download_saved(scope, payload["render_id"], payload["format"], token=token)
    if isinstance(result, DomainError):
        raise EngineBoundaryError("WORK_READ_DENIED")
    return result
