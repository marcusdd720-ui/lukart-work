# Stage 02 — odbiór Case Core

**Aktualizacja 2026-09-16:** po zgodzie użytkownika opublikowano afbd195 i uzyskano CI SUCCESS. Aktualny odbiór GO i dowody: [12-stage02-closure.md](12-stage02-closure.md). Poniższy raport zachowuje stan sprzed publikacji, gdy brak CI rzeczywiście blokował zamknięcie.

## Stan odbioru implementacji

Punkt wejścia: e278b97521731b8dc0395560db17e0e601a1d714, main, tylko zastany egg-info poza repo oraz raport gotowości z poprzedniej tury. Implementacja rozwija macierz w `08-stage02-readiness.md`. Nie zmieniono Architektury 00, 23 encji, kontraktów historycznych ani repozytorium ROS.

**Zamknięcie Stage 02: NO-GO — brak wykonanego CI na końcowym SHA.** Implementacja, niezależny review kodu, lokalny merge i testy po merge zostały wykonane. Ten dokument nie zastępuje niezależnego review na konkretnym końcowym SHA.

Oceniony i scalony commit kodu: `d9cabf319a30ee3f633f74df386899af317bd3df`. Branch odbioru: `main`; merge fast-forward z `stage02/case-core`, bez push. Śledzone drzewo po merge było czyste; jedynym nieśledzonym katalogiem pozostaje zastany egg-info. Końcowy commit aktualizuje jedynie dokumentację, raporty i manifest; jego dokładny SHA zostanie wskazany w końcowym odczytowym review.

Pierwszy review kodu na `6acd6e8c38a62b04547f6280a0aa753e981d03a8` zgłosił konkretne problemy i został przerwany limitem użycia przed werdyktem. Wykonano iterację naprawczą 1; root causes, poprawki i sześć osobnych regresji opisuje `11-stage02-review.md`. Nie przypisujemy zatwierdzenia pierwszego snapshotu zmienionemu kodowi.

Re-review na `56faafec9f37da067ee1c3821a5f21e1dd148485` potwierdził te poprawki, ale zgłosił blokadę odzyskania workflow po cofnięciu plan.approval. Iteracja 2 dodaje przewidziany w lifecycle SupersedePlan oraz dwa testy całego scenariusza i autoryzacji. Iteracja 3 usuwa kolizję identyfikatorów zdarzeń przy jednakowym command_id w różnych tenant/case; regresja obejmuje także invalidation i replay. Szczegóły i aktualny stan niezależnej oceny: `11-stage02-review.md`.

## Macierz bieżącego stanu

| Wymaganie i źródło | Implementacja | Dowód | Stan |
|---|---|---|---|
| 23 encje i zgodność schematów; baseline §5 | niezmienione domain/contracts, dwa nowe envelopes CoreRequest/CoreQuery | verify_package.py; istniejące testy kontraktów | VERIFIED lokalnie |
| Authenticated CommandService i scope; spec Komendy/Error model | core/security.py, core/requests.py, core/service.py | actor assignment, metadata rejection, explicit grants, cross-scope read/write, revoked replay, AI/human boundary | VERIFIED dla lokalnego adaptera tokenów |
| CreateCase i wymagane handlers VerifyParty/ConfirmFact/ApprovePlan/RecordDecision | jawne operacje w service.py, serwerowe rewizje i aktor | full_core_golden_all_guards_and_plan_approval, błędna decyzja/target/status | VERIFIED w obsługiwanym zakresie Case Core |
| Rewizje, heads i CAS; ADR-08 | core/postgres.py, migration.sql, scoped advisory lock | dwa rzeczywiste połączenia: jeden sukces; historia po edycji; stale target conflict | VERIFIED |
| Snapshot i dokładna akceptacja; spec Snapshoty, AGR-001/006 | osobny immutable snapshot i acceptance, aktualne decyzje i input heads | pełny golden, podmieniony hash, zmiana head po freeze, brak akceptacji | VERIFIED |
| Queries i źródła | chronione odczyty, hash oryginalnych bytes, graph traversal provenance | source download, cross-case rejection, history, source corruption | VERIFIED lokalnie |
| Idempotency po restarcie | persisted commands/result, auth przed replay i CAS | osobny proces Python zwraca identyczny rezultat, inny body konflikt, revoked token denied | VERIFIED |
| Atomic audit/outbox + izolacja; spec DomainEvent, I01–I04 | jedna transakcja, RLS/FK, runtime bez owner/superuser/BYPASSRLS | wymuszony błąd FK przy outbox cofa encję/head/sequence/audyt/result; read/write isolation | VERIFIED |
| KG / DAG rozdzielone, aktualność | dependency records pochodzą z jawnego snapshotu planu; atomowe DependenciesInvalidated | golden: DisputeFact emituje invalidation planu, bez zmiany historycznego APPROVED | VERIFIED w zakresie planów; draft engines później |
| Bezpieczne błędy, wersje i fail-closed | ścisły JSON, bounded request, whitelist operacji, hash przed parse, nieznany URN denied | unknown stored contract zachowuje raw payload; parser/PII tests; RequestRelease denied | VERIFIED lokalnie |
| DoD baseline §47 | implementacja + testy syntetyczne/real DB + docs + niezależny review kodu + lokalny merge/post-merge | GO recenzenta na d9cabf3, pełna regresja po merge | VERIFIED lokalnie; pełny odbiór UNVERIFIED z powodu CI |
| CI na dokładnym SHA; docs/06-status.md:89 (87 w bazowym e278b97) | workflow .github/workflows/stage02.yml | workflow nie został uruchomiony; zakaz push | UNVERIFIED — jedyny pozostały blocker zamknięcia |

## Weryfikacja i ograniczenia

Bieżące dane liczbowe i dokładne hashe testowanych plików źródłowych znajdują się w `reports/stage02-status.json`; pełny log w `reports/stage02-unittest.txt`. `reports/package-validation.json` zawiera bieżący wynik weryfikatora pakietu. Historyczne `reports/status.json` i `reports/unittest.txt` nadal dotyczą Stage 01.

Wyniki końcowe na d9cabf3:

- `python -B -X utf8 scripts/verify_stage02.py`: **109 PASS, 0 failures/errors/skips**, 94.373 s.
- Po `git merge --ff-only stage02/case-core` do main: `python -B -X utf8 -m unittest discover -v`: **109 PASS**, 77.771 s; pełny log `reports/stage02-postmerge-unittest.txt`.
- `python -B -X utf8 verify_package.py` przed i po merge: **61 kontroli PASS, 60 JSON**.
- `git diff --check`, przegląd diff i staged: PASS. Niezależny review potwierdził 29/29 hashy źródeł i 116/116 wpisów ówczesnego manifestu. Manifest raportów jest aktualizowany osobno po dodaniu dowodu post-merge.
- Trzy iteracje naprawcze; ostatnia regresja przed poprawką FAIL, po poprawce PASS. Recenzent nie zgłosił otwartych blockerów kodu.

Pierwszy przebieg 23 testów Stage 02 na PostgreSQL wykazał dwa błędy tego samego pochodzenia: ReviewFact zastępował provenance pustymi listami. Poprawka zachowuje źródła przy zmianie statusu; osobny test `test_fact_transition_preserves_provenance` wykrywa pierwotny błąd. Kolejne 28 testów Stage 02 przeszło. Pełna regresja obejmuje 100 testów (72 wcześniejsze + 28 nowych), bez SKIP; ostateczny wynik należy odczytać z bieżącego raportu, a nie z tej historycznej liczby.

Lokalne środowisko: Python 3.14.7, Pydantic 2.13.5, psycopg 3.3.3, PostgreSQL 18.6. Archiwum EDB: SHA-256 `59f8ce701c63c2ed623c665a5e51b3ef6f2e37ccf837b68ffeed0742d0ae6abd`. Baza testowa jest odizolowana, zawiera tylko syntetyczne dane i używa osobnego runtime role. Nie instalowano usługi Windows.

Uruchomienia Pythona wymagały eskalacji narzędzia po odmowie dostępu w sandboxie. Zależność PostgreSQL i lokalne archiwum pobrano po zgodach narzędziowych. Początkowy test bez przygotowanej bazy miał jawne SKIP i nie był uznany za odbiór. Poprawiono także oczekiwanie skryptu startowego: PowerShell Start-Process -Wait oczekiwał na cały proces potomny serwera; obecnie oczekuje tylko na zakończenie pg_ctl.

Manifest repozytorium dotyczy tekstu z CRLF znormalizowanym do LF. Historyczne payloady domenowe i oryginalne bytes źródeł nie przechodzą tej normalizacji: payload jest sprawdzany według zapisanych UTF-8 bytes LW-CJSON-1, a source według oryginalnych bytes. Nie przeliczano historycznych akceptacji ani hashy danych sprawy.

Przygotowano workflow `.github/workflows/stage02.yml`. **Nie uruchomiono zdalnego CI na nowym SHA**: instrukcja zabrania push. Lokalna regresja nie jest przedstawiana jako wykonane zdalne CI. Nie twierdzimy, że brakujące walidatory prawne, rendering czy certyfikacja zostały zastąpione testami syntetycznymi.

## Pliki zmiany

- `lukart_work/core/`: requests, security, service, postgres, migration SQL i package init.
- `tests/test_stage02.py`, `tests/stage02_restart_probe.py`: scenariusze core i procesowy replay.
- `schemas/CoreRequest.schema.json`, `schemas/CoreQuery.schema.json`, export_contracts.py, verify_package.py.
- `scripts/`: start/prepare local DB, prepare CI DB, verify_stage02, refresh_manifest.
- `.github/workflows/stage02.yml`, `.gitignore`, pyproject.toml, README.md.
- `docs/08-stage02-readiness.md`, `docs/09-stage02-implementation.md`, ten raport oraz raporty wykonania/manifest.

`lukart_work_domain_contracts.egg-info/` pozostaje nietknięty i poza commitami. `.local-stage02/` jest ignorowany; sekrety i dane testowej bazy nie są artefaktem repozytorium.

## Co zostało do zrobienia

- [x] Przygotowano i sprawdzono izolowaną bazę PostgreSQL oraz runtime role.
- [x] Wykonano scenariusz core i regresję provenance, transakcji, izolacji i replay.
- [x] Stage 02: niezależny review implementacji na d9cabf319a30ee3f633f74df386899af317bd3df; trzy iteracje napraw zakończone, GO do merge.
- [x] Stage 02: lokalny merge do main i pełna regresja po merge na tym samym SHA.
- [ ] Stage 02: wykonanie CI na końcowym SHA; zależność: opublikowanie zmian, obecnie zabronione; blokuje bezwarunkowy odbiór.
- [ ] Stage 03 i później: pełny storage/versioning, zewnętrzne identity/policy, validators/rendering/audit hardening; zależność: właściwe wcześniejsze etapy; nie poszerza Stage 02.
- [ ] AGR-01-008–010: pozostają odłożone; treść i przypisanie do etapów nie są udokumentowane w tym repo; nie deklarujemy ich naprawy.

**Stage 02 closed: NO. Next stage may begin: NO.**

## Krótki wniosek

Kod Case Core przeszedł niezależny review i pełne testy po lokalnym scaleniu; Stage 03 nie został rozpoczęty. Następny krok do zamknięcia to wykonanie CI na końcowym SHA. Przygotowany workflow GitHub wymaga publikacji zmian, której obecna instrukcja zabrania.
