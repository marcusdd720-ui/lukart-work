# H1 — LUKART WORK: Generator WORK i CASE-first (mapa wdrożenia i luki)

Źródło zlecenia: https://github.com/marcusdd720-ui/lukart-ros/issues/370 (nadrzędne)
Kanoniczne zadanie H1: https://github.com/marcusdd720-ui/lukart-work/issues/81 (ta karta)
Profil wykonawczy: lukart-hermes-ops; H0 pozostaje osobnym koordynatorem (jego sesja przyjęcia była wcześniej zweryfikowana — zakres kod i syntetyki autoryzowany, brak drugiego mutującego koordynatora).

## Repozytorium i stan bazowy
- Repozytorium SSOT: `marcusdd720-ui/lukart-work` (kanbanowa karta `t_d5cab736` to przydział/odnośnik, nie drugie źródło statusu).
- Lokalny klon roboczy: workspace zadania, gałąź `main`, baza `09921b8e` ("Merge pull request #78 ... Pillow 13.0.0").
- Commit końcowy tej sesji: `29644bc` na gałęzi `h1/operator-host-graceful-send-close` (rodzic `09921b8e`; commit niezapisany — klucz podpisania wymaga passphrase niedostępnej w tej sesji; credentiali nie dotykane).
- Python 3.14 (izolowany venv zadania z zależnościami z `pyproject.toml`: `packaging==25.0`, `pydantic==2.13.5`, `python-docx==1.2.0`, `reportlab==4.4.9`, `fontpkg==0.2.2`, `fontpkg-lato==2.15`, `psycopg[binary]==3.3.3`, `pypdf==6.10.0`, `Pillow==13.0.0` — zainstalowane wyłącznie w tym venvie; brak `pip` w środowisku Hermes, zatem brak modificacji środowisk operatora).
- `git status` przed pracą: czyste drzewo (poza beklądotworzonymi przez git checkout plikami śledzonymi bez zmian).

## Zgodność z kanоном (przed pracą)
Przeczytane i zastosowane: `lukart-work/AGENTS.md` (Enterprise Execution Policy, v1.0, ACTIVE) oraz `lukart-ros/docs/WORKING_PRINCIPLES.md` (kanon naprawy: Problem → Evidence → Measurement → Design → Implementation → Focused Tests → Adversarial Tests → Full Regression → CI → Exact-SHA Validation → PR → Merge → Post-Merge Validation → Evidence → Closure; Unknown is not PASS; SKIP = missing evidence).
- Nie tworzone: nowego Generatora, nowej architektury, nowej granicy zaufania, zmian credentiali/security, wydania, déploiementu, mergu do `main`, real-case, rzeczywistego HUMAN, płatnego fallbacku.
- Zasada fail-closed i CASE-first (issue `lukart-work#67`): rzeczywiste sprawy → dokument → jawna akceptacja człowieka; syntetyczne testy nie są dopuszczeniem wzorca; trzy historyczne type-packi (PR #64) pozostają `NOT_ADMITTED`; legal/type admission `HUMAN_REQUIRED / RELEASE_HOLD`.

## Zweryfikowane componentes (IMPLEMENTED, evidence w tym raporcie i logach testów)
1. `GeneratorPismOperator` (`lukart_work/operator.py`) — wąska elewacja produkcyjna nad istniejącymi usługami WORK: CommandService, IngestionService (konfiguracja OCR), FactEvidenceService, ProceduralEngineService, DocumentPlannerService, ControlledDraftingService (`ManualAttestedDraftingProvider`), ValidationEngineService, FinalizationService; wiązanie type-pack z dokładnym pinem (`TYPE_PACK_IDENTITY_MISMATCH`, `AMBIGUOUS_DOCUMENT_PROFILE`); `export_local` odczytuje Exact persisted bytes DOCX/PDF przez scoped boundary finalizacji.
2. Ingestion/OCR ścieżka: `upload_source`/`query_ingestion` (`lukart_work/operator_ingestion.py`), `OCRConfig` z administratorskimi ścieżkami bezwzględnymi (tesseract/tessdata/pdftoppm) — nigdy z HTTP; limity (1 MiW body, 700 KiB form, 16 MiB worker, 20 stron OCR, 10s natywna wywołania, 40s budżet, 60s worker); bez pobierania modeli/narzędzi w runtime; bez OCR = `NEEDS_OCR`.
3. Drafting: `ControlledDraftingService` + `ManualAttestedDraftingProvider` — fail-closed, żadnych decyzji HUMAN przez automatykę, poprawki szkicu wymagają świeżego przeglądu/walidacji (`docs/DRAFT_AMENDMENT_HUMAN_ACCEPTANCE.md`).
4. DOCX/PDF render i lokalny eksport (`lukart_work/rendering`, `operator.export_local`): hash-weryfikowane bajty, `preview.html`, brak nadpisywania istniejących artefaktów.
5. FINAL/pakiet: granica PB02/PB03 (render → trwałość → zatwierdzenie HUMAN → release → pakiet 10 elementów: final.docx, final.pdf, document.json, validation.json, sources.json, evidence-map.json, argument-map.json, audit.json, release.json, manifest.json); transakcyjny zapis bytes/rewizji/audytu/outbox w jednej jednostce; rollback przy błędzie zapisu artefaktu; pakiet nie admitteduje żadnego realnego polskiego typu pisma.
6. Host operatora (`lukart_work/operator_host.py`): pętla zaplecza 127.0.0.1, granice Host/Origin/Sec-Fetch-Site/Authorization, limit treści 1 MiB, odrzucanie 413 z ograniczonym opróżnianiem, brak przechowywania tokenów, brak poświadczeń w UI.
7. Kontrakty i bramy: 23 encje, closed schemas, porty autoryzacji, `safe_error`, fail-closed na nieznane kontrakty/tokeny/profile.

## Naprawiony defekt (odtworzony i zweryfikowany)
**Defekt:** `lukart_work/operator_host` — na Windows pętla zaplecza wysyła odpowiedzi z `Connection: close` i twardo zamyka gniazdo tuż po flushu; klient `http.client` czytający odpowiedź w tym samym momencie dostaje `ConnectionAbortedError (WinError 10053)` — odpowiedź HTTP ginie. Odtworzone: skrypt stresowy 300 szybkich sekwencyjnych połączeń (mieszane 200/403/403-odrzucenia nagłówków) → 7× `ConnectionAbortedError` (~2,3%); testy jednostkowe `tests.test_operator_host` (odrzucenia bezpieczeństwa, brak/wadliwy token, granice przeglądarki) — błędy w 3 z 3, potem 1 z 3, potem 1 z 3 (wyścig).

**Poprawka (minimalna, jedna lokalizacja):** w `Handler.reply()` po `self.wfile.write(body)`: `self.wfile.flush()` oraz `self.connection.shutdown(socket.SHUT_WR)` z `except OSError: pass` przed `self.close_connection = True`. Klienci otrzymują czysty EOF (FIN) przed twardym zamknięciem; każdy kod statusu, nagłówki i zachowanie fail-closed niezmienione (`socket` już importowane w module).

**Weryfikacja po poprawce:**
- Stres 300 połączeń: 200×100, 403×200, 0× abort.
- `tests.test_operator_host.OperatorHostTests` (trzy sekcje odrzuceniowe): OK × 3 powtórzeń.
- Pełne repo: `python -B -X utf8 -m unittest discover -s tests -t .` → 727 testów, 61,3 s: **322 PASS, failures=1, errors=0, skipped=404**. Pełny log: `full-discover.log` (zachowany w raportach zadania; nie commitowany — to wyjście terminalowe, nie źródło repo).

## Luki / NOT VERIFIED (brak kodu do naprawy — brak dowodów lub brak infrastruktury)
1. Suite PB02/finalization, poprawki szkiców i bramy PostgreSQL `tests.test_product_baseline.PostgreSQLGateTests` — pomijane (`skipped`): brak lokalnego PostgreSQL (`pg_isready`/`psql` nieobecne) i brak izolowanych DSN (`LUKART_TEST_ADMIN_DSN`, `LUKART_TEST_RUNTIME_PASSWORD`, `LUKART_TEST_DSN`, `LUKART_TEST_EGRESS_*`). Per polityka repo: SKIP = brak dowodu, nie PASS. **Wymagane:** izolowana baza PG + DSN od właściciela.
2. `docs/GENERATOR_OCR_CREATECASE.md` odwołuje się do `tests.ocr_intake_acceptance` — moduł nie istnieje w drzewie. Testy OCR wymagają `LUKART_OCR_TEST_CONFIG` (trusted tesseract/tessdata/pdftoppm) oraz izolowanych DSN `lukart_ocr_acceptance_*`. **Luka dokumentacyjna i brak środowiska uruchomieniowego OCR.**
3. `test_fresh_process_reproduction_is_stable` (`tests.test_stage11`): DOCX/PDF z nowego procesu różnią się bajtowo od złotego wzorca Linux (`ed374419…docx` vs `2bb54e25…docx`; zlib-ng 2.2.4 w tym Pythonie Windows). Runbook `PR64-FU-RENDER-IDENTITY`: nie zastępować kanonicznych hashy wyjściem Windows, nie osłabiać asercji. **Platformowa luka, NOT VERIFIED do rozstrzygnięcia tutaj; renderer i wzorzec niezmienione.**
4. PR #79 (bieżący kandydat WORK): otwarty Draft, commit `52979a5d432bf183b2a80c5f9bd7e8818292965d`, gałąź `recovery/integrated-product-20261023`, +1070/−43, 20 plików, `stage_10_closed=false`. Nie scalony; jego zmiana `lukart_work/facts/service.py` (brama `OCR_REQUIRED` przy ekstrakcji) oraz nowy pakiet `lukart_work/generator_next` (kandydat syntetyczny, bez admittedu typu prawnego) nie są w `main`; CI dla tego SHA wymaga osobnego odbioru. Runnery GitHub dla kandydatów PR #64 blokowane błędem rozliczeń/spending limit (zaobserwowane w adnotacjach runnera) — nie dotyczyć rozliczeń, nie twierdzić o błędach testów z tej przyczyny.
5. Integracja ROS↔WORK (`docs/ROS_WORK_CAPABILITY_GAP_V1.md`): PLANNED / NOT IMPLEMENTED; luki RW-GAP-01..05 (checkpoint PB02/PB03, adapter operacji ROS→WORK, mapowania CIRP, admitted typów, odświeżenie bazy ROS przez supervisor). WORK pozostaje autorytetem Generatora Pism; ROS nie duplikuje pamięci, renderu, release ani pakietu.
6. Dokładne-SHA CI PASS dla kandydata H1 nieosiągalne teraz (brak admitted runnera/CI; rozliczenia GitHub) — **NOT VERIFIED**.

## Zmiany w drzewie (ten raport dotyczy)
- `lukart_work/operator_host.py` — graceful send-side close (poprawka defektu WinError 10053), commit `29644bc` na gałęzi `h1/operator-host-graceful-send-close` (rodzic `09921b8e`; commit niezapisany — klucz podpisania wymaga passphrase niedostępnej w tej sesji).
- Brak zmian w `main`; brak pushu/merge'a — wymagana wyraźna zgoda człowieka (HUMAN_MERGE_AUTHORIZATION_REQUIRED) przed scaleniem.

## Następna akcja
Właściciel/H0: autoryzacja scalenia poprawki `operator_host` (HUMAN_MERGE_AUTHORIZATION_REQUIRED — bez tego nie ma commitu do `main` ani merge'a), następnie: provision PG + DSN i konfiguracja OCR (odblokowanie suite'ów), rozstrzygnięcie follow-up render-tożsamości Windows, ciągły exact-SHA CI po odblokowaniu runnera, koordynacja z H2/H4/H5. Zapis wykonania (owner/profile/task/run ID, SHA, PR, testy, CI, wnioski, kolejna akcja) umieszczony na zadaniu GitHub `lukart-work#81`.

## Oświadczenie
Żaden z powyższych wyników nie constituye produkcyjnego dopuszczenia, certyfikacji ani realnego zatwierdzenia HUMAN. Syntetyczne testy nie są admissions typów dokumentów. Gdzie brak dowodu, wynik to `NOT VERIFIED`, nie PASS.

## Aktualizacja publikacji — 2026-11-01

Historyczne SHA `29644bc` i `8357c79` opisują lokalne, niepodpisane wykonanie z 31.10.2026; nie są kandydatem do merge. Naprawa klucza SSH po stronie operatora pozwoliła przygotować świeżą, podpisaną gałąź kandydata H1 na bazie `09921b8e` bez przepisywania historycznych commitów. Aktualne podpisane SHA, PR oraz wyniki exact-SHA CI należy pobrać z nowego PR i Issue WORK #81. Zachowano poprzednie dowody (300 połączeń, 0 abort po poprawce); nie traktować 404 SKIP jako PASS. PR #79 również modyfikuje `lukart_work/operator_host.py`: przed integracją konieczna jest ocena zgodności obu deltas, oddzielny review H4 i wymagana zgoda HUMAN na merge. Żadnego dopuszczenia rzeczywistych typów pism ani wdrożenia.
