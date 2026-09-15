# Stage 02 — weryfikacja gotowości

Data: 2026-09-15. Zakres bieżącego zadania: weryfikacja gotowości, zgodnie z nazwą zadania użytkownika; nie realizacja ani zamknięcie Case Core. Załączona instrukcja wykonawcza stanowi podstawę macierzy przyszłego odbioru.

## Werdykt i punkt odniesienia

**CONDITIONAL GO do rozpoczęcia implementacji Stage 02. NO-GO dla zamknięcia Stage 02.**

Oceniony commit: `e278b97521731b8dc0395560db17e0e601a1d714`, branch `main`. HEAD jest dokładnie wskazanym commitem remediation Stage 01; brak późniejszych commitów. Przed kontrolą brak zmian tracked/staged; jedynie nieśledzony `lukart_work_domain_contracts.egg-info/`, pozostawiony nietknięty. Jedyna nowa zmiana po review to ten raport; nie przypisujemy mu zatwierdzenia recenzenta kodu. Nie utworzono commita implementacji: wykonano weryfikację gotowości, bez zmian kodu.

Nie znaleziono AGENTS.md w repozytorium ani w sprawdzonych katalogach nadrzędnych aż do C:\. Nie instalowano zależności, nie wykonywano push, deploymentu ani operacji ROS.

## Hierarchia i granice

1. Bieżąca instrukcja użytkownika i przekazany kontekst: post-remediation AGR-01-001–007 FIXED VERIFIED, Stage 02 may begin YES. Jest to informacja użytkownika; oryginalny raport tego review nie znajduje się w repozytorium.
2. `00-baseline.md`, zwłaszcza §4–6, 27–30, 47, 49–50: architektura nadrzędna; Stage 02 = Case Core, Stage 03 = Storage + Versioning.
3. `01-specification.md`: ADR-01–09, agregaty/transakcje, komendy, invarianty i granice adapterów; normatywne uzupełnienie w `07-stage01-remediation.md`.
4. `02-entity-catalog.md`, `03-relations.md`, `04-test-specification.md` oraz wykonawcze modele/kontrakty. README opisuje brakujące obowiązki Stage 02.
5. `05-compliance.md`, `06-status.md` i reports: dowody ograniczone do opisanego zakresu/czasu, nie nadrzędna architektura. Historyczne zalecenia nie uchylają nowszej instrukcji użytkownika.

Minimum Stage 02 obejmuje trwały zapis wymagany przez operacje Case Core: rewizje, heads, snapshots, CAS, idempotency oraz atomowy audit/outbox. Sam adapter in-memory nie spełnia odbioru. Nie oznacza to realizacji całego Stage 03, 12 lub 18. PostgreSQL jest wskazany w baseline; nie potrzeba ponownego wyboru bazy. Konfiguracja dostępnej instancji testowej i CI pozostaje UNVERIFIED: psql/docker nie zostały znalezione w PATH, co nie dowodzi braku infrastruktury. Repo ma origin GitHub; nie sprawdzano zdalnego CI.

## Macierz odbioru

Statusy opisują obecny commit, nie planowany wynik. VERIFIED dla zależności Stage 01 oznacza wyłącznie lokalnie sprawdzony zakres kontraktów.

| Wymaganie | Źródło | Element implementacji | Wymagany test/dowód | Stan |
|---|---|---|---|---|
| 23 encje, wersje kontraktów i schema/union export | baseline §5; spec Machine-readable contract strategy | domain/models.py, contracts/messages.py, versions.py, schemas | testy kontraktów + porównanie 56 schematów/URN | VERIFIED — zależność Stage 01 |
| KG oddzielony od DAG, immutable revisions i binding akceptacji | baseline §6, 16, 28; ADR-01/02/05; remediation AGR-001–007 | validation/rules.py, lifecycle.py, test_remediation.py | lokalne testy pozytywne i odrzucenia; nie dowód działania usług | VERIFIED — lokalna zależność Stage 01 |
| Uwierzytelniony CommandService, scope i aktor z kontekstu; brak publicznego AppendRevision | spec Komendy, Error model; README:33 | przyszła usługa i AuthorizationPort; obecnie tylko Protocol | podrobiony actor/scope, brak uprawnień, cross-case/tenant, bezpieczny błąd | NOT IMPLEMENTED |
| CreateCase, VerifyParty, ConfirmFact, ApprovePlan, RecordDecision i pełna koniunkcja guardów | spec Komendy oraz Invariants/lifecycle | przyszłe application handlers | scenariusz przechodzący wszystkie wymagane guardy + osobne odrzucenia i I20 | NOT IMPLEMENTED |
| Append-only revisions, heads, CAS i case_sequence | baseline §4/28; ADR-08; spec Aggregate roots | trwały CaseRepository/unit of work | I01 rollback, I02 dwa połączenia PostgreSQL, odczyt historii po restarcie | NOT IMPLEMENTED |
| Snapshot closure, dokładna akceptacja i chroniony odczyt | spec Snapshoty, Komendy; remediation AGR-001/006 | tworzenie/utrwalenie snapshotu i AcceptSnapshot handler | poprawna akceptacja; obcy scope, brak źródła/decision, podmieniony hash, zachowanie historii | NOT IMPLEMENTED — guardy istnieją |
| Chronione queries revision/head/snapshot/provenance/affected | spec Queries oraz KG/DAG | query service i scoped repository | autoryzacja odczytu, brak ujawnienia obcych ID, zgodna sekwencja i heads | NOT IMPLEMENTED |
| Trwała idempotencja po autoryzacji i przed CAS | spec Idempotency; README:33 | dispatcher + persistent result store | I04 replay po restarcie; inne body konflikt; brak powtórnego zdarzenia | NOT IMPLEMENTED |
| Atomowy audit/outbox i izolacja danych | baseline §27/30; ADR-08; spec DomainEvent/Error model | transakcja encja/head/sequence/audit/outbox, scoped access | I01/I02 i I03 dla dostępnych powierzchni Case Core; rollback przy awarii | NOT IMPLEMENTED |
| Granice release fail-closed, safe errors, oryginalne payloady/wersje/hashe | spec ReleaseService 02/10, Error model, Machine-readable strategy; remediation Compatibility | adapter błędów/wersji, odmowa przy niedostępnych dowodach | nieznana wersja, brak authoritative evidence, brak cichej migracji, brak PII w błędach | NOT IMPLEMENTED — pure guards nie zastępują adaptera |
| Pełny DoD modułu | baseline §47; test-spec I01–I04/I20 w zakresie core | implementacja, testy DB, core golden, docs, review na końcowym SHA, merge/post-merge; CI wg kryterium zamknięcia | bieżące logi i exact SHA, niezależny pozytywny review | UNVERIFIED / brak implementacji Stage 02 |

Później: pełny Storage + Versioning (03), ingestion (04), Facts/Evidence (05), planner/drafting (08/09), rzeczywiste validatory i pełny ReleaseService (10), rendering (11), pełny audit/provenance (12), hardening (18), ROS (19), certification (20). Bezpieczna odmowa niedostępnych operacji nie jest dowodem implementacji tych etapów. AGR-01-008–010 pozostają odłożone zgodnie z instrukcją; repo nie zawiera treści tych findingów, więc nie przypisano im wymyślonego zakresu ani zakończenia.

## Bieżąca weryfikacja

- `.venv\Scripts\python.exe -B -X utf8 -m unittest discover -v`: **72 testy PASS**, 0 failures/errors, 0.411 s. Obejmuje 15 testów remediation. Pierwsza próba została zablokowana odmową dostępu; ponowienie po eskalacji narzędzia zakończyło się sukcesem.
- Osobna odczytowa kontrola `model_json_schema()` / `TypeAdapter` względem zapisanych schematów i `contract_version`: **56 schema/union/URN PASS**, 23 encje. Pierwsze polecenie pomocnicze miało błąd składni, poprawione ponowienie PASS; błąd dotyczył polecenia kontroli, nie repozytorium.
- `git diff --check`, `git diff --cached --check`, przegląd diff/stat/staged: przed raportem PASS, brak zmian. Relacja ancestor do wskazanego SHA potwierdzona; HEAD identyczny.
- Manifest: **92/92 zgodne po normalizacji tekstu UTF-8 CRLF→LF**; 84/92 różne dla surowych bytes working tree. Końcówki linii Git: baseline index LF, working tree CRLF. Nie uznano tego za zmianę treści.
- Baseline SHA-256 raw working tree: `834c576cb3324dc6b0d2d701f2df68f95c8183af4a0a0d18fbb0ea473e274ecc` (zgodny z reports/status.json); po LF: `3c980207dd77cb2b0139a710d4446c76408c90ceff0f1d124eba853afdaebe83` (manifest). Nie zmieniano manifestu.
- Hash domenowy jest inną reprezentacją: `LW-CJSON-1`, JSON UTF-8, sortowane klucze, bez odstępów, ensure_ascii=false, allow_nan=false, zachowana kolejność list; model jest dumpowany w trybie JSON. Hash źródła/renderu dotyczy oryginalnych bytes, których nie wolno normalizować jak plików tekstowych repozytorium.
- `python verify_package.py`: **NOT EXECUTED w odczytowym review**, ponieważ nadpisuje reports/package-validation.json. Odczytowe porównanie schematów nie jest deklarowane jako wykonanie całego skryptu. W fazie implementacji nadal obowiązuje uruchomienie pełnego weryfikatora.
- Testy realnych transakcji, CI, Stage 02 E2E/golden i post-merge: **NOT EXECUTED**. Syntetyczne testy kontraktów nie dowodzą certyfikacji, prawnej poprawności dokumentu ani bezpieczeństwa produkcji.

## Niezależny review

Osobny subagent `readiness_review` wykonał read-only przegląd dokładnego SHA wskazanego powyżej. Podczas review nie edytowano kodu ani dokumentów. To review gotowości; nie pozytywny odbiór implementacji Stage 02.

Ustalenia: P1 brak implementacji Case Core (`contracts/ports.py:1–13`, `validation/rules.py:252–271`, README:31–33); P1 brak pełnego DoD (baseline:1422–1445); P2 potrzeba jawnej granicy persystencji 02/03 (baseline:1512–1521, spec:178); P2 brak repozytoryjnego śladu GO przekazanego przez użytkownika (status:32–33). Dwa P1 blokują zamknięcie, nie rozpoczęcie prac. Nie stwierdzono nierozstrzygalnego konfliktu architektonicznego blokującego implementację core.

Werdykt recenzenta: **CONDITIONAL GO start / NO-GO zamknięcie**. Recenzent nie uruchomił testów z powodu odmowy dostępu; bieżące PASS powyżej pochodzą z wykonania głównego agenta po eskalacji, a nie z historycznych raportów ani osobnego wykonania recenzenta. Iteracje naprawcze: **0**. Nie tworzono końcowego commita implementacji ani nie deklarowano jego zatwierdzenia.

## Co zostało do zrobienia

- [x] Potwierdzono HEAD/branch, czystość tracked/staged oraz ochronę egg-info.
- [x] Sprawdzono bieżące 72 testy i zgodność 56 schematów/URN oraz 92 wpisów manifestu w jawnej reprezentacji.
- [x] Ustalono zakres core i wykonano niezależny review gotowości ocenionego SHA.
- [ ] Stage 02: zaimplementować usługi/adaptery według macierzy; zależność: istniejące kontrakty Stage 01; blokuje zamknięcie 02.
- [ ] Stage 02: potwierdzić testową instancję PostgreSQL i CI, wykonać integrację/golden/regresję oraz verify_package.py; zależność: środowisko i implementacja; blokuje zamknięcie, nie niezależne kodowanie usług.
- [ ] Stage 02: pozytywny niezależny review końcowego SHA, właściwy commit/merge i post-merge validation; zależność: implementacja i testy; blokuje zamknięcie/przejście do 03.
- [ ] Audyt wejścia Stage 02: dołączyć oryginalny raport GO Stage 01, jeśli dostępny; zależność: artefakt wcześniejszego review; nie blokuje rozpoczęcia na podstawie jawnej instrukcji użytkownika.
- [ ] Etapy 03–20: funkcje wymienione w sekcji granic oraz AGR-01-008–010 po ustaleniu ich treści i przypisania; zależność: właściwe wcześniejsze etapy; nie rozszerzają obecnego odbioru 02, chyba że wykaże się konieczność dla scenariusza core.

**Stage 02 closed: NO. Next stage may begin: NO (Stage 03).**

## Krótki wniosek

Można kontynuować implementację Stage 02 zgodnie z macierzą. Następny krok to uwierzytelnione usługi Case Core i trwały adapter transakcyjny, z potwierdzeniem środowiska testowego. Zamknięcie nadal blokują brak implementacji i dowodów pełnego odbioru.
