"""SSPI-authenticated loopback reverse proxy for the existing WORK operator host."""
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from lukart_work.operator_host import create_server


def _rewrite_html(body: bytes) -> bytes:
    replacements = (
        (b"<label>Token uprawnienia", b"<label hidden>Token uprawnienia"),
        (b"<label>Token prywatnej sesji WORK", b"<label hidden>Token prywatnej sesji WORK"),
    )
    for old, new in replacements:
        body = body.replace(old, new, 1)
    script = (
        b'<script>window.LUKART_NATIVE_AUTH=true;'
        b'var t=document.getElementById("token");'
        b'if(t)t.value="NATIVE-SSPI-SESSION";</script>'
    )
    for marker in (b'<script src="/client.js">', b'<script src="/case.js">'):
        if marker in body:
            return body.replace(marker, script + marker, 1)
    raise ValueError("NATIVE_AUTH_HTML_SCRIPT_MARKER_MISSING")


def _rewrite_javascript(body: bytes) -> bytes:
    body = body.replace(b"credentials:'omit'", b"credentials:'same-origin'")
    body = body.replace(b'credentials:"omit"', b'credentials:"same-origin"')
    return body


def create_frontend_server(operator, human_auth, port: int = 8786) -> HTTPServer:
    if human_auth is None or not callable(getattr(human_auth, "authenticate", None)):
        raise ValueError("NATIVE_WINDOWS_HUMAN_AUTHENTICATOR_REQUIRED")
    backend = create_server(operator, 0)
    backend_thread = Thread(target=backend.serve_forever, name="lukart-work-backend", daemon=True)
    backend_thread.start()

    class Handler(BaseHTTPRequestHandler):
        server_version = "LUKART-WINDOWS-SSPI/1"

        def log_message(self, _format, *_args):
            return

        def setup(self):
            super().setup()
            self._native_cookie_headers = []
            self.connection.settimeout(15)

        def reply(self, status, body=b"", content_type="application/json; charset=utf-8", extra_headers=()):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Connection", "close")
            headers = (*self._native_cookie_headers, *extra_headers)
            self._native_cookie_headers = []
            for name, value in headers:
                if name not in {"Set-Cookie", "WWW-Authenticate", "Content-Disposition", "X-Content-SHA256"}:
                    raise ValueError("INVALID_FRONTEND_RESPONSE_HEADER")
                if any(ord(char) < 32 for char in value):
                    raise ValueError("INVALID_FRONTEND_RESPONSE_HEADER")
                self.send_header(name, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)
            self.close_connection = True

        def boundary(self):
            hosts = {f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"}
            values = self.headers.get_all("Host") or []
            if len(values) != 1 or values[0] not in hosts:
                return False
            origins = self.headers.get_all("Origin")
            if origins is not None and origins != ["http://" + values[0]]:
                return False
            fetch = self.headers.get_all("Sec-Fetch-Site")
            if fetch not in (None, ["same-origin"], ["none"]):
                return False
            if self.command == "POST":
                return origins == ["http://" + values[0]] and fetch == ["same-origin"]
            return True

        def cookie_value(self, name):
            values = self.headers.get_all("Cookie") or []
            if len(values) > 1:
                return None, True
            found = []
            for item in (values[0].split(";") if values else []):
                key, separator, value = item.strip().partition("=")
                if separator and key == name:
                    found.append(value)
            if len(found) > 1:
                return None, True
            if not found:
                return None, False
            value = found[0]
            allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            if not value or len(value) > 256 or any(char not in allowed for char in value):
                return None, True
            return value, False

        def native_authorize(self):
            session, bad_session = self.cookie_value("LUKART_SESSION")
            handshake, bad_handshake = self.cookie_value("LUKART_NEGOTIATE")
            auth_values = self.headers.get_all("Authorization") or []
            if bad_session or bad_handshake or len(auth_values) > 1:
                outcome = None
            else:
                authorization = auth_values[0] if auth_values and auth_values[0].startswith("Negotiate ") else None
                outcome = human_auth.authenticate(
                    session_token=session,
                    handshake_id=handshake,
                    authorization=authorization,
                )
            if outcome is not None and outcome.state == "AUTHENTICATED" and outcome.session_token:
                token = outcome.session_token
                self._native_cookie_headers = [
                    ("Set-Cookie", f"LUKART_SESSION={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={human_auth.session_ttl_seconds}"),
                    ("Set-Cookie", "LUKART_NEGOTIATE=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0"),
                ]
                return token
            if outcome is not None and outcome.state in ("CHALLENGE", "CONTINUE") and outcome.handshake_id and outcome.challenge:
                self.reply(
                    401,
                    b'{"error":"WINDOWS_AUTHENTICATION_REQUIRED"}',
                    extra_headers=(
                        ("WWW-Authenticate", outcome.challenge),
                        ("Set-Cookie", f"LUKART_NEGOTIATE={outcome.handshake_id}; Path=/; HttpOnly; SameSite=Strict; Max-Age=60"),
                    ),
                )
                return None
            self.reply(403, b'{"error":"FORBIDDEN"}')
            return None

        def proxy(self, token):
            body = b""
            if self.command == "POST":
                lengths = self.headers.get_all("Content-Length") or []
                if len(lengths) != 1 or not lengths[0].isdigit():
                    return self.reply(400, b'{"error":"INVALID_CONTENT_LENGTH"}')
                length = int(lengths[0])
                if length < 0 or length > 1_048_576:
                    return self.reply(413, b'{"error":"BODY_LIMIT"}')
                body = self.rfile.read(length)
                if len(body) != length:
                    return self.reply(400, b'{"error":"INCOMPLETE_BODY"}')
            headers = {"Authorization": "Bearer " + token}
            for name in ("Content-Type", "Accept", "Range", "If-None-Match"):
                value = self.headers.get(name)
                if value:
                    headers[name] = value
            connection = HTTPConnection("127.0.0.1", backend.server_port, timeout=15)
            try:
                connection.request(self.command, self.path, body=body if self.command == "POST" else None, headers=headers)
                response = connection.getresponse()
                payload = response.read()
                content_type = response.getheader("Content-Type", "application/octet-stream")
                extras = []
                for name in ("Content-Disposition", "X-Content-SHA256"):
                    value = response.getheader(name)
                    if value:
                        extras.append((name, value))
                if self.command == "GET" and "text/html" in content_type:
                    payload = _rewrite_html(payload)
                elif self.command == "GET" and ("javascript" in content_type or self.path.endswith(".js")):
                    payload = _rewrite_javascript(payload)
                self.reply(response.status, payload, content_type, tuple(extras))
            finally:
                connection.close()

        def do_GET(self):
            if not self.boundary():
                return self.reply(403, b'{"error":"FORBIDDEN"}')
            token = self.native_authorize()
            if token is not None:
                self.proxy(token)

        def do_POST(self):
            if not self.boundary():
                return self.reply(403, b'{"error":"FORBIDDEN"}')
            token = self.native_authorize()
            if token is not None:
                self.proxy(token)

        def do_HEAD(self):
            if not self.boundary():
                return self.reply(403, b'{"error":"FORBIDDEN"}')
            token = self.native_authorize()
            if token is not None:
                self.proxy(token)

    class FrontendServer(HTTPServer):
        def server_close(self):
            try:
                super().server_close()
            finally:
                backend.shutdown()
                backend.server_close()
                backend_thread.join(timeout=5)
                human_auth.close()

    server = FrontendServer(("127.0.0.1", port), Handler)
    server.backend_server = backend
    server.backend_thread = backend_thread
    server.human_auth = human_auth
    return server


def run_frontend(operator, *, port: int = 8786) -> None:
    from native_windows.windows_identity import create_authenticator

    authenticator = create_authenticator(operator)
    server = create_frontend_server(operator, authenticator, port)
    try:
        print(f"LEGAL OS native HUMAN: http://localhost:{server.server_port}/", flush=True)
        server.serve_forever()
    finally:
        server.server_close()
