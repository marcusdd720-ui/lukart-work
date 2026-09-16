# LUKART WORK — Domain Contracts + Stage 02 Case Core

Stage 02 (pakiet 0.2.0): uwierzytelniony serwis intencji, trwały PostgreSQL, rewizje append-only, snapshoty, decyzje i atomowy audit/outbox. Opis i granice: [docs/09-stage02-implementation.md](docs/09-stage02-implementation.md). [Bieżący odbiór Stage 02](docs/10-stage02-acceptance.md): 109 testów PASS, pozytywny niezależny review kodu i lokalny merge/post-merge; zamknięcie NO-GO do wykonania CI na końcowym SHA.

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
