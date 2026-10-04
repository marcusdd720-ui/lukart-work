# LUKART WORK — controlled drafting and validation

PB02 builder candidate adds an authenticated, PostgreSQL-backed finalization boundary for
synthetic or separately admitted document types. It derives the semantic document from trusted
records, persists exact DOCX/PDF bytes, records the HUMAN document approval and post-render
validation evidence, and issues a durable FINAL eligibility receipt. It does not admit any real
PL letter type, assemble the later ten-member final package, submit a filing, or certify the
product. See [the PB02 boundary and verification contract](docs/PB02_FINALIZATION.md).
Focused verification: `python -B -X utf8 -m unittest -v tests.test_finalization`; schema/package
verification: `python -B -X utf8 verify_package.py`. PostgreSQL tests must execute with zero
skips against the isolated runtime/admin DSNs.

Stage 10 (pakiet 0.10.0): walidacja pomiędzy GENERATED a późniejszym renderingiem.
`lukart_work.validation.service.ValidationEngineService` udostępnia `execute` dla jawnych
poleceń walidacji, oceny człowieka i rozstrzygnięcia findings oraz `query` dla bieżącej kwalifikacji.
[Zakres i dowody wejściowe](docs/37-stage10-readiness.md),
[kontrakty, użycie i ograniczenia](docs/38-stage10-implementation.md),
[odbiór i Red Team](docs/39-stage10-acceptance.md).
Pełny runner: `python -B -X utf8 scripts/verify_stage10.py`; każdy SKIP oznacza FAIL.
Stage 10 pozostaje przed niezależnym review i merge. Nie realizuje renderowania ani FINAL.

Poniższe opisy wcześniejszych etapów są historyczne; dowody ich późniejszego zamknięcia
zestawiono w gotowości Stage 10.

Stage 05 (pakiet 0.5.0): ludzki przegląd kandydatów, lifecycle faktów i dowodów,
wersjonowane decyzje oraz macierz pochodzenia i aktualności potwierdzeń.
[Zakres](docs/23-stage05-readiness.md), [interfejs](docs/24-stage05-implementation.md),
[odbiór](docs/25-stage05-acceptance.md). Pełny runner:
`python -B -X utf8 scripts/verify_stage05.py`. Stage 06 nie rozpoczęto.

Stage 04 (pakiet 0.4.0): ekstrakcja TXT, DOCX, e-mail i tekstowych PDF,
wersjonowane wyniki z pochodzeniem i kandydatami bez automatycznych akceptacji.
[Zakres i macierz](docs/18-stage04-readiness.md),
[interfejs i ograniczenia](docs/19-stage04-implementation.md),
[odbiór](docs/20-stage04-acceptance.md). Instalacja:
`python -m pip install '.[postgres,ingestion]'`. Pełna kontrola:
`python -B -X utf8 scripts/verify_stage04.py` (SKIP oznacza FAIL).
Skany wymagają OCR; częściowa ekstrakcja jest jawna. Stage 05 nie rozpoczęto.

[Stage 04 — odbiór GO i dowody zamknięcia](docs/22-stage04-closure.md).

[Stage 03 — odbiór GO i dowody zamknięcia](docs/17-stage03-closure.md).

Stage 03 (pakiet 0.3.0): scoped storage oryginałów i artefaktów, niezależne wersje, jawne migracje, retencja/legal hold oraz sprawdzone backup/restore. [Zakres](docs/13-stage03-readiness.md), [interfejs i ograniczenia](docs/14-stage03-implementation.md), [odbiór](docs/15-stage03-acceptance.md), [niezależny review](docs/16-stage03-review.md). Włączenie storage jest jawne w konfiguracji hosta; etap nie uruchamia ingestion ani deploymentu.

Stage 02 (pakiet 0.2.0): uwierzytelniony serwis intencji, trwały PostgreSQL, rewizje append-only, snapshoty, decyzje i atomowy audit/outbox. Opis i granice: [docs/09-stage02-implementation.md](docs/09-stage02-implementation.md). [Odbiór po CI](docs/12-stage02-closure.md): GO na afbd195, 109 testów PASS lokalnie i w GitHub Actions, pozytywny niezależny review oraz merge/post-merge. Końcowy commit raportu podlega własnemu review i CI.

Pakiet wykonawczy rozwijający zatwierdzoną Architekturę 00. Zawiera 23 encje, wspólne typy, lifecycle, relacje, kontrakty, generowane JSON Schema, deterministyczne kontrole i syntetyczne testy.

Stage 01 remediation AGR-01-001–007: pakiet 0.1.1. Zmienione kontrakty mają URN 2.0.0; format wspólnych metadanych Entity.schema_version pozostaje 1.0.0. Szczegóły, migracja i mapa regresji: [docs/07-stage01-remediation.md](docs/07-stage01-remediation.md). Wymagany jest osobny niezależny Architecture Gate Review; nie jest to zgoda na Stage 02.

**Nie jest produkcyjnym Case Core ani certyfikowanym generatorem pism.** Szczegółowy status: docs/06-status.md i reports/status.json.

## Czytanie

1. docs/01-specification.md — decyzje, agregaty, trust chain, invariants, snapshots, AI, gate.
2. docs/02-entity-catalog.md — komplet pól, typów, required/optional i dozwolonych przejść 23 encji.
3. docs/03-relations.md — macierz relacji/cardinality i source-of-truth semantics.
4. docs/04-test-specification.md — executed scenarios oraz niewykonane testy integracyjne.
5. docs/05-compliance.md — śledzenie do sekcji Architektury 00.
6. docs/06-status.md — wyniki, ograniczenia, ryzyka, DoD i rekomendacja.

## Uruchomienie

Python 3.11+ oraz pydantic==2.13.5. Weryfikowana wersja środowiska jest zapisana w reports/status.json.

```bash
python -m pip install -e .
python export_contracts.py
python -m unittest discover -v
python verify_package.py
```

Lokalnie wykorzystano zainstalowany Pydantic; polecenie pip install nie było potrzebne ani wykonane. Importy nie wykonują operacji sieciowych. Tests używają unittest ze standardowej biblioteki.

Entry points: domain/models.py, contracts/messages.py, contracts/ports.py, validation/rules.py. Schematy są eksportem, nie osobno edytowanym źródłem. RevisionLedger to sekwencyjny test harness, nie repozytorium produkcyjne. `evaluate_release` przyjmuje zaufane rekordy załadowane przez przyszły serwis, nie payload klienta.

Usługi Stage 02 znajdują się w `lukart_work/core/`. Instalacja opcjonalnego adaptera: `python -m pip install '.[postgres]'`. Pełna kontrola Stage 02: `python -B -X utf8 scripts/verify_stage02.py` — każdy SKIP jest brakiem dowodu i powoduje FAIL. Repozytorium LUKART ROS pozostaje poza zakresem.
