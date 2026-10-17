"""Loopback transport for a trusted, explicitly configured CASE operator."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import runpy
import socket
from time import monotonic

from lukart_work.operator import GeneratorPismOperator
from lukart_work.validation.rules import Violation, strict_json

ROUTES = (
    "execute_core", "query_core", "execute_fact_evidence",
    "execute_procedural", "query_procedural", "execute_plan", "query_plan",
    "execute_draft", "execute_validation", "query_validation",
    "execute_finalization", "query_finalization",
)
MAX_BODY = 1024 * 1024
PAGE = '''<!doctype html><html lang="pl"><meta charset="utf-8">
<title>LUKART LEGAL OS — operator sprawy</title>
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
<fieldset><legend>3. Jawne polecenia, analiza i projekt pisma</legend>
<p>Dalsze operacje CASE wymagają pełnych, jawnych kontraktów usługi.
Każda decyzja HUMAN musi zostać podjęta przez rzeczywistego uprawnionego człowieka.</p>
<details id="advanced"><summary>Sprawdź i zatwierdź szczegóły polecenia JSON</summary>
<label>Usługa <select id="route"></select></label>
<p><label>Żądanie JSON<br><textarea id="request" rows="20" cols="90">{}</textarea></label></p>
<button id="send">Wyślij jawnie zatwierdzone żądanie</button></details></fieldset>
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
<iframe id="preview" title="Podgląd zapisanego PDF" sandbox hidden width="100%" height="700"></iframe></fieldset>
<pre id="result" aria-live="polite"></pre>
<script src="/client.js"></script></html>'''.encode('utf-8')
CLIENT = ("const routes=" + json.dumps(ROUTES) + ";" + '''
const token=document.getElementById('token'),route=document.getElementById('route'),
request=document.getElementById('request'),send=document.getElementById('send'),
result=document.getElementById('result');
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
result.textContent='';send.disabled=false;clearArtifact();}
document.getElementById('clear').onclick=clearPrivate;
window.addEventListener('pagehide',clearPrivate);
for(const r of routes){const o=document.createElement('option');o.value=o.textContent=r;route.append(o);}
async function submit(service,body){const current=++generation;send.disabled=true;clearArtifact();try{
const response=await fetch('/api/'+service,{method:'POST',cache:'no-store',credentials:'omit',headers:{
'Content-Type':'application/json','Authorization':'Bearer '+token.value},body:JSON.stringify(body)});
if(response.ok&&response.headers.get('Content-Type')==='application/octet-stream'){
const format=service==='query_finalization'&&body.operation==='ReadFinalArtifact'?body.format:null;
const type=format==='PDF'?'application/pdf':format==='DOCX'?
'application/vnd.openxmlformats-officedocument.wordprocessingml.document':'application/octet-stream';
const bytes=await response.arrayBuffer();if(current!==generation)return;
artifactUrl=URL.createObjectURL(new Blob([bytes],{type}));
download.href=artifactUrl;download.download=format?'document.'+format.toLowerCase():'artifact.bin';
download.hidden=false;if(format==='PDF'){preview.src=artifactUrl;preview.hidden=false;}
result.textContent='Persisted artifact read. Preview does not grant approval.';
}else{const text=await response.text();if(current!==generation)return;
try{result.textContent='HTTP '+response.status+'\\n'+
JSON.stringify(JSON.parse(text),null,2);}catch{result.textContent='HTTP '+response.status+'\\n'+text;}}
}catch(e){if(current===generation)result.textContent='Request failed';}finally{if(current===generation)send.disabled=false;}}
send.onclick=()=>{try{const body=JSON.parse(request.value);submit(route.value,body);}
catch{result.textContent='Enter valid JSON before submitting.';}};
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


def create_server(operator: GeneratorPismOperator, port: int = 8765) -> HTTPServer:
    if not isinstance(operator, GeneratorPismOperator) or operator.binding is not None:
        raise ValueError("TRUSTED_CASE_OPERATOR_REQUIRED")

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(10)

        def log_message(self, *args):
            pass  # No tokens, request bodies, CASE identifiers or URLs in logs.

        def reply(self, status, body, content_type="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; connect-src 'self'; frame-src blob:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def boundary(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            return (self.headers.get_all("Host") == [expected]
                    and self.headers.get_all("Origin") in (None, ["http://" + expected])
                    and self.headers.get_all("Sec-Fetch-Site") in
                    (None, ["same-origin"], ["none"]))

        def reject_body(self, length):
            self.reply(413, b'{"error":"BODY_LIMIT"}')
            # Closing over unread upload bytes can reset Windows connections
            # before the client receives 413. Discard only a bounded amount,
            # after sending the rejection; never parse or dispatch this body.
            remaining = min(length, MAX_BODY + 1)
            deadline = monotonic() + 1
            try:
                self.connection.shutdown(socket.SHUT_WR)
                while remaining > 0 and (timeout := deadline - monotonic()) > 0:
                    self.connection.settimeout(timeout)
                    chunk = self.rfile.read1(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
            except OSError:
                pass  # The rejected connection is already being closed.

        def do_GET(self):
            if not self.boundary():
                return self.reply(403, b'{"error":"FORBIDDEN"}')
            if self.path == "/":
                return self.reply(200, PAGE, "text/html; charset=utf-8")
            if self.path == "/client.js":
                return self.reply(200, CLIENT, "text/javascript; charset=utf-8")
            self.reply(404, b'{"error":"NOT_FOUND"}')

        def do_POST(self):
            if not self.boundary():
                return self.reply(403, b'{"error":"FORBIDDEN"}')
            route = self.path.removeprefix("/api/")
            if self.path != "/api/" + route or route not in ROUTES:
                return self.reply(404, b'{"error":"NOT_FOUND"}')
            auth = self.headers.get_all("Authorization") or []
            if len(auth) != 1 or not auth[0].startswith("Bearer "):
                return self.reply(403, b'{"error":"FORBIDDEN"}')
            token = auth[0][7:]
            try:
                with operator.core.authority.session(token):
                    lengths = self.headers.get_all("Content-Length") or []
                    if (len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit()
                            or self.headers.get("Transfer-Encoding") is not None
                            or self.headers.get_all("Content-Type") != ["application/json"]):
                        return self.reply(400, b'{"error":"INVALID_REQUEST"}')
                    length = int(lengths[0])
                    if not 0 < length <= MAX_BODY:
                        return self.reject_body(length)
                    raw = self.rfile.read(length)
                    if len(raw) != length:
                        return self.reply(400, b'{"error":"INVALID_REQUEST"}')
                    try:
                        payload = strict_json(raw.decode("utf-8"))
                    except (Violation, ValueError, UnicodeError, RecursionError):
                        return self.reply(400, b'{"error":"INVALID_REQUEST"}')
                    if not isinstance(payload, dict):
                        return self.reply(400, b'{"error":"INVALID_REQUEST"}')
                    result = getattr(operator, route)(payload, token)
                    if isinstance(result, bytes):
                        return self.reply(200, result, "application/octet-stream")
                    self.reply(200, result.model_dump_json().encode())
            except Violation:
                self.reply(403, b'{"error":"FORBIDDEN"}')
            except (ValueError, UnicodeError):
                self.reply(400, b'{"error":"INVALID_REQUEST"}')
            except Exception:
                self.reply(500, b'{"error":"SERVICE_FAILED"}')

    return HTTPServer(("127.0.0.1", port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True,
                        help="Trusted local Python file defining build_operator(); never an uploaded CASE file")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        factory = runpy.run_path(str(args.config.resolve()))["build_operator"]
        server = create_server(factory(), args.port)
    except Exception:
        parser.exit(1, "HOST_CONFIGURATION_FAILED: trusted CASE services and capabilities required\n")
    print(f"CASE operator: http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
