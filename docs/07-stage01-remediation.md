# Stage 01 remediation — AGR-01-001–007

Zakres: wyłącznie siedem blockerów niezależnego Architecture Gate Review 01 → 02. Architektura 00 nie została zmieniona. Nie zaimplementowano Stage 02, autoryzacji, repozytorium, transakcji ani produkcyjnego release service. Nie przyznajemy GO; następny krok to osobny niezależny review.

## Root cause → minimal fix → focused test

| Finding | Przyczyna | Minimalna poprawka | Regresja w tests/test_remediation.py |
|---|---|---|---|
| AGR-01-001 | Ref nie reprezentuje snapshotu | SnapshotTarget w Decision; validate_snapshot_acceptance i validate_accept_snapshot sprawdzają scope, ID/hash, Case target i HUMAN/RECORDED/ACCEPT | test_agr_001_snapshot_acceptance_exact_binding; test_agr_001_snapshot_acceptance_requires_human_accept |
| AGR-01-002 | Approval wskazuje tylko Draft, a gate porównuje wyłącznie run/request render hashes | RenderTarget przypina dokładne bytes; gate odrzuca zmianę renderu; ReleaseReceipt wiąże podstawę wydania | test_agr_002_approval_cannot_be_reused_for_another_render; test_agr_002_receipt_and_approval_fail_closed |
| AGR-01-003 | Lock rewizji nie obejmował ValidationFinding | Immutable run/target/hash/layer/code/severity/message/path; resolution wymaga ludzkiej decyzji o poprzedniej rewizji | test_agr_003_finding_content_is_immutable; test_agr_003_resolution_requires_exact_human_decision |
| AGR-01-004 | Spłaszczenie relacji zmieniało zakres unikalności | Unikalność kolekcji liściowej; Participation według party/role | test_agr_004_reuse_fact_and_citation_across_statements; test_agr_004_participation_uniqueness_is_party_and_role |
| AGR-01-005 | Użyte inputs pomijały citations | Wspólny validate_section_inputs dla AI i Draft liczy refs + citations, sprawdza typy i allowed_claims | test_agr_005_required_citation_is_counted_in_ai_and_domain |
| AGR-01-006 | Snapshot closure obejmowała Ref, nie źródła; brak zgodności plan–draft | Source closure/scope/hash; wymagany zaakceptowany snapshot, identyczne piny i przynależność inputs | test_agr_006_snapshot_source_closure; test_agr_006_plan_draft_snapshot_and_acceptance; test_agr_006_used_input_must_belong_to_snapshot |
| AGR-01-007 | Brak strukturalnych guardów normatywnych | Cykl rodziców, SATISFIED satisfaction, recipient i Request ownership planu | test_agr_007_proceeding_parent_cycles; test_agr_007_deadline_satisfaction; test_agr_007_plan_filing_ownership |

## Kontrakty akceptacji i receipt

SnapshotTarget zawiera tenant_id, case_id, snapshot_id, snapshot_hash. Decision typu SNAPSHOT_ACCEPTANCE wymaga tego pola i nie może mieć render_target. Decyzja wskazuje także jeden Case Ref obecny w members. Hash dotyczy całego Snapshot według istniejącego LW-CJSON-1. validate_accept_snapshot rozwiązuje Decision ze scoped records; nie przyjmuje deklarowanej tożsamości człowieka jako uwierzytelnienia. Authoritative records, autoryzacja, aktualne revocations i CAS pozostają warunkami przyszłego adaptera.

RenderTarget dodaje Draft Ref/hash i niepustą uporządkowaną listę unikalnych render_hashes. Draft hash wiąże również reproduction/render profile. DOCUMENT_APPROVAL wymaga dokładnie tego Draft target; istniejący lock RECORDED chroni także nowe pola. Zmiana któregokolwiek pinu wymaga nowego zatwierdzenia, nie edycji starej decyzji.

ReleaseReceipt zawiera target, approval Ref/hash, niepuste pins runów (ID/hash), policy i case_sequence. Jego digest jest deterministycznym identyfikatorem treści receipt. evaluate_release emituje receipt wyłącznie przy FINAL; DRAFT nie ma receipt. Funkcja nadal ocenia jeden kompletny run, nie łączy częściowych PASS z różnych runów. Receipt stanowi kontrakt dowodowy, nie podpis ani dowód atomowego utrwalenia. Zapis receipt/audit/outbox w jednej transakcji jest zadaniem przyszłej usługi.

## Snapshot i lifecycle

validate_state dla wygenerowanego Draft wymaga keyword arguments snapshot i snapshot_approval. Brak danych blokuje guard. Sprawdzane są źródła members, hash i scope snapshotu, jego akceptacja, zgodność pinów plan–draft, przynależność wejść planu oraz użytych refs/citations do members. Plan/Decision mogą powstać po zamrożeniu snapshotu: nie wymagamy ich członkostwa w jego wejściu i nie tworzymy cyklu akceptacji.

Graph/state/revision pozostają odrębnymi, wymaganymi guardami. Walidacja źródeł porównuje metadane hashy; weryfikacja oryginalnych bytes i sensu fragmentu nadal należy do SourceDocumentPort oraz validatorów. Sama poprawność strukturalna nie dowodzi prawdziwości źródła.

ValidationFinding zachowuje treść obserwacji. Zmiana statusu/resolution ma nową rewizję i ludzką decyzję o poprzedniej wersji; nie usuwa blokującego severity. Nowy wynik merytoryczny wymaga nowego runu/findingu. Istniejący gate nadal blokuje ERROR/BLOCKER/CRITICAL nawet po RESOLVED/FALSE_POSITIVE.

## ADR i kompatybilność

ADR-01/05 uzupełniono o typowane cele akceptacji i receipt; rozdzielenie FINAL od lifecycle i decyzja o poprzedniej rewizji encji pozostają. ADR-02/03/04/06/07/08/09 pozostają bez zmiany kierunku. Nie dodano kanonicznej encji Snapshot ani Render.

Pakiet 0.1.1 publikuje nowe główne wersje zmienionych kontraktów: lista jest jawna w contracts/versions.py. Ich URN ma 2.0.0; nowe pomocnicze kontrakty zaczynają od 1.0.0. Entity.schema_version=1.0.0 nadal oznacza format wspólnych metadanych, nie wersję policy/guardów ani całego kontraktu. Konsument musi przypiąć pełny kontrakt przez URN/VersionPin. Wymóg registry odrzucającego nieznane wersje pozostaje zadaniem adaptera.

Nie migrujemy automatycznie historycznych Decision: brak dokładnego zatwierdzonego snapshotu/renderu nie może zostać uzupełniony na podstawie bieżącego stanu. Historyczny payload/hash pozostaje dowodem historycznym; nowe dopuszczenie wymaga jawnej weryfikacji i nowej decyzji. Wzmocnione guardy mogą odrzucić stare dane i wymagają osobnego przeglądu, nie przepisywania historii.

## Weryfikacja i dalsza praca

Po focused regressions należy wykonać export_contracts.py, verify_package.py, pełny unittest discover i git diff. Wyniki bieżącego wykonania są w reports/package-validation.json, reports/unittest.txt i reports/status.json. Testy pozostają syntetyczne; PASS nie oznacza autorytatywnej walidacji prawnej ani zakończenia DoD całego produktu.

Po jednym commicie remediation: niezależny Architecture Gate Review na jego SHA. Dopiero odrębna decyzja użytkownika określi dalszy etap. Findingi AGR-01-008–010 nie są przedmiotem tej zmiany.
