"""Loopback transport for a trusted, explicitly configured CASE operator."""
from __future__ import annotations

import argparse
import json
import runpy
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from time import monotonic

from lukart_work.embedded_document_engine import EngineBoundaryError, SavedArtifact
from lukart_work.legal_os_case_view import (
    CASE_CSS,
    CASE_HTML,
    CASE_JS,
    read_case_action,
    read_session_case_action,
)
from lukart_work.operator import GeneratorPismOperator
from lukart_work.validation.rules import Violation, strict_json

ROUTES = (
    "execute_core", "query_core", "execute_fact_evidence",
    "execute_procedural", "query_procedural", "execute_plan", "query_plan",
    "execute_draft", "execute_validation", "query_validation",
    "execute_finalization", "query_finalization",
    "upload_source", "query_ingestion", "query_fact_evidence", "query_draft",
)
MAX_BODY = 1024 * 1024
PAGE = '''<!doctype html><html lang="pl"><meta charset="utf-8">
<title>LUKART LEGAL OS — operator sprawy</title>
<link rel="stylesheet" href="/client.css">
<h1>LUKART LEGAL OS — Generator Pism</h1>
<p>Praca na rzeczywistej sprawie wymaga uprzedniej konfiguracji administratora oraz autoryzacji.
Ten interfejs nie tworzy zatwierdzeń ani nie wysyła dokumentów automatycznie.</p>
<fieldset><legend>1. Prywatna sesja i identyfikacja sprawy</legend>
<label>Token uprawnienia <input id="token" type="password" autocomplete="off"></label>
<button id="clear">Wyczyść sesję prywatną</button>
<p><label>Tenant ID <input id="tenant" autocomplete="off"></label>
<label>CASE ID <input id="case" autocomplete="off"></label>
<button id="open">Otwórz istniejącą sprawę</button></p></fieldset>
<fieldset><legend>2. Przygotowanie nowej sprawy (tylko uprawniony HUMAN)</legend>
<p>Wpisz wyłącznie rzeczywiste wartości nadane przez uprawnionego administratora.
Przygotowanie żądania NIE oznacza jego wykonania.</p>
<label>Tytuł sprawy <input id="caseTitle" autocomplete="off"></label>
<label>Identyfikator polityki retencji <input id="policyId" autocomplete="off"></label>
<label>Wersja polityki <input id="policyVersion" autocomplete="off"></label>
<label>SHA-256 polityki (64 znaki) <input id="policyHash" autocomplete="off"></label>
<button id="prepareCase">Przygotuj żądanie CreateCase do kontroli</button></fieldset>
<button id="confirmCase">Zatwierdzam utworzenie przygotowanej sprawy</button>
<fieldset><legend>Dokumenty i automatyczne OCR</legend>
<p>Otwórz sprawę, aby odczytać aktualny numer sekwencji. Wybierz PDF, PNG, JPEG, TIFF, DOCX lub TXT (do 700 KiB).
Zapis zachowuje oryginał. OCR i parser tworzą wyłącznie kandydatów do weryfikacji.</p>
<label>Sekwencja sprawy <input id="caseSequence" type="number" min="1"></label>
<label>Dokument <input id="sourceFile" type="file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.docx,.txt"></label>
<button id="uploadSource">Zapisz dokument i odczytaj tekst</button>
<label>ID źródła <input id="sourceId" autocomplete="off"></label>
<label>ID odczytu <input id="ingestionId" autocomplete="off"></label>
<button id="readIngestion">Pokaż zapisany tekst i kandydatów</button>
<button id="retryIngestion">Ponów odczyt źródła jako nowy przebieg</button>
<p id="ingestionStatus" role="status" aria-live="polite"></p></fieldset>
<fieldset><legend>Weryfikacja kandydatów przez uprawnionego HUMAN</legend>
<p>Porównaj tekst z oryginałem. Przyjęcie kandydata tworzy informację do dalszej weryfikacji;
potwierdzenie faktu i akceptacja dowodu pozostają odrębnymi decyzjami.</p>
<label>Kandydat <select id="candidateIndex"></select></label>
<pre id="candidateQuote"></pre>
<label>Dyspozycja <select id="candidateDisposition"><option value="REJECT">Odrzuć</option><option value="ADMIT">Przyjmij do dalszej weryfikacji</option></select></label>
<label>Wersja dotychczasowej oceny (0 dla pierwszej) <input id="reviewRevision" type="number" min="0" value="0"></label>
<label>Opis dowodu <textarea id="candidateDescription" rows="2"></textarea></label>
<label>Treść proponowanego faktu <textarea id="candidateStatement" rows="3"></textarea></label>
<label>Uzasadnienie oceny <textarea id="candidateRationale" rows="2"></textarea></label>
<button id="prepareReview">Przygotuj ocenę do jawnego zatwierdzenia</button>
<button id="viewFacts">Pokaż fakty, dowody i statusy weryfikacji</button></fieldset>
<fieldset><legend>3. Jawne polecenia, analiza i projekt pisma</legend>
<p>Dalsze operacje CASE wymagają pełnych, jawnych kontraktów usługi.
Każda decyzja HUMAN musi zostać podjęta przez rzeczywistego uprawnionego człowieka.</p>
<details id="advanced"><summary>Sprawdź i zatwierdź szczegóły polecenia JSON</summary>
<label>Usługa <select id="route"></select></label>
<p><label>Żądanie JSON<br><textarea id="request" rows="20" cols="90">{}</textarea></label></p>
<button id="send">Wyślij jawnie zatwierdzone żądanie</button></details></fieldset>
<fieldset><legend>Edytor projektu pisma</legend>
<p>Zapis poprawki tworzy nowy projekt. Poprzednia wersja i źródła pozostają w historii.
Nowy projekt wymaga ponownego przeglądu i walidacji. Zapis nie zatwierdza pisma ani nie wydaje FINAL.</p>
<label>ID projektu <input id="draftId" autocomplete="off"></label>
<label>Rewizja <input id="draftRevision" type="number" min="1" value="2"></label>
<button id="loadDraft">Otwórz projekt</button><button id="previousDraft" disabled>Otwórz poprzednią wersję</button>
<p id="draftStatus" role="status"></p><section id="draftTexts"></section>
<label>Uzasadnienie poprawki <textarea id="amendRationale" rows="2"></textarea></label>
<button id="prepareAmend">Przygotuj zapis poprawki</button>
<button id="confirmAmend">Zatwierdzam zapis nowego projektu</button>
<details><summary>Przegląd HUMAN nowej treści i ponowna walidacja</summary>
<p>Oceń osobno każdy obszar. System nie nadaje ocen za człowieka.</p>
<section id="draftAssessments"></section>
<label>Uzasadnienie przeglądu <textarea id="draftReviewRationale" rows="2"></textarea></label>
<button id="prepareDraftReview">Przygotuj przegląd do zatwierdzenia</button>
<button id="prepareDraftValidation">Przygotuj ponowną walidację</button>
<button id="prepareDraftRender">Przygotuj DOCX/PDF zwalidowanego projektu</button>
<p>Sprawdź przygotowane polecenie i użyj poniższego przycisku wysłania. Brakujące zatwierdzenia blokują operację.</p>
</details></fieldset>
<fieldset><legend>4. Odczyt planu i walidacji (bez zmian sprawy)</legend>
<p>Podaj identyfikatory istniejących rekordów CASE. Odczyt nie zatwierdza planu ani wyniku walidacji.</p>
<label>ID planu dokumentu <input id="planId" autocomplete="off"></label>
<label>Rewizja planu <input id="planRevision" type="number" min="1" value="1"></label>
<button id="viewPlan">Pokaż plan dokumentu</button>
<label>ID przebiegu walidacji <input id="validationId" autocomplete="off"></label>
<button id="viewValidation">Pokaż wynik walidacji</button></fieldset>
<fieldset><legend>5. Kontrolowane odczyty renderu i finalizacji</legend>
<p>Podgląd lub pobranie pliku samo w sobie NIE stanowi akceptacji prawnej ani wydania FINAL.</p>
<label>Render ID <input id="render" autocomplete="off"></label>
<button id="checkRender">Sprawdź status renderu</button>
<button id="checkRelease">Sprawdź status FINAL</button>
<button id="pdf">Podgląd PDF</button><button id="docx">Pobierz DOCX</button>
<a id="download" hidden>Pobierz dokument</a>
<p id="pdfStatus" role="status" aria-live="polite"></p>
<section id="previewPages" aria-label="Strony zapisanego PDF" hidden></section>
<iframe id="preview" title="Podgląd zapisanego PDF" sandbox hidden width="100%" height="700"></iframe></fieldset>
<pre id="result" aria-live="polite"></pre>
<script src="/client.js"></script></html>'''.encode()
CLIENT = ("const routes=" + json.dumps(ROUTES) + ";" + '''
const token=document.getElementById('token'),route=document.getElementById('route'),
request=document.getElementById('request'),send=document.getElementById('send'),
result=document.getElementById('result');
const nativeAuth=window.LUKART_NATIVE_AUTH===true;
function authHeaders(){const headers={'Content-Type':'application/json'};if(!nativeAuth)headers.Authorization='Bearer '+token.value;return headers;}
const tenant=document.getElementById('tenant'),caseId=document.getElementById('case'),
render=document.getElementById('render'),preview=document.getElementById('preview'),
download=document.getElementById('download');
const caseTitle=document.getElementById('caseTitle'),policyId=document.getElementById('policyId'),
policyVersion=document.getElementById('policyVersion'),policyHash=document.getElementById('policyHash'),
advanced=document.getElementById('advanced');
const planId=document.getElementById('planId'),planRevision=document.getElementById('planRevision'),
validationId=document.getElementById('validationId');
let artifactUrl=null;
let generation=0;
function clearArtifact(){preview.hidden=true;preview.removeAttribute('src');
download.hidden=true;download.removeAttribute('href');
if(artifactUrl){URL.revokeObjectURL(artifactUrl);artifactUrl=null;}}
function clearPrivate(){generation++;token.value='';request.value='{}';
tenant.value='';caseId.value='';render.value='';
caseTitle.value='';policyId.value='';policyVersion.value='';policyHash.value='';
planId.value='';planRevision.value='1';validationId.value='';
result.textContent='';send.disabled=false;clearArtifact();clearIntake();clearDraftEditor();}
document.getElementById('clear').onclick=clearPrivate;
window.addEventListener('pagehide',clearPrivate);
for(const r of routes){const o=document.createElement('option');o.value=o.textContent=r;route.append(o);}
async function submit(service,body){const current=++generation;send.disabled=true;clearArtifact();try{
const response=await fetch('/api/'+service,{method:'POST',cache:'no-store',credentials:nativeAuth?'same-origin':'omit',headers:authHeaders(),body:JSON.stringify(body)});
if(response.ok&&response.headers.get('Content-Type')==='application/octet-stream'){
const format=service==='query_finalization'&&body.operation==='ReadFinalArtifact'?body.format:null;
const type=format==='PDF'?'application/pdf':format==='DOCX'?
'application/vnd.openxmlformats-officedocument.wordprocessingml.document':'application/octet-stream';
const bytes=await response.arrayBuffer();if(current!==generation)return;
artifactUrl=URL.createObjectURL(new Blob([bytes],{type}));
download.href=artifactUrl;download.download=format?'document.'+format.toLowerCase():'artifact.bin';
download.textContent=format?'Pobierz '+format:'Pobierz dokument';
download.hidden=false;
result.textContent='Odczytano zapisany dokument. Sam odczyt nie oznacza zatwierdzenia pisma.';
}else{const text=await response.text();if(current!==generation)return;
try{result.textContent='HTTP '+response.status+'\\n'+
JSON.stringify(JSON.parse(text),null,2);handleIntakeResult(service,body,JSON.parse(text));}catch{result.textContent='HTTP '+response.status+'\\n'+text;}}
}catch(e){if(current===generation)result.textContent='Nie udało się połączyć z panelem.';}finally{if(current===generation)send.disabled=false;}}
send.onclick=()=>{try{const body=JSON.parse(request.value);submit(route.value,body);}
catch{result.textContent='Wpisz poprawne żądanie JSON przed wysłaniem.';}};
function query(service,body){route.value=service;request.value=JSON.stringify(body,null,2);submit(service,body);}
document.getElementById('open').onclick=()=>query('query_core',{
contract:'urn:lukart:work:CoreQuery:1.0.0',operation:'GetCaseHead',tenant_id:tenant.value,case_id:caseId.value});
for(const format of ['PDF','DOCX']){document.getElementById(format.toLowerCase()).onclick=()=>query(
'query_finalization',{contract:'urn:lukart:work:FinalizationQuery:1.0.0',operation:'ReadFinalArtifact',
tenant_id:tenant.value,case_id:caseId.value,render_id:render.value,format});}
// Only prepare a CoreRequest; NEVER dispatch a create command without an explicit
// separate operator click and the existing token/HUMAN authorization check.
document.getElementById('prepareCase').onclick=()=>{
const validUuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const title=caseTitle.value.trim(),id=policyId.value.trim(),version=policyVersion.value.trim(),
content_hash=policyHash.value.trim().toLowerCase();
if(!validUuid.test(tenant.value.trim())||!validUuid.test(caseId.value.trim())||
!title||!id||!version||!/^[0-9a-f]{64}$/.test(content_hash)||
!globalThis.crypto||typeof crypto.randomUUID!=='function'){
result.textContent='Brak poprawnych identyfikatorów, polityki retencji albo bezpiecznego generatora UUID.';
return;
}
const meta={command_id:crypto.randomUUID(),tenant_id:tenant.value.trim(),
case_id:caseId.value.trim(),idempotency_key:crypto.randomUUID(),
expected_case_sequence:0,correlation_id:crypto.randomUUID()};
const body={contract:'urn:lukart:work:CoreRequest:1.0.0',operation:'CreateCase',meta,
data:{title,jurisdiction:'PL',retention_policy:{id,version,content_hash}},
rationale:'Jawna decyzja uprawnionego operatora o utworzeniu sprawy'};
route.value='execute_core';request.value=JSON.stringify(body,null,2);
advanced.open=true;
result.textContent='Żądanie przygotowane. Zweryfikuj dane w JSON i osobno zatwierdź wysłanie.';
};
// All four actions below are existing repository read-only queries. No approval,
// drafting or CASE mutation may be constructed from a query button.
function idReady(...ids){
const validUuid=/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
if(ids.some(id=>!validUuid.test(id.trim()))){
 result.textContent='Podaj poprawne identyfikatory UUID. Nie wysłano zapytania.';
 return false;
}
return true;
}
function knownCase(){return idReady(tenant.value,caseId.value);}
document.getElementById('viewPlan').onclick=()=>{
if(!knownCase()||!idReady(planId.value))return;
const revision=Number(planRevision.value);
if(!Number.isSafeInteger(revision)||revision<1){
 result.textContent='Numer rewizji musi być dodatnią liczbą całkowitą.';
 return;
}
query('query_plan',{contract:'urn:lukart:work:PlannerQuery:1.0.0',operation:'GetDocumentPlan',
tenant_id:tenant.value.trim(),case_id:caseId.value.trim(),
plan:{kind:'DocumentPlan',id:planId.value.trim(),revision}});
};
document.getElementById('viewValidation').onclick=()=>{
if(!knownCase()||!idReady(validationId.value))return;
query('query_validation',{contract:'urn:lukart:work:ValidationQuery:1.0.0',operation:'GetValidation',
tenant_id:tenant.value.trim(),case_id:caseId.value.trim(),run_id:validationId.value.trim()});
};
for(const [button,operation] of [['checkRender','GetFinalization'],['checkRelease','GetFinalRelease']]){
document.getElementById(button).onclick=()=>{
if(!knownCase()||!idReady(render.value))return;
query('query_finalization',{contract:'urn:lukart:work:FinalizationQuery:1.0.0',
operation,tenant_id:tenant.value.trim(),case_id:caseId.value.trim(),render_id:render.value.trim()});
};
}

''').encode()
CLIENT += b'\n' + Path(__file__).with_name('operator_preview.js').read_bytes()
CLIENT += b'\n' + Path(__file__).with_name('operator_intake.js').read_bytes()
CLIENT += b'\n' + Path(__file__).with_name('operator_editor.js').read_bytes()
CSS = b'''body{max-width:1400px;margin:auto;padding:16px;font-family:system-ui,sans-serif}
fieldset{min-width:0;margin:12px 0;padding:16px}label{display:inline-flex;flex-direction:column;gap:4px;margin:4px}
input:not([type=number]){width:38ch;max-width:100%;box-sizing:border-box}textarea{width:100%;max-width:100%;box-sizing:border-box}
pre{white-space:pre-wrap;overflow-wrap:anywhere}button{margin:4px;min-height:32px}
#draftTexts label{display:flex;width:100%;box-sizing:border-box}#draftTexts textarea{min-height:7em}
#previewPages{max-height:85vh;overflow:auto;background:#e5e7eb;padding:12px;margin-top:12px}
#previewPages img{display:block;width:100%;max-width:1100px;height:auto;margin:0 auto 16px;background:white}
#pdfStatus{font-weight:bold}'''


def create_server(operator: GeneratorPismOperator, port: int = 8765, *, pdf_preview=None,
                  case_only=False, human_auth=None) -> HTTPServer:
    if not isinstance(operator, GeneratorPismOperator) or operator.binding is not None:
        raise ValueError("TRUSTED_CASE_OPERATOR_REQUIRED")
    if human_auth is None:
        human_auth = getattr(operator, "_human_authenticator", None)
    if human_auth is not None and (
        not callable(getattr(human_auth, "authenticate", None))
        or not callable(getattr(human_auth, "close", None))
        or type(getattr(human_auth, "session_ttl_seconds", None)) is not int
    ):
        raise ValueError("NATIVE_WINDOWS_HUMAN_AUTHENTICATOR_REQUIRED")
    if type(case_only) is not bool:
        raise ValueError("CASE_ONLY_FLAG_INVALID")
    if pdf_preview is not None and not callable(pdf_preview):
        raise ValueError("TRUSTED_PDF_PREVIEW_REQUIRED")

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self._native_cookie_headers = []
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass  # No tokens, request bodies, CASE identifiers or URLs in logs.

        def reply(self, status, body, content_type="application/json", extra_headers=()):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            headers = (*getattr(self, "_native_cookie_headers", ()), *extra_headers)
            self._native_cookie_headers = []
            for name, value in headers:
                if name not in {"Content-Disposition", "X-Content-SHA256", "Set-Cookie", "WWW-Authenticate"} or any(ord(char) < 32 for char in value):
                    raise ValueError("INVALID_RESPONSE_HEADER")
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; connect-src 'self'; frame-src blob:; img-src blob:; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.wfile.flush()
            # Deliver the response before half-closing the send side.
            try:
                self.connection.shutdown(socket.SHUT_WR)
            except OSError:
                pass
            self.close_connection = True

        def boundary(self):
            hosts={f"127.0.0.1:{self.server.server_port}",f"localhost:{self.server.server_port}"}
            host_values=self.headers.get_all("Host") or []
            if len(host_values)!=1 or host_values[0] not in hosts: return False
            origin_values=self.headers.get_all("Origin")
            if origin_values is not None and origin_values!=["http://"+host_values[0]]: return False
            fetch_values=self.headers.get_all("Sec-Fetch-Site")
            if fetch_values not in (None,["same-origin"],["none"]): return False
            if human_auth is not None and self.command=="POST":
                return origin_values==["http://"+host_values[0]] and fetch_values==["same-origin"]
            return True

        def cookie_value(self,name):
            values=self.headers.get_all("Cookie") or []
            if len(values)>1: return None,True
            found=[]
            for item in (values[0].split(";") if values else []):
                key,separator,value=item.strip().partition("=")
                if separator and key==name: found.append(value)
            if len(found)>1: return None,True
            if not found: return None,False
            value=found[0]
            if not value or len(value)>256 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in value):
                return None,True
            return value,False

        def native_authorize(self,post=False):
            session_token,bad_session=self.cookie_value("LUKART_SESSION")
            handshake_id,bad_handshake=self.cookie_value("LUKART_NEGOTIATE")
            auth_values=self.headers.get_all("Authorization") or []
            outcome=None if bad_session or bad_handshake or len(auth_values)>1 else human_auth.authenticate(
                session_token=session_token,handshake_id=handshake_id,
                authorization=auth_values[0] if auth_values else None)
            if outcome is not None and outcome.state=="AUTHENTICATED" and outcome.session_token:
                token=outcome.session_token
                self._native_cookie_headers=[
                    ("Set-Cookie",f"LUKART_SESSION={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={human_auth.session_ttl_seconds}"),
                    ("Set-Cookie","LUKART_NEGOTIATE=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0")]
                return token
            if outcome is not None and outcome.state in ("CHALLENGE","CONTINUE") and outcome.handshake_id and outcome.challenge:
                headers=(("WWW-Authenticate",outcome.challenge),
                    ("Set-Cookie",f"LUKART_NEGOTIATE={outcome.handshake_id}; Path=/; HttpOnly; SameSite=Strict; Max-Age=60"))
                body=b'{"error":"WINDOWS_AUTHENTICATION_REQUIRED"}'
                if post: self.reject_request(401,body,extra_headers=headers)
                else: self.reply(401,body,extra_headers=headers)
                return None
            if post: self.reject_request(403,b'{"error":"FORBIDDEN"}')
            else: self.reply(403,b'{"error":"FORBIDDEN"}')
            return None

        def native_page(self,content,script_name,token_label,old_hint=None,new_hint=None):
            marker=f'<script src="{script_name}">'.encode("utf-8")
            if marker not in content: raise ValueError("NATIVE_AUTH_PAGE_SCRIPT_MISSING")
            content=content.replace(marker,b'<script>window.LUKART_NATIVE_AUTH=true;</script>'+marker,1)
            if token_label not in content: raise ValueError("NATIVE_AUTH_TOKEN_FIELD_MISSING")
            content=content.replace(token_label,token_label.replace(b"<label>",b"<label hidden>",1),1)
            if old_hint and new_hint: content=content.replace(old_hint,new_hint,1)
            return content

        def reject_body(self,length,*,status=413,body=b'{"error":"BODY_LIMIT"}',extra_headers=()):
            if extra_headers: self.reply(status,body,extra_headers=extra_headers)
            else: self.reply(status,body)
            # Discard a bounded amount after sending the rejection; never parse or dispatch it.
            remaining = min(length, MAX_BODY + 1)
            deadline = monotonic() + 1
            try:
                while remaining > 0 and (timeout := deadline - monotonic()) > 0:
                    self.connection.settimeout(timeout)
                    chunk = self.rfile.read1(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except OSError:
                pass  # The rejected connection is already being closed.

        def reject_request(self,status,body,*,extra_headers=()):
            lengths=self.headers.get_all("Content-Length") or []
            # Untrusted or ambiguous framing cannot authorize an unbounded drain.
            length = MAX_BODY + 1
            if (len(lengths) == 1 and len(lengths[0]) <= 20
                    and lengths[0].isascii() and lengths[0].isdigit()
                    and self.headers.get("Transfer-Encoding") is None):
                length = min(int(lengths[0]), MAX_BODY + 1)
            if extra_headers: return self.reject_body(length,status=status,body=body,extra_headers=extra_headers)
            return self.reject_body(length,status=status,body=body)

        def do_GET(self):
            if not self.boundary(): return self.reply(403,b'{"error":"FORBIDDEN"}')
            if human_auth is not None and self.native_authorize() is None: return
            case_html,page=CASE_HTML,PAGE
            if human_auth is not None:
                case_html=self.native_page(CASE_HTML,"/case.js",b"<label>Token prywatnej sesji WORK",
                    "Wersja lokalna wymaga jeszcze tokenu; docelowo zastąpi go logowanie.".encode("utf-8"),
                    "Uwierzytelnienie wykorzystuje natywną sesję Windows (SSPI/Negotiate).".encode("utf-8"))
                page=self.native_page(PAGE,"/client.js",b"<label>Token uprawnienia")
            if self.path=="/case": return self.reply(200,case_html,"text/html; charset=utf-8")
            if self.path=="/case.js": return self.reply(200,CASE_JS,"text/javascript; charset=utf-8")
            if self.path=="/case.css": return self.reply(200,CASE_CSS,"text/css; charset=utf-8")
            if self.path=="/": return self.reply(200,case_html if case_only else page,"text/html; charset=utf-8")
            if self.path == "/client.js" and not case_only:
                return self.reply(200, CLIENT, "text/javascript; charset=utf-8")
            if self.path == "/client.css" and not case_only:
                return self.reply(200, CSS, "text/css; charset=utf-8")
            self.reply(404, b'{"error":"NOT_FOUND"}')

        def do_POST(self):
            body_consumed = False
            if not self.boundary():
                return self.reject_request(403, b'{"error":"FORBIDDEN"}')
            route = self.path.removeprefix("/api/")
            allowed_routes = ("embedded_session",) if case_only else (*ROUTES, "embedded_case", "embedded_session")
            if self.path != "/api/" + route or route not in allowed_routes:
                return self.reject_request(404, b'{"error":"NOT_FOUND"}')
            if human_auth is not None:
                token=self.native_authorize(post=True)
                if token is None: return
            else:
                auth=self.headers.get_all("Authorization") or []
                if len(auth)!=1 or not auth[0].startswith("Bearer "):
                    return self.reject_request(403,b'{"error":"FORBIDDEN"}')
                token=auth[0][7:]
            try:
                with operator.core.authority.session(token):
                    lengths = self.headers.get_all("Content-Length") or []
                    if (len(lengths) != 1 or len(lengths[0]) > 20
                            or not lengths[0].isascii() or not lengths[0].isdigit()
                            or self.headers.get("Transfer-Encoding") is not None
                            or self.headers.get_all("Content-Type") != ["application/json"]):
                        return self.reject_request(400, b'{"error":"INVALID_REQUEST"}')
                    length = int(lengths[0])
                    if not 0 < length <= MAX_BODY:
                        return self.reject_body(length)
                    raw = self.rfile.read(length)
                    body_consumed = True
                    if len(raw) != length:
                        return self.reject_body(
                            length - len(raw), status=400, body=b'{"error":"INVALID_REQUEST"}'
                        )
                    body_consumed = True
                    try:
                        payload = strict_json(raw.decode("utf-8"))
                    except (Violation, ValueError, UnicodeError, RecursionError):
                        return self.reply(400, b'{"error":"INVALID_REQUEST"}')
                    if not isinstance(payload, dict):
                        return self.reply(400, b'{"error":"INVALID_REQUEST"}')
                    result = (read_session_case_action(operator, payload, token)
                              if route == "embedded_session" else
                              read_case_action(operator, payload, token)
                              if route == "embedded_case" else getattr(operator, route)(payload, token))
                    if isinstance(result, SavedArtifact):
                        if (
                            not isinstance(result.filename, str)
                            or not result.filename
                            or any(char in result.filename for char in '\r\n"\\')
                            or not isinstance(result.sha256, str)
                            or len(result.sha256) != 64
                            or any(char not in "0123456789abcdef" for char in result.sha256)
                        ):
                            raise ValueError("INVALID_SAVED_ARTIFACT_METADATA")
                        return self.reply(200, result.data, result.mime_type, extra_headers=(
                            ("Content-Disposition", f'attachment; filename="{result.filename}"'),
                            ("X-Content-SHA256", result.sha256),
                        ))
                    if isinstance(result, bytes):
                        if (route == 'query_finalization' and payload.get('operation') == 'ReadFinalArtifact'
                                and payload.get('format') == 'PDF'
                                and self.headers.get_all('Accept') == ['application/vnd.lukart.local-pdf-preview+json']):
                            if pdf_preview is None:
                                return self.reply(503, b'{"error":"PDF_PREVIEW_NOT_CONFIGURED"}')
                            if not result.startswith(b'%PDF-'):
                                return self.reply(422, b'{"error":"PDF_PREVIEW_INVALID_DOCUMENT"}')
                            preview = pdf_preview(result)
                            return self.reply(200, json.dumps(preview, allow_nan=False).encode())
                        return self.reply(200, result, "application/octet-stream")
                    if route == "embedded_session" and isinstance(result, dict):
                        return self.reply(200, json.dumps(result, ensure_ascii=False,
                                                          allow_nan=False).encode("utf-8"))
                    self.reply(200, result.model_dump_json().encode())
            except EngineBoundaryError:
                self.reply(403, b'{"error":"CASE_OPERATION_REJECTED"}')
            except Violation:
                if not body_consumed:
                    return self.reject_request(403, b'{"error":"FORBIDDEN"}')
                self.reply(403, b'{"error":"FORBIDDEN"}')
            except (ValueError, UnicodeError):
                self.reply(400, b'{"error":"INVALID_REQUEST"}')
            except Exception:  # noqa: BLE001 - HTTP boundary must not leak internal details.
                self.reply(500, b'{"error":"SERVICE_FAILED"}')

    class OperatorHTTPServer(HTTPServer):
        def server_close(self):
            try: super().server_close()
            finally:
                if human_auth is not None: human_auth.close()
    server=OperatorHTTPServer(("127.0.0.1",port),Handler)
    server.human_auth=human_auth
    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True,
                        help="Trusted local Python file defining build_operator(); never an uploaded CASE file")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--legal-os", action="store_true",
                        help="Open the one-window LEGAL OS case workspace and hide legacy operator API")
    args = parser.parse_args()
    try:
        config = runpy.run_path(str(args.config.resolve()))
        factory = config["build_operator"]
        server = create_server(factory(), args.port, pdf_preview=config.get('render_pdf_preview'),
                               case_only=(args.legal_os or config.get('legal_os_case_only', False)))
    except Exception:  # noqa: BLE001 - configuration errors must not expose credentials.
        parser.exit(1, "HOST_CONFIGURATION_FAILED: trusted CASE services and capabilities required\n")
    host_name="localhost" if getattr(server,"human_auth",None) is not None else "127.0.0.1"
    print(f"CASE operator: http://{host_name}:{server.server_port}/",flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
