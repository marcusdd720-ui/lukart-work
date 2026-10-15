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
PAGE = b'''<!doctype html><html lang="en"><meta charset="utf-8">
<title>LUKART CASE operator</title><h1>CASE operator</h1>
<p>Submit an existing service command or query. HUMAN decisions require your explicit input.</p>
<label>Capability token <input id="token" type="password" autocomplete="off"></label>
<button id="clear">Clear private session</button>
<p><label>Tenant ID <input id="tenant" autocomplete="off"></label>
<label>CASE ID <input id="case" autocomplete="off"></label>
<button id="open">Open CASE</button></p>
<p><label>Render ID <input id="render" autocomplete="off"></label>
<button id="pdf">Preview PDF</button><button id="docx">Download DOCX</button></p>
<label>Service <select id="route"></select></label>
<p><label>Request JSON<br><textarea id="request" rows="20" cols="90">{}</textarea></label></p>
<button id="send">Submit explicit request</button><pre id="result" aria-live="polite"></pre>
<a id="download" hidden>Download artifact</a>
<iframe id="preview" title="Persisted PDF preview" sandbox hidden width="100%" height="700"></iframe>
<script src="/client.js"></script></html>'''
CLIENT = ("const routes=" + json.dumps(ROUTES) + ";" + '''
const token=document.getElementById('token'),route=document.getElementById('route'),
request=document.getElementById('request'),send=document.getElementById('send'),
result=document.getElementById('result');
const tenant=document.getElementById('tenant'),caseId=document.getElementById('case'),
render=document.getElementById('render'),preview=document.getElementById('preview'),
download=document.getElementById('download');
let artifactUrl=null;
let generation=0;
function clearArtifact(){preview.hidden=true;preview.removeAttribute('src');
download.hidden=true;download.removeAttribute('href');
if(artifactUrl){URL.revokeObjectURL(artifactUrl);artifactUrl=null;}}
function clearPrivate(){generation++;token.value='';request.value='{}';
tenant.value='';caseId.value='';render.value='';result.textContent='';clearArtifact();}
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
}catch(e){if(current===generation)result.textContent='Request failed';}finally{send.disabled=false;}}
send.onclick=()=>{try{const body=JSON.parse(request.value);submit(route.value,body);}
catch{result.textContent='Enter valid JSON before submitting.';}};
function query(service,body){route.value=service;request.value=JSON.stringify(body,null,2);submit(service,body);}
document.getElementById('open').onclick=()=>query('query_core',{
contract:'urn:lukart:work:CoreQuery:1.0.0',operation:'GetCaseHead',tenant_id:tenant.value,case_id:caseId.value});
for(const format of ['PDF','DOCX']){document.getElementById(format.toLowerCase()).onclick=()=>query(
'query_finalization',{contract:'urn:lukart:work:FinalizationQuery:1.0.0',operation:'ReadFinalArtifact',
tenant_id:tenant.value,case_id:caseId.value,render_id:render.value,format});}
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
