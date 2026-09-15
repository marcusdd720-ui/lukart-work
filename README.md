# LUKART WORK — 01 Domain Model & Contracts

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

Do etapu 02 trzeba wdrożyć pełną orkiestrację guardów, authorization, transakcje, trwałe CAS/idempotency/outbox oraz integracyjne testy bezpieczeństwa. Ten pakiet nie zmienia repozytorium LUKART ROS.
