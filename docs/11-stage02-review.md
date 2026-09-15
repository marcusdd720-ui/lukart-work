# Stage 02 — niezależny review i naprawy

## Pierwszy review implementacji

Snapshot: `6acd6e8c38a62b04547f6280a0aa753e981d03a8`, branch `stage02/case-core`, parent Stage 01 `e278b97521731b8dc0395560db17e0e601a1d714`.

Osobny subagent `stage02_code_review` analizował rzeczywisty kod/diff oraz baseline, ADR i macierz Stage 02 w trybie read-only. Podczas review snapshot nie był zmieniany. Recenzent przekazał konkretne findingi, lecz jego wykonanie zakończył limit użycia przed końcowym werdyktem. Nie przedstawiamy tego przebiegu jako pełnego pozytywnego review ani własnych testów jako testów wykonanych przez recenzenta.

## Iteracja naprawcza 1

Poniższe identyfikatory porządkują przekazane uwagi. Stan FIXED LOCAL oznacza implementację i przejście dedykowanego testu głównego agenta; niezależne re-review nadal jest osobnym wymaganiem.

| ID | Problem / źródło | Root cause → minimal fix | Test regresyjny | Stan |
|---|---|---|---|---|
| S02-R1-01 | Cofnięcie decyzji blokuje DisputeParty/DisputeFact; service.py w ocenionym SHA:327–332 i 182–186; blokuje wymagany workflow naprawczy | nowa rewizja DISPUTED zachowywała aktywny approval link, a walidacja wymagała live Decision → wyczyść link tylko w nowej rewizji; zachowaj historię i provenance | test_review_r1_dispute_party_after_revocation_preserves_history; test_review_r1_dispute_fact_after_revocation_preserves_sources | FIXED LOCAL |
| S02-R1-02 | Revocation akceptacji snapshotu nie unieważnia planu; service.py:344–346; obowiązek aktualności ze spec | decyzja powstaje po snapshot i nie jest jego member → jawna dodatkowa krawędź tej decyzji do wersji planu | test_review_r1_snapshot_acceptance_revocation_invalidates_plan | FIXED LOCAL |
| S02-R1-03 | P2: replay bez URN/hash, events bez URN, outbox bez kontroli hash/chain; migration.sql:26–37, postgres.py:142–177 | tylko encje/objects miały komplet pinów → rozszerz nowy schemat o URN/hash wyników i events; jeden decoder i wspólna weryfikacja łańcucha; last_event_hash zwraca zapisany hash, nie przelicza historycznego payloadu | test_review_r1_replay_rejects_unknown_contract_and_changed_bytes; test_review_r1_outbox_validates_event_contract_hash_and_chain | FIXED LOCAL |
| S02-R1-04 | P2: rule pin był SHA-256 stałej nazwy; service.py:38; nie identyfikował faktycznych reguł | zastąp etykietę hashem jawnego manifestu źródeł core/domain/contracts/guards, profil LF, wersja policy 1.0.1 | test_review_r1_audit_pin_covers_real_rule_artifact | FIXED LOCAL |

Sześć dedykowanych testów przeszło na rzeczywistym PostgreSQL (14.369 s, 0 błędów). Pełna regresja po zmianach jest zapisana osobno w reports/stage02-status.json i reports/stage02-unittest.txt. Weryfikator pakietu: 61 kontroli PASS, 60 plików JSON. Nie osłabiano asercji ani oczekiwanych wyników poprzednich testów.

Nową strukturę persistence utworzono w osobnej syntetycznej bazie testowej. Stara baza, jej payloady i hashe pozostają niezmienione. Nie uzupełniano starych akceptacji ani wersji na podstawie obecnych modeli.

## Re-review

Recenzent wznowił pełną ocenę na `56faafec9f37da067ee1c3821a5f21e1dd148485`. Potwierdził naprawy S02-R1-01–04, zgodność hashy testowanych źródeł i diff check. Raport 106 PASS był dowodem głównego agenta; recenzent nie deklarował osobnego wykonania testów. Werdykt: NO-GO do merge, z nowym blockerem opisanym poniżej.

## Iteracja naprawcza 2

**S02-R2-01, P1:** po cofnięciu decyzji plan.approval istniejący APPROVED plan pozostaje head. CreateSnapshot odrzuca jego cofnięte approval, a serwis nie udostępniał żadnej ścieżki przejścia planu do SUPERSEDED. To blokowało utworzenie aktualnego snapshotu i nowego planu po zmianie danych. Dowód recenzenta na SHA 56faafe: service.py:249–255 oraz brak operacji w service.py:33 / requests.py:19–21.

Minimalna poprawka: jawny, autoryzowany SupersedePlan dla człowieka, korzystający z istniejącego lifecycle APPROVED→SUPERSEDED. Historia i frozen approval pozostają w nowej rewizji, ale nie są traktowane jako aktywne dopuszczenie przy tworzeniu snapshotu. Stan terminalny nie może zostać ponownie zatwierdzony; nowy plan ma nowy ID.

Regresje: `test_review_r2_revoke_plan_then_supersede_and_approve_replacement` obejmuje cały przepływ cofnięcie → supersede → zmiana danych → nowy snapshot → nowy zaakceptowany plan oraz zachowanie historycznego planu. `test_review_r2_supersede_plan_requires_human_and_legal_transition` sprawdza odmowę aktorowi SERVICE i odrzucenie SUPERSEDED→APPROVED.

Niezależny recenzent potwierdził poprawki na `5efe940b4a68a128b682e23a3403df989ac6370b`. Dodatkowa kontrola przed merge wykazała poniższy blocker i wycofała wcześniejszy techniczny GO dla tego SHA.

## Iteracja naprawcza 3 (ostatnia)

**S02-R3-01, P1:** event_id zależał wyłącznie od klientowskiego command_id oraz etykiety event/invalidated (service.py:88,107 na SHA 5efe940). Idempotency jest ograniczone do tenant/case, a spec wymaga deduplikacji odbiorcy po event_id. Brak gwarancji globalnej unikalności command_id pozwalał na zgubienie odrębnego zdarzenia innej sprawy; nie jest to dowód odczytu cudzych danych.

Minimalna poprawka: przestrzeń UUID obu zdarzeń zawiera zaufane tenant_id i case_id. Zapisany replay oraz historyczne zdarzenia pozostają niezmienione. Test `test_review_r3_event_ids_distinguish_scopes_and_preserve_replay` powiela command_id w dwóch sprawach jednej organizacji oraz w trzeciej sprawie innej organizacji. Sprawdza odrębność zwykłych zdarzeń i DependenciesInvalidated, zgodność outbox oraz identyczny replay.

Test przed poprawką: FAIL w 10.751 s przy kolizji drugiej sprawy. Ten sam test po poprawce: PASS w 20.154 s. Pełna regresja i niezależny re-review zamrożonego commita są osobnymi dowodami. Wykorzystano trzy z trzech dopuszczonych iteracji naprawczych.

Formalne kryteria odbioru nadal obejmują końcowy SHA, merge/post-merge oraz CI. Zakaz push pozostaje w mocy; workflow nie jest dowodem jego wykonania.
