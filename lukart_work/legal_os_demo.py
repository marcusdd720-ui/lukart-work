"""Explicit, loopback-only synthetic demonstration; never constructs a WORK operator.

Reuses the real case form/CSS and composer input validation. Preview is a form
summary, not Generator 2.0 output. Only an explicitly saved synthetic browser
draft may persist locally; no server persistence and production APIs deny.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from lukart_work.embedded_document_engine import EngineBoundaryError
from lukart_work.legal_os_case_view import CASE_CSS, CASE_HTML
from lukart_work.legal_os_composer import validate_form

EXAMPLE_DIR = Path(__file__).with_name("demo_examples")

# 20,000-character Unicode fields can exceed 32 KiB when JSON-escaped.
MAX_DEMO_FORM_BODY_BYTES = 256 * 1024
EXAMPLE_FILES = {
    "przyklad-demonstracyjny.pdf": ("application/pdf", "e7c296dd5876650a9b11aa972142337666e6912893630692edbd67d1f8f27c3f"),
    "przyklad-demonstracyjny.docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "ff5acf8466b16e2e6568a940eb772f4c35ab371dc012eae135f5163dea2ab2d1"),
    "przyklad-demonstracyjny.png": ("image/png", "201e200c79bff57a5e4afab01babb2c870b1d2b2da02a627d827fddcf646d112"),
}


def load_example():
    """Pin the complete historical pair and its exact PDF raster in memory."""
    result = {}
    for name, (mime, expected) in EXAMPLE_FILES.items():
        data = (EXAMPLE_DIR / name).read_bytes()
        if sha256(data).hexdigest() != expected:
            raise ValueError("DEMO_EXAMPLE_INTEGRITY_FAILED")
        result[name] = (mime, data)
    return result


def demo_html(example_available=True):
    page = CASE_HTML.decode("utf-8")
    for first, following in (("connect", "overview"), ("intake", "compose"), ("editor", "docs")):
        pattern = rf'  <section class="panel" aria-labelledby="{first}-title">.*?(?=  <section class="panel" aria-labelledby="{following}-title">)'
        page, count = re.subn(pattern, "", page, count=1, flags=re.DOTALL)
        if count != 1:
            raise RuntimeError("Case form layout changed; demo refuses an incomplete projection")
    start = page.index('  <section class="panel" aria-labelledby="docs-title">')
    end = page.index('  <p id="status"', start)
    page = page[:start] + '''  <section class="panel" aria-labelledby="docs-title">
    <div class="panel-heading"><h2 id="docs-title">Podgląd danych pisma</h2><span class="pill neutral">Podgląd lokalny</span></div>
    <p class="hint">To uporządkowany podgląd formularza. Generator Pism 2.0 nie jest wywoływany. Podgląd nie stanowi gotowego pisma ani porady prawnej.</p>
    <article id="demo-document" class="demo-document" aria-live="polite"><p>Uzupełnij dane i wybierz „Pokaż podgląd danych”.</p></article>
    <p class="hint">Eksport danych formularza do DOCX i PDF: ZABLOKOWANY. Stałe przykładowe pismo jest dostępne w oddzielnej sekcji poniżej i nie korzysta z danych szkicu.</p>
  </section>
''' + page[end:]
    example = '''  <section class="panel" aria-labelledby="example-title">
    <div class="panel-heading"><h2 id="example-title">Przykładowe pismo</h2><span class="pill neutral">Stały przykład</span></div>
    <p class="demo-example-label"><strong>PRZYKŁAD DEMONSTRACYJNY — NIEGENEROWANY NA ŻYWO</strong></p>
    <p class="hint">Wezwanie do zapłaty: Podmiot Testowy Alfa / Podmiot Testowy Beta. Wyłącznie syntetyczne dane z istniejących artefaktów A3/export-recovery-v5. Pliki pozostają niezmienne; edycja, zapis i usunięcie szkicu nie zmieniają tego przykładu.</p>
'''
    if example_available:
        example += '''    <div class="actions"><a class="demo-download" href="/demo/example/przyklad-demonstracyjny.pdf" download="przyklad-demonstracyjny.pdf">Pobierz PDF</a><a class="demo-download" href="/demo/example/przyklad-demonstracyjny.docx" download="przyklad-demonstracyjny.docx">Pobierz DOCX</a></div>
    <p class="hint"><a href="/demo/example/preview.pdf" target="_blank" rel="noopener">Otwórz PDF w osobnej karcie</a></p>
    <figure class="demo-pdf-preview"><figcaption>Podgląd PDF — strona 1 z 1. Obraz odczytany z dokładnie tego pliku PDF, który można pobrać.</figcaption><img src="/demo/example/przyklad-demonstracyjny.png" alt="Podgląd PDF: syntetyczne wezwanie do zapłaty pomiędzy podmiotami testowymi, strona 1" loading="lazy" width="910" height="1287"></figure>
'''
    else:
        example += '<p class="status error">PRZYKŁAD ZABLOKOWANY: brak kompletnej pary lub niezgodność SHA-256. Żaden przykładowy plik nie jest udostępniony.</p>'
    example += '  </section>\n'
    page = page.replace('  <p id="status"', example + '  <p id="status"', 1)
    page = page.replace('<title>LUKART LEGAL OS — Moja sprawa</title>', '<title>LUKART LEGAL OS — lokalne demo syntetyczne</title>')
    page = page.replace('Prywatna karta sprawy · silnik dokumentowy działa w tle', 'DEMO LOKALNE · wyłącznie dane syntetyczne')
    page = page.replace('<main>', '''<main><aside class="demo-banner" role="note"><strong>Tryb demonstracyjny — brak połączenia z WORK</strong><p>Wyłącznie dane syntetyczne. Szkic można zapisać w lokalnej pamięci tej przeglądarki i przywrócić po F5. To pamięć bez szyfrowania: nie wpisuj rzeczywistych danych spraw, tokenów ani haseł. Brak logowania, decyzji HUMAN i generowania dokumentów.</p><button id="demo-reset" type="button" class="secondary">Usuń lokalny szkic i przywróć przykład</button></aside>''')
    page = page.replace('Opisz sprawę, przygotuj projekt i pobierz dokumenty w jednym miejscu. Oryginały i historia pozostają w WORK, a wymagane decyzje należą do człowieka.', 'Poznaj formularz sprawy, dane stron i układ podglądu. Ten tryb nie zapisuje spraw i nie zastępuje autoryzowanego środowiska WORK.')
    page = page.replace('Wersja sprawy', 'Wersja w WORK — niedostępna').replace('Aktywne rekordy', 'Rekordy WORK — niedostępne')
    page = page.replace('Ten panel odczytuje stan bezpośrednio z istniejącego Case Core. Nie jest drugą bazą spraw.', 'Przykład syntetyczny nie ma rekordów, snapshotu ani zatwierdzonego planu w WORK.')
    page = page.replace('Generator 2.0 w tle', 'Generator 2.0 — zablokowany')
    page = page.replace('Zapisz komplet danych jako materiał sprawy. Generowanie korzysta z zatwierdzonego planu WORK i zweryfikowanych danych stron; zapis formularza nie tworzy tych zatwierdzeń.', 'Możesz edytować dane syntetyczne i sprawdzić kompletność formularza. Podgląd korzysta z tych danych, bez tworzenia projektu w Generatorze 2.0.')
    page = page.replace('Wymagana autoryzowana sesja WORK. Nie podawaj hasła Windows.', 'ZABLOKOWANE: zapis do WORK, zatwierdzenia HUMAN, plan, generowanie, walidacja dokumentu i eksport. Nie wpisuj tokenów ani haseł.')
    page = page.replace('Nie rozpoczęto przygotowania pisma.', 'Nie uruchomiono Generatora 2.0.')
    page = page.replace('Połącz się z istniejącą sprawą.', 'Demo lokalne gotowe. Przykład syntetyczny; brak sesji WORK.')
    page = page.replace('Generator Pism 2.0: silnik wewnętrzny · HUMAN approvals: wyłącznie przez autoryzowane operacje WORK', 'DEMO SYNTETYCZNE · Issue #80: FROZEN · DEPLOYMENT_GATE: BLOCKED')
    page = page.replace('<script src="/case.js">', '<script src="/demo.js">')
    page = page.replace('<div class="actions"><button id="compose-save"', '''<label class="demo-consent"><input id="demo-synthetic-only" type="checkbox">Potwierdzam: wpisano wyłącznie dane syntetyczne, bez rzeczywistych spraw, tokenów i haseł.</label>
    <div class="actions"><button id="demo-save-local" type="button" disabled>Zapisz szkic lokalnie</button></div>
    <p id="demo-draft-status" class="hint" role="status" aria-live="polite">Szkic nie został zapisany lokalnie.</p>
    <div class="actions"><button id="demo-preview" type="button">Pokaż podgląd danych</button><button id="compose-save"''')
    return page.encode("utf-8")


DEMO_CSS = CASE_CSS + b'\n.demo-banner{padding:22px;border:2px solid #c28a32;background:#fff8e8;border-radius:12px;line-height:1.6}.demo-document{padding:28px;border:1px solid #dce3ea;min-height:320px;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.7}.demo-document h3{font-size:22px}.demo-document address{font-style:normal}.demo-document .recipient{text-align:right}.demo-banner p{margin:8px 0}fieldset{border:1px solid #dce3ea;border-radius:8px}button:disabled{opacity:1;background:#e5e7eb;color:#626a75;border:1px solid #cbd0d8;box-shadow:none;cursor:not-allowed}.demo-consent{display:flex;flex-direction:row;align-items:flex-start;gap:10px}.demo-consent input{width:18px;height:18px;flex-shrink:0;margin:0}\n'
DEMO_CSS += b'.demo-download{display:inline-block;padding:12px 18px;border-radius:8px;background:#227c71;color:#fff;font-size:13px;font-weight:660;text-decoration:none}.demo-download:focus-visible{outline:3px solid #a7d5cb;outline-offset:2px}.demo-example-label{padding:12px;background:#fff8e8;border:1px solid #d5b578;border-radius:8px;font-size:13px;line-height:1.5}.demo-pdf-preview{margin:22px 0 0}.demo-pdf-preview figcaption{font-size:13px;color:#64748b;line-height:1.5;margin-bottom:12px}.demo-pdf-preview img{display:block;width:100%;height:auto;border:1px solid #dce3ea;background:#fff}'


def make_server(port=8786):
    # Fixed routes only: no filesystem serving, credentials, operator or outbound IO.
    try:
        examples = load_example()
    except (OSError, ValueError):
        examples = {}  # Keep the form available, but deny the entire example set.
    routes = {
        "/": ("text/html; charset=utf-8", demo_html(bool(examples))),
        "/case.css": ("text/css; charset=utf-8", DEMO_CSS),
        "/demo.js": ("text/javascript; charset=utf-8", Path(__file__).with_suffix(".js").read_bytes()),
    }

    class DemoHandler(BaseHTTPRequestHandler):
        timeout = 5

        def send(self, status, mime, body, disposition=None):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            if disposition is not None:
                self.send_header("Content-Disposition", disposition)
                self.send_header("X-Content-SHA256", sha256(body).hexdigest())
            self.end_headers()
            self.wfile.write(body)

        def reply(self, status, obj):
            self.send(status, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode("utf-8"))

        def allowed_host(self):
            return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

        def do_GET(self):
            if not self.allowed_host():
                return self.reply(403, {"error": "DEMO_LOOPBACK_HOST_REQUIRED"})
            if self.path == "/health":
                return self.reply(200, {"mode": "LOCAL_SYNTHETIC_DEMO", "pid": os.getpid(), "work_connected": False, "generator_invoked": False, "example_available": bool(examples)})
            if self.path.startswith("/demo/example/"):
                name = self.path.removeprefix("/demo/example/")
                inline = name == "preview.pdf"
                if inline:
                    name = "przyklad-demonstracyjny.pdf"
                if name not in examples:
                    return self.reply(404, {"error": "DEMO_EXAMPLE_UNAVAILABLE"})
                mime, data = examples[name]
                mode = "inline" if inline or name.endswith(".png") else "attachment"
                return self.send(200, mime, data, f'{mode}; filename="{name}"')
            if self.path in routes:
                mime, data = routes[self.path]
                return self.send(200, mime, data)
            self.reply(403 if self.path.startswith("/api/") else 404, {"error": "DEMO_OPERATION_BLOCKED"})

        def do_POST(self):
            if not self.allowed_host() or self.path != "/demo/validate":
                return self.reply(403, {"error": "DEMO_OPERATION_BLOCKED"})
            if self.headers.get("Origin") != f"http://127.0.0.1:{self.server.server_port}":
                return self.reply(403, {"error": "DEMO_ORIGIN_REQUIRED"})
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type") != "application/json":
                return self.reply(415, {"error": "DEMO_JSON_REQUIRED"})
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_DEMO_FORM_BODY_BYTES:
                    return self.reply(413, {"error": "DEMO_FORM_SIZE_LIMIT"})
                form = validate_form(json.loads(self.rfile.read(size)))
                if form["document_type"] not in ("synthetic-request", "synthetic-letter"):
                    return self.reply(400, {"error": "DEMO_SYNTHETIC_TYPE_REQUIRED"})
            except (ValueError, TypeError, UnicodeError, EngineBoundaryError):
                return self.reply(400, {"error": "DEMO_FORM_INCOMPLETE_OR_INVALID"})
            self.reply(200, {"form": form, "mode": "FORM_PREVIEW_ONLY", "saved": False, "generator_invoked": False})

        def log_message(self, *_args):
            pass  # No request bodies, paths, personal data or credentials in logs.

    return ThreadingHTTPServer(("127.0.0.1", port), DemoHandler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8786)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Local demo requires an unprivileged TCP port")
    try:
        server = make_server(args.port)
    except OSError:
        parser.exit(2, "BLOCKED: local port unavailable; no existing process was stopped.\n")
    print(f"LEGAL OS LOCAL DEMO http://127.0.0.1:{args.port}/ PID={os.getpid()} SYNTHETIC ONLY", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
