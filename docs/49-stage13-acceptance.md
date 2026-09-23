# Stage 13 — Acceptance / Evidence Matrix

Status: PRE-FINALIZATION — EXECUTED CI AND PERFORMANCE EVIDENCE AVAILABLE; FINAL EXACT-SHA CI AND INDEPENDENT REVIEW PENDING

## Offline Capability Matrix

| Funkcja | Online | Offline | Local LLM | Remote LLM | Aktualne evidence / ograniczenie |
|---|---|---|---|---|---|
| CASE contracts / validation | tak | tak po instalacji zależności | n/a | n/a | pełna regresja PASS na `a2b9026...`; final exact-SHA rerun wymagany |
| deterministic DOCX/PDF rendering | tak | tak po instalacji zależności/fontów | n/a | n/a | regresja i benchmark PASS na `a2b9026...` |
| canonical persistence using local PostgreSQL | tak | local-host capable | n/a | n/a | CI użyło lokalnego PostgreSQL; production-equivalent offline benchmark nie był wykonywany |
| filesystem artifact storage | tak | local-host capable | n/a | n/a | environment-specific |
| Stage 09 controlled drafting | tak | provider-dependent | adapter path implemented | istniejący hosted path może działać osobno | Stage 13 provider tests PASS na `a2b9026...` |
| Ollama inference adapter | tak na dozwolonym endpoint | zaprojektowany dla loopback/local host | implemented | brak nowego remote providera w Stage 13 | live Ollama execution `NOT EXECUTED` |
| current public legal research | tak | nie, chyba że istnieje osobny aktualny autorytatywny local corpus | n/a | n/a | `REMOTE_REQUIRED` dla freshness w obecnej architekturze |
| GitHub CI / assurance | tak | nie | n/a | n/a | runtime: `REMOTE_OPTIONAL`; promotion: `REQUIRED` według obecnego standardu |

Stage 13 NIE oznacza, że cały CASE lifecycle jest `OFFLINE READY`.
Stage 13 ustanawia offline-capable local-model execution path i jawnie pozostawia
remote-required capabilities poza tym zakresem.

## Dependency Matrix

| Dependency | Local | Remote | Optional | Required | Fail behavior |
|---|---|---|---|---|---|
| Python/Pydantic runtime | tak | nie po instalacji | nie | tak | fail closed |
| local PostgreSQL | tak | możliwy remote deployment | deployment choice | tak dla PostgreSQL-backed CASE operations | fail closed |
| local filesystem/object storage | tak | możliwy | deployment choice | operation-dependent | fail closed |
| rendering dependencies/fonts | tak | nie po instalacji | nie dla renderingu | rendering-only | fail closed |
| Ollama | tak | LAN tylko po explicit allowlist i `local_only=False` | tak dla non-LLM operations | local inference only | fail closed |
| hosted LLM provider | nie | tak | tak | nie dla local-model mode | provider-specific |
| public current legal sources | local corpus nie został wdrożony | tak | nie, gdy fresh legal research jest wymagany | task-dependent | `UNKNOWN/ABSTAIN`, gdy freshness nie może być ustalone |
| GitHub Actions | nie | tak | runtime: tak | promotion: tak | promotion blocked bez evidence |

## Performance evidence

Baseline:
- exact SHA: `6968c9df1130673ecb89417d82cd25ecabfc00fe`;
- run: `35788342721`;
- result: `SUCCESS`.

Post-implementation:
- exact SHA: `a2b9026cf59995774c9fd84c14510cc1b171c068`;
- run: `35832948690`;
- benchmark step: `PASS`;
- `network_io=NOT_USED`;
- `case_data=SYNTHETIC_ONLY`.

Poniższe wartości są pomiarem na tym samym typie self-hosted środowiska WSL2/Python 3.14.7.
Nie są uniwersalnym SLO. Delta oznacza zmianę obserwowanego p50 względem baseline.

| Operacja | Baseline p50 | Po Stage 13 p50 | Delta p50 | Post p95 | Post p99 | Post Peak RAM | Status |
|---|---:|---:|---:|---:|---:|---:|---|
| cold import | 716.903 ms | 617.301 ms | -13.9% | 667.233 ms | 667.233 ms | n/a | MEASURED |
| canonical digest | 0.5858 ms | 0.4080 ms | -30.4% | 0.6673 ms | 0.9080 ms | 139452 B | MEASURED |
| AIRequest validation | 0.0329 ms | 0.0167 ms | -49.2% | 0.0347 ms | 0.0485 ms | 66164 B | MEASURED |
| ModelExecutionReceipt validation | 0.0263 ms | 0.0125 ms | -52.5% | 0.0134 ms | 0.0326 ms | 65668 B | MEASURED |
| render DOCX+PDF bundle | n/a | 117.625 ms | n/a | 127.388 ms | 127.388 ms | 4470794 B | MEASURED |
| render bundle validation | n/a | 1.4626 ms | n/a | 1.7486 ms | 1.8343 ms | 86318 B | MEASURED |
| revision-ledger test harness replay | n/a | 0.1015 ms | n/a | 0.1248 ms | 0.1714 ms | 66261 B | MEASURED |
| Ollama config validation | n/a | 9.5432 ms | n/a | 12.1330 ms | 17.1429 ms | 742221 B | MEASURED |
| deterministic digest concurrency 4x64 | n/a | 35.6778 ms | n/a | 37.3674 ms | 37.3674 ms | 160881 B | MEASURED |
| live Ollama inference | NOT MEASURED | NOT MEASURED | n/a | n/a | n/a | n/a | NOT EXECUTED |

Baseline peak-memory i CPU fields dla pierwszej generacji baseline nie są sztucznie uzupełniane,
jeżeli nie zostały zapisane przez artefakt. Brak pomiaru pozostaje brakiem pomiaru.

## Determinism

`DETERMINISTIC`:
- validation and domain contracts;
- canonical hashes/serialization where defined;
- execution receipts;
- render model/layout/artifact identity;
- ledger/replay semantics covered by prior Stages;
- benchmark fixture inputs.

`NON-DETERMINISTIC BY DESIGN`:
- raw LLM inference output.

Nie jest składane roszczenie o byte-exact reproducibility LLM output.

## Critical promotion gates

- exact-SHA baseline artifact: PASS — run `35788342721`;
- focused Stage 13 tests: PASS na pre-finalization SHA `a2b9026...`;
- full regression: PASS, 470/470 na `a2b9026...`;
- schema validation: PASS na `a2b9026...`;
- package verification: PASS na `a2b9026...`;
- performance artifact: PASS na `a2b9026...`;
- manifest refresh: PASS, canonical manifest wymaga synchronizacji z repo;
- manifest stabilized: PENDING do chwili świeżego clean-diff CI;
- reproducibility / clean diff: PENDING po synchronizacji manifestu;
- final exact-SHA Red Team delta check: PENDING;
- independent exact-SHA review: PENDING;
- merge/landing authorization: HUMAN GATE;
- post-landing verification: PENDING.

Po zmianie dokumentacji/manifestu powstaje nowy SHA.
PASS z `a2b9026...` jest evidence poprzedzającym finalizację, ale nie certyfikuje nowego SHA.

Current status is not `SEND_READY`.
