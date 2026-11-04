"""Case-centric LEGAL OS page, served by the existing authenticated WORK host.

No separate process, database, or GENERATOR user interface. Source intake,
drafting, validation and rendering delegate to authoritative WORK services.
"""
from __future__ import annotations

from typing import Any, cast

from lukart_work.contracts.messages import CaseHeadResult, DomainError, RevisionResult
from lukart_work.domain.models import Case
from lukart_work.embedded_document_engine import (
    CaseScope,
    EmbeddedDocumentEngine,
    EngineBoundaryError,
)

CASE_HTML = r'''<!doctype html>
<html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>LUKART LEGAL OS — Moja sprawa</title><link rel="stylesheet" href="/case.css"></head>
<body><div class="shell">
<header><div class="brand">LUKART <span>LEGAL OS</span></div><small>Prywatna karta sprawy · silnik dokumentowy działa w tle</small></header>
<main>
  <div class="eyebrow">PRZESTRZEŃ SPRAWY</div>
  <h1>Moja sprawa</h1>
  <p class="lead">Opisz sprawę, przygotuj projekt i pobierz dokumenty w jednym miejscu. Oryginały i historia pozostają w WORK, a wymagane decyzje należą do człowieka.</p>
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
    <section id="review-panel" hidden aria-label="Weryfikacja materiału">
      <h3>Fakty i dowody — przegląd HUMAN</h3>
      <p class="hint">Odczyt OCR nie jest dowodem prawdziwości. Decyzja PRZYJMIJ tworzy kandydata do dalszej oceny, nie potwierdzony fakt.</p>
      <label>Kandydat ze źródła <select id="review-select"></select></label>
      <blockquote id="review-quote" class="review-quote"></blockquote>
      <label>Opis materiału <input id="review-description" autocomplete="off"></label>
      <label>Proponowane brzmienie faktu (dla faktu) <textarea id="review-statement" rows="3"></textarea></label>
      <label>Uzasadnienie decyzji <textarea id="review-rationale" rows="2" placeholder="Dlaczego przyjmujesz lub odrzucasz ten materiał?"></textarea></label>
      <div class="actions"><button type="button" id="review-admit" disabled>Przyjmij jako kandydata</button><button type="button" id="review-reject" class="secondary" disabled>Odrzuć</button></div>
      <p id="review-result" class="hint" role="status" aria-live="polite">Brak decyzji.</p>
    </section>
  </section>
  <section class="panel" aria-labelledby="compose-title">
    <div class="panel-heading"><h2 id="compose-title">Przygotuj pismo</h2><span class="pill neutral">Generator 2.0 w tle</span></div>
    <p class="hint">Zapisz komplet danych jako materiał sprawy. Generowanie korzysta z zatwierdzonego planu WORK i zweryfikowanych danych stron; zapis formularza nie tworzy tych zatwierdzeń.</p>
    <label>Rodzaj pisma <select id="compose-type"><option value="">Otwórz sprawę, aby odczytać dostępny profil</option></select></label>
    <label>Opis sprawy i cel pisma <textarea id="compose-description" rows="5" maxlength="20000" placeholder="Opisz sytuację własnymi słowami i wskaż, czego oczekujesz."></textarea></label>
    <div class="fields">
      <fieldset><legend>Nadawca</legend>
        <label>Imię i nazwisko / pełna nazwa <input id="compose-sender-name" maxlength="500" autocomplete="off"></label>
        <label>Ulica, numer oraz miejscowość <textarea id="compose-sender-lines" rows="3" placeholder="ul. Przykładowa 1/2&#10;Warszawa"></textarea></label>
        <label>Kod pocztowy <input id="compose-sender-postal" autocomplete="off"></label>
        <label>Kraj — kod dwuliterowy <input id="compose-sender-country" maxlength="2" placeholder="PL" autocomplete="off"></label>
      </fieldset>
      <fieldset><legend>Adresat</legend>
        <label>Imię i nazwisko / pełna nazwa <input id="compose-recipient-name" maxlength="500" autocomplete="off"></label>
        <label>Ulica, numer oraz miejscowość <textarea id="compose-recipient-lines" rows="3" placeholder="ul. Testowa 3&#10;Warszawa"></textarea></label>
        <label>Kod pocztowy <input id="compose-recipient-postal" autocomplete="off"></label>
        <label>Kraj — kod dwuliterowy <input id="compose-recipient-country" maxlength="2" placeholder="PL" autocomplete="off"></label>
      </fieldset>
    </div>
    <div class="actions"><button id="compose-save" type="button" disabled>Zapisz komplet danych do sprawy</button><button id="compose-refresh" type="button" class="secondary" disabled>Sprawdź gotowość sprawy</button></div>
    <p id="compose-gate" class="hint">Wymagana autoryzowana sesja WORK. Nie podawaj hasła Windows.</p>
    <label>Zatwierdzony plan pisma <select id="compose-plan"><option value="">Brak odczytanych planów</option></select></label>
    <label>Zakres opracowania <select id="compose-profile"><option value="">Brak odczytanych profili</option></select></label>
    <div class="actions"><button id="compose-generate" type="button" disabled>Przygotuj projekt pisma</button><button id="compose-validate" type="button" class="secondary" disabled>Sprawdź projekt</button><button id="compose-render" type="button" disabled>Utwórz DOCX i PDF</button></div>
    <p id="compose-result" class="hint" role="status" aria-live="polite">Nie rozpoczęto przygotowania pisma.</p>
  </section>
  <section class="panel" aria-labelledby="editor-title">
    <div class="panel-heading"><h2 id="editor-title">Projekt pisma — edytor</h2><span class="pill neutral">Historia w WORK</span></div>
    <p class="hint">Wybierz istniejący projekt tej sprawy. Edytujesz cały tekst pisma, ale zapis poprawek nie jest zatwierdzeniem ani wysyłką.</p>
    <label>Projekty pisma <select id="draft-select"><option value="">Otwórz sprawę, aby zobaczyć projekty</option></select></label>
    <div class="actions"><button id="draft-open" type="button" class="secondary" disabled>Otwórz do edycji</button></div>
    <div id="draft-editor" hidden>
      <p id="draft-details" class="hint"></p>
      <div id="draft-sections"></div>
      <label>Uzasadnienie wprowadzonych poprawek <textarea id="draft-rationale" rows="2" placeholder="Co i dlaczego zmieniasz?"></textarea></label>
      <div class="actions"><button id="draft-save" type="button" disabled>Zapisz poprawki w sprawie</button></div>
    </div>
    <p id="draft-result" role="status" aria-live="polite" class="hint">Nie otwarto projektu.</p>
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
  <section class="panel" aria-labelledby="finalization-title">
    <div class="panel-heading"><h2 id="finalization-title">Zatwierdzenie i pakiet końcowy</h2><span class="pill neutral" id="finalization-state">Nie wybrano renderu</span></div>
    <p class="hint">Przed zatwierdzeniem pobierz i przeczytaj dokładny zapisany DOCX oraz PDF. Akceptacja dokumentu, wydanie FINAL i złożenie pakietu są odrębnymi czynnościami HUMAN. Każda wymaga osobnego kliknięcia i uzasadnienia; system nie podejmuje tych decyzji automatycznie.</p>
    <div class="actions"><button id="finalization-refresh" type="button" class="secondary" disabled>Odczytaj status finalizacji</button></div>
    <pre id="finalization-status" class="status" role="status" aria-live="polite">Wybierz zapisany render, aby odczytać stan.</pre>
    <label>Uzasadnienie akceptacji dokładnego dokumentu <textarea id="approval-rationale" rows="2" maxlength="4000" placeholder="Potwierdź, co zostało sprawdzone w DOCX i PDF."></textarea></label>
    <div class="actions"><button id="approve-document" type="button" disabled>Jawnie zatwierdzam dokument</button></div>
    <label>Uzasadnienie wydania FINAL <textarea id="release-rationale" rows="2" maxlength="4000" placeholder="Uzasadnij wydanie dokładnej, zatwierdzonej wersji."></textarea></label>
    <div class="actions"><button id="release-document" type="button" disabled>Wydaj FINAL</button></div>
    <label>Uzasadnienie złożenia pakietu <textarea id="package-rationale" rows="2" maxlength="4000" placeholder="Uzasadnij utrwalenie kompletnego pakietu końcowego."></textarea></label>
    <div class="actions"><button id="assemble-package" type="button" disabled>Złóż pakiet końcowy</button></div>
    <label>Plik pakietu <select id="package-member" disabled><option value="">Pakiet nie jest jeszcze dostępny</option></select></label>
    <div class="actions"><button id="package-download" type="button" class="secondary" disabled>Pobierz wybrany plik pakietu</button></div>
    <pre id="package-status" class="status" role="status" aria-live="polite">Pakiet nie został jeszcze złożony.</pre>
  </section>
  <p id="status" class="status" role="status" aria-live="polite">Połącz się z istniejącą sprawą.</p>
</main><footer>Generator Pism 2.0: silnik wewnętrzny · HUMAN approvals: wyłącznie przez autoryzowane operacje WORK</footer>
</div><script src="/case.js"></script></body></html>'''.encode()

CASE_CSS = br'''*{box-sizing:border-box}body{margin:0;background:#f6f8fa;color:#17243b;font-family:system-ui,-apple-system,"Segoe UI",Arial,sans-serif}
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
.review-quote{padding:12px;border-left:3px solid #227c71;background:#f6f8fa;white-space:pre-wrap;overflow-wrap:anywhere}.intake-preview{background:#f6f8fa;border:1px solid #dce3ea;border-radius:8px;padding:12px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:340px;overflow:auto;font-size:13px}
textarea{width:100%;font:inherit;border:1px solid #cbd6e1;border-radius:8px;padding:12px;resize:vertical}
.status{padding:15px 19px;border-radius:8px;border:1px solid #d6dfe7;background:#fff;white-space:pre-wrap;overflow-wrap:anywhere}
.status.error{color:#a32035;border-color:#e9bcc4;background:#fff7f8}footer{font-size:12px;padding:18px 0 34px;border-top:1px solid #dce3ea}
@media(max-width:600px){header{align-items:flex-start;flex-direction:column;gap:3px}.shell{padding:0 15px}.panel{padding:18px}.metricrow{gap:28px}}'''

CASE_JS = r'''(() => {
"use strict";
const $=id=>document.getElementById(id);
const state={opened:false,pending:0,revision:0,caseSequence:0,review:null,draft:null,composeDraft:null,composeValidation:null,composeUnknown:false,finalization:null,finalizationUnknown:false};
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
const finalizationSelected=state.opened&&selected;
$("finalization-refresh").disabled=!finalizationSelected||busy;
$("approve-document").disabled=!finalizationSelected||busy||state.finalizationUnknown||!state.finalization?.can_approve;
$("release-document").disabled=!finalizationSelected||busy||state.finalizationUnknown||!state.finalization?.can_release;
$("assemble-package").disabled=!finalizationSelected||busy||state.finalizationUnknown||!state.finalization?.can_assemble;
const hasPackage=Boolean(state.finalization?.package);
$("package-member").disabled=!hasPackage||busy;
$("package-download").disabled=!hasPackage||busy||!$("package-member").value;
}
function close(){composeReset();state.revision++;state.opened=false;state.caseSequence=0;state.review=null;state.draft=null;state.finalization=null;state.finalizationUnknown=false;$("finalization-state").textContent="Nie wybrano renderu";$("finalization-status").textContent="Wybierz zapisany render, aby odczytać stan.";$("package-member").replaceChildren(new Option("Pakiet nie jest jeszcze dostępny",""));$("package-status").textContent="Pakiet nie został jeszcze złożony.";$("approval-rationale").value="";$("release-rationale").value="";$("package-rationale").value="";$("draft-editor").hidden=true;$("draft-select").replaceChildren(new Option("Otwórz sprawę, aby zobaczyć projekty",""));$("draft-sections").replaceChildren();$("draft-rationale").value="";$("draft-result").textContent="Nie otwarto projektu.";$("review-panel").hidden=true;$("review-select").replaceChildren();$("review-quote").textContent="";$("review-statement").value="";$("review-description").value="";$("review-rationale").value="";$("review-result").textContent="Brak decyzji.";$("case-state").textContent="Nieotwarta";$("case-title").textContent="Tytuł sprawy pojawi się po odczycie";$("case-seq").textContent="—";$("heads").textContent="—";$("render").replaceChildren(new Option("Otwórz sprawę, aby wyświetlić dokumenty",""));$("render-count").textContent="Lista dokumentów nie została jeszcze pobrana.";$("intake-preview").hidden=true;$("intake-preview").textContent="";$("intake-candidates").replaceChildren();$("intake-proposals").hidden=true;$("intake-result").textContent="Dodaj dokument lub wpisz opis.";refresh();}
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
    const expected=state.finalization?.artifacts?.find(item=>item.format===extra.format);
    const actual=response.headers.get("X-Content-SHA256");
    if(!expected||actual!==expected.content_hash||bytes.size!==expected.byte_length)
      throw new Error("Pobrany plik nie odpowiada dokładnemu, zapisanemu renderowi.");
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
    if(select.options.length>1){select.selectedIndex=1;await invoke("finalization_context",{render_id:select.value});}
    else{state.finalization=null;$("finalization-state").textContent="Brak zapisanego renderu";$("finalization-status").textContent="Najpierw utwórz zapisany render DOCX/PDF.";}
    status("Lista dokumentów pobrana z WORK. Wybierz plik do odczytu.");
  } else if(action==="finalization_context"){
    if(json.result_type!=="FINALIZATION_CONTEXT"||json.render_id!==$("render").value)throw new Error("Nieprawidłowy stan finalizacji.");
    state.finalization=json;state.finalizationUnknown=false;state.caseSequence=Number(json.case_sequence);
    $("case-seq").textContent=String(state.caseSequence);
    $("finalization-state").textContent=json.status;
    $("finalization-status").textContent=[
      "Render: "+json.render_id,
      "Stan: "+json.status,
      "Wersja sprawy: "+String(json.case_sequence),
      "Status projektu: "+json.draft_status,
      ...json.artifacts.map(item=>item.format+": "+item.byte_length+" B · SHA-256 "+item.content_hash),
      "Akceptacja HUMAN: "+(json.approval?"zapisana — sekwencja "+json.approval.committed_sequence:"brak"),
      "Wydanie FINAL: "+(json.release?json.release.eligibility+" — sekwencja "+json.release.committed_sequence:"brak"),
      "Pakiet: "+(json.package?"złożony — "+json.package.package_id:"brak"),
      "Następna bramka: "+json.next_gate,
      json.current?"Stan zgodny z bieżącą sekwencją CASE.":"Stan nie jest bieżący — wymagane ponowne sprawdzenie / walidacja."
    ].join("\n");
    const members=$("package-member");members.replaceChildren(new Option("Wybierz plik pakietu",""));
    if(json.package){for(const item of json.package.members){
      const label=item.name+" · "+String(item.byte_length)+" B · SHA-256 "+item.content_hash.slice(0,12);
      members.add(new Option(label,item.name));
    }}
    $("package-status").textContent=json.package?[
      "Pakiet: "+json.package.package_id,
      "Sekwencja: "+json.package.committed_sequence,
      "SHA-256 manifestu: "+json.package.manifest_hash,
      "Członkowie: "+String(json.package.members.length)+" / 10"
    ].join("\n"):"Pakiet nie został jeszcze złożony.";
  } else if(action==="approve_document"||action==="release_document"||action==="assemble_package"){
    const expected={approve_document:"DOCUMENT_APPROVED",release_document:"DOCUMENT_RELEASED",assemble_package:"PACKAGE_ASSEMBLED"}[action];
    if(json.result_type!==expected||!Number.isSafeInteger(json.case_sequence))throw new Error("WORK nie potwierdził oczekiwanego przejścia.");
    state.caseSequence=json.case_sequence;state.finalizationUnknown=false;
    for(const id of ["approval-rationale","release-rationale","package-rationale"])$(id).value="";
    status(action==="approve_document"?"WORK zapisał akceptację HUMAN dokładnego renderu.":action==="release_document"?"WORK potwierdził wydanie FINAL.":"WORK utrwalił pakiet końcowy.");
    await invoke("finalization_context",{render_id:json.render_id});
  } else status("Sprawdzono zapisany render. Status i decyzje pozostają w WORK.");
  return json;
}catch(error){if(generation===state.revision){
  if(["approve_document","release_document","assemble_package"].includes(action))state.finalizationUnknown=true;
  status(error.message,true);
}return null;}
finally{state.pending=Math.max(0,state.pending-1);refresh();}
}
$("open").addEventListener("click",()=>{close();invoke("open_case");});
$("render").addEventListener("change",()=>{
state.finalization=null;state.finalizationUnknown=false;
$("finalization-state").textContent="Odczyt wymagany";
$("finalization-status").textContent="Odczytaj status wybranego renderu.";
$("package-member").replaceChildren(new Option("Pakiet nie jest jeszcze dostępny",""));
$("package-status").textContent="Pakiet nie został jeszcze złożony.";
refresh();
if(uuid.test($("render").value))invoke("finalization_context",{render_id:$("render").value});
});
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

function finalizationCommand(action,rationaleId){
  const renderId=$("render").value.trim(),rationale=$(rationaleId).value.trim();
  if(!uuid.test(renderId))return status("Wybierz zapisany render.",true);
  if(!rationale)return status("Podaj uzasadnienie decyzji.",true);
  const permitted={approve_document:"can_approve",release_document:"can_release",assemble_package:"can_assemble"}[action];
  if(!state.finalization?.[permitted]||state.finalizationUnknown)return status("Najpierw odczytaj aktualny stan WORK; przejście nie jest obecnie dozwolone.",true);
  if(typeof crypto.randomUUID!=="function")return status("Brak bezpiecznego generatora identyfikatorów.",true);
  invoke(action,{render_id:renderId,rationale,command_id:crypto.randomUUID(),
    idempotency_key:crypto.randomUUID(),correlation_id:crypto.randomUUID()});
}
$("finalization-refresh").addEventListener("click",()=>{
  const renderId=$("render").value.trim();
  if(!uuid.test(renderId))return status("Wybierz zapisany render.",true);
  invoke("finalization_context",{render_id:renderId});
});
$("approve-document").addEventListener("click",()=>finalizationCommand("approve_document","approval-rationale"));
$("release-document").addEventListener("click",()=>finalizationCommand("release_document","release-rationale"));
$("assemble-package").addEventListener("click",()=>finalizationCommand("assemble_package","package-rationale"));
async function downloadPackageMember(){
  const renderId=$("render").value.trim(),member=$("package-member").value;
  if(!uuid.test(renderId)||!state.finalization?.package||!member)return status("Wybierz istniejącego członka pakietu.",true);
  const expected=state.finalization.package.members.find(item=>item.name===member);
  if(!expected)return status("Członek nie należy do manifestu pakietu.",true);
  const generation=state.revision;state.pending++;refresh();
  try{
    const response=await fetch("/api/embedded_session",{method:"POST",cache:"no-store",credentials:"omit",
      headers:{"Content-Type":"application/json","Authorization":"Bearer "+$("token").value},
      body:JSON.stringify({action:"read_package_member",render_id:renderId,member})});
    if(generation!==state.revision)return;
    if(!response.ok)throw new Error("WORK odmówił odczytu członka pakietu ("+response.status+").");
    const bytes=await response.arrayBuffer();
    const actual=response.headers.get("X-Content-SHA256");
    if(actual!==expected.content_hash||bytes.byteLength!==expected.byte_length)
      throw new Error("Odczytane bajty nie odpowiadają manifestowi pakietu.");
    const blob=new Blob([bytes],{type:response.headers.get("Content-Type")||expected.media_type});
    const url=URL.createObjectURL(blob),link=document.createElement("a");
    link.href=url;link.download=member;document.body.appendChild(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),1000);
    $("package-status").textContent="Pobrano: "+member+"\nRozmiar: "+bytes.byteLength+" B\nSHA-256: "+actual;
  }catch(error){status(error.message,true);}
  finally{state.pending=Math.max(0,state.pending-1);refresh();}
}
$("package-member").addEventListener("change",refresh);
$("package-download").addEventListener("click",downloadPackageMember);
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
  if(action==='render_document'){await invoke('list_saved');$('render').value=data.render_id;await invoke('finalization_context',{render_id:data.render_id});}
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
})();'''.encode()


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
        if not isinstance(result, RevisionResult) or getattr(result.entity, "kind", None) != "Case":
            raise EngineBoundaryError("CASE_REVISION_READ_REJECTED")
        case_entity = cast(Case, result.entity)
        if str(case_entity.id) != scope.case_id or case_entity.revision != revision:
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
        "composition_context": {"action"},
        "save_document_brief": {"action", "form", "run_id", "expected_case_sequence", "command_id", "idempotency_key", "correlation_id"},
        "generate_document": {"action", "form", "plan_id", "plan_revision", "profile", "expected_case_sequence", "command_id", "idempotency_key", "correlation_id"},
        "validate_document": {"action", "draft_id", "draft_revision", "expected_case_sequence", "command_id", "idempotency_key", "correlation_id"},
        "render_document": {"action", "draft_id", "draft_revision", "validation_run_id", "expected_case_sequence", "command_id", "idempotency_key", "correlation_id"},
        "finalization_context": {"action", "render_id"},
        "approve_document": {"action", "render_id", "rationale", "command_id", "idempotency_key", "correlation_id"},
        "release_document": {"action", "render_id", "rationale", "command_id", "idempotency_key", "correlation_id"},
        "assemble_package": {"action", "render_id", "rationale", "command_id", "idempotency_key", "correlation_id"},
        "read_package_member": {"action", "render_id", "member"},
        "open_case": {"action"},
        "case_title": {"action", "case_revision"},
        "list_saved": {"action"},
        "upload_source": {"action", "media_type", "content_base64", "expected_case_sequence", "command_id", "idempotency_key", "correlation_id", "run_id"},
        "list_drafts": {"action"},
        "open_draft": {"action", "draft_id", "revision"},
        "amend_draft": {"action", "draft_id", "revision", "draft_hash", "expected_case_sequence", "edits", "rationale", "command_id", "idempotency_key", "correlation_id"},
        "review_context": {"action", "source_id", "run_id"},
        "review_candidate": {"action", "source_id", "run_id", "candidate_index", "expected_case_sequence", "disposition", "statement", "description", "rationale", "command_id", "idempotency_key", "correlation_id"},
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
    if action in (
        "composition_context", "save_document_brief", "generate_document",
        "validate_document", "render_document", "finalization_context",
        "approve_document", "release_document", "assemble_package", "read_package_member",
    ):
        from lukart_work.legal_os_composer import composer_action
        return composer_action(operator, payload, token)
    if action in ("list_drafts", "open_draft", "amend_draft"):
        from lukart_work.legal_os_editor import edit_action
        return edit_action(operator, payload, token)
    if action in ("review_context", "review_candidate"):
        from lukart_work.legal_os_review import review_action
        return review_action(operator, payload, token)
    if action == "upload_source":
        from lukart_work.legal_os_intake import upload_case_source
        return upload_case_source(operator, payload, token)
    return read_case_action(
        operator,
        dict(payload, tenant_id=str(tenant), case_id=str(case)),
        token,
    )
