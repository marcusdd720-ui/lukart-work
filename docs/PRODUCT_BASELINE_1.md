# LUKART WORK PRODUCT BASELINE 1 — LW-PB-01

Repozytorium: `marcusdd720-ui/lukart-work`. Exact base: `f88c3137ef96542ac836478d0f266dcc883ec406`.
Kontrakt maszynowy: [product-baseline-v1.json](../acceptance/product-baseline-v1.json).
Status: **kontrakt buildera do niezależnego review; produkt PLANNED; Certified = nie**.
Dokument nie nadaje wsparcia funkcji bez wykonania odpowiedniego odbioru. Nie zmienia publicznych URN, modeli, SQL, workflow ani policy pins. Bieżący manifest plików jest indeksem integralności; historyczne wyniki/receipts nie są nadpisywane. Stage 14 i ROS są poza zakresem.

## 1. Zamrożona granica

Minimalny produkt realizuje jedną publiczną, autoryzowaną ścieżkę od CreateCase, przez materiał, HUMAN acceptance, snapshot, plan, kontrolowany Draft, walidację, trwały DOCX/PDF, final HUMAN approval i release, do odczytywalnego po restarcie pełnego pakietu. FINAL jest kwalifikacją wydania z trwałym receipt, a nie deklaracją modelu i nie statusem SUBMITTED. Dzisiejszy Draft ma PLANNED/GENERATED/VALIDATED/APPROVED/RENDERED/CERTIFIED; nie dodajemy w LW-PB-01 statusu FINAL.

Pierwszy katalog ogranicza się do następujących typów. Identyfikatory poniżej są **kontraktem planowanego katalogu**, nie obecnymi wpisami rejestru ani zweryfikowanymi VersionPin.

| ID | Typ | Wymagane wejścia specyficzne |
|---|---|---|
| PL-PRE-PAYMENT-1 | Wezwanie do zapłaty | claim_basis; principal_amount_decimal; currency_PLN; performance_due_date; payment_history; requested_payment_date_human; payment_destination |
| PL-PRE-COMPLAINT-1 | Reklamacja wykonania umowy | contract_subject; performance_date; documented_defect; prior_correspondence; requested_remedy; requested_response_date_human |
| PL-PRE-REPLY-1 | Odpowiedź na wezwanie do zapłaty | incoming_demand_source; incoming_demand_date; asserted_amount_decimal; admitted_and_disputed_items; response_position_human; supporting_evidence |

Jurysdykcja PL, język pl-PL, kwoty PLN. Krajowa korespondencja przedprocesowa dotycząca umowy, pełnoletnie osoby lub podmioty, bez spraw transgranicznych i sektorów regulowanych. Reklamacja oznacza opis udokumentowanego nienależytego wykonania i wybrane przez HUMAN żądanie; kontrakt nie obiecuje obsługi szczególnych reżimów konsumenckich. Wybór podstawy i skutków prawnych pozostaje HUMAN, z wersjonowanymi źródłami i oceną zastosowania na konkretną datę. Nie stwierdzamy tu aktualnej treści przepisów.

Każdy typ wymaga odrębnego versioned input schema, profilu planu/promptu oraz testu T01. Wspólny renderer nie jest dowodem wsparcia typu. **Każdy z trzech typów ma dzisiaj NOT SUPPORTED / FUTURE** — tabela opisuje zakres docelowego kontraktu, nie funkcje już przyjęte. Zmiana katalogu lub jurysdykcji wymaga nowej wersji kontraktu i odbioru; baseline nie jest całym katalogiem docelowym Architecture 00.

Poza baseline: Court pleadings, appeals, enforcement and administrative/office letters; ZUS/UFG/banking/insurance and special consumer regimes; Foreign/cross-border jurisdiction or currencies other than PLN; OCR and quotations from non-TXT without a verified locator adapter; Automatic statutory deadlines, interest or limitation periods; External filing, e-signature or delivery effectiveness; HTML/TXT export, QUICK/FORENSIC additional modes; Autonomous legal/adversarial truth certification; Stage 14 dependency or ROS integration. Nie obiecujemy automatycznych odsetek, przedawnienia, skuteczności doręczenia, podpisu elektronicznego ani obiektywnej prawdziwości faktów. Puste/missing/UNKNOWN nie zostaje domyślnym PASS.

## 2. Wejścia i odpowiedzialności

Wymagane wspólnie: tenant_id; case_id; HUMAN_identity_and_scoped_capabilities; retention_policy_pin; document_type_pin; PL_jurisdiction_confirmation; evaluation_date_and_timezone; verified_sender_recipient_identity_and_addresses; representative_authority_if_used; document_place_and_date; source_bytes_hashes_and_retention; accepted_extraction_and_evidence; confirmed_facts_with_acceptance; issues_claims_requests_arguments_and_position; legal_sources_rules_citations_and_applicability; explicit_procedural_coverage_even_for_pre_litigation; accepted_snapshot_id_hash; approved_plan_ref_hash; prompt_model_provider_generator_parameter_pins; validation_policy_pin; render_profile_pin; attachment_inventory_and_signature_party.

Każda data i kwota pochodzi z potwierdzonego faktu/źródła lub jawnie oznaczonej ludzkiej deklaracji odpowiedniej do tego pola. Kwoty w decimal string, nie binary float. Nieznane obowiązkowe dane blokują, zamiast trafiać do pisma jako wymyślone wartości. Pełne adresy, data/miejsce, odbiorca, umocowanie i podpisująca strona muszą mieć jawny kontrakt wejścia i odbioru; obecny SemanticDocument nie stanowi samodzielnego schematu wszystkich tych danych.

TXT UTF-8 jest minimalnym formatem pozytywnego materiału i literalnych cytatów (RECORD 1/BYTE_RANGE). DOCX/email/text PDF wymagają świadomego rozstrzygnięcia kompletności ekstrakcji, a nie milczącej promocji PARTIAL_EXTRACTION. Obraz/skan z NEEDS_OCR blokuje zależną ścieżkę. Nie wymagamy OCR do pierwszego katalogu.

Brak procedural rules pozostaje UNKNOWN. Dla pisma przedprocesowego HUMAN i przypięty ruleset muszą wykazać pokrycie i zakres zastosowania — nie dodajemy pustej reguły „wszystko PASS” ani automatycznego N/A. Manualnie wskazana data odpowiedzi nie jest dowodem terminu ustawowego.

Nie tworzymy dodatkowych trybów QUICK/FORENSIC. Jeden baseline ma pełną obowiązkową ścieżkę kontroli. Piny profilu/promptu/modelu muszą zostać ustanowione i odebrane w późniejszym pakiecie katalogu; fixture QUICK z testów Stage 09/10 jest syntetyczna i nie certyfikuje profilu produktu.

## 3. Wszystkie HUMAN gates

| ID | Bramka | Wiązanie i DoD |
|---|---|---|
| HG-01 | Tożsamość, umocowanie i zakres sprawy | Exact Party revisions, source evidence and scope; current IDENTITY decisions. |
| HG-02 | Materiał, fakty i dowody | Accepted extraction/evidence; current FACT_ACCEPTANCE on exact Fact revisions; disputed facts cannot become confirmed silently. |
| HG-03 | Prawo, procedura i interpretacja | Verified sources and ACTIVE exact rules; HUMAN INTERPRETATION where required; jurisdiction/date/applicability/coverage explicit. |
| HG-04 | Strategia, stanowisko i żądania | Explicit HUMAN STRATEGY/REQUEST_APPROVAL or equivalent versioned approval covering exact position, Request and Argument refs; NOT presently demonstrated as a complete enforced product gate. |
| HG-05 | Snapshot acceptance | Current SNAPSHOT_ACCEPTANCE of exact snapshot id/hash. |
| HG-06 | Plan approval | Current PLAN_APPROVAL on exact reviewed plan; live snapshot approval. |
| HG-07 | Semantic review | RecordValidationReview with all seven assessments, rationale, exact draft/snapshot/policy/date; AI proposal cannot replace HUMAN. |
| HG-08 | Rozstrzygnięcie findings | Conditional live FINDING_RESOLUTION; fresh validation after resolution; cannot rewrite a historical FAIL into PASS. |
| HG-09 | Final document approval | Current DOCUMENT_APPROVAL of exact draft hash, snapshot, DOCX and PDF hashes and associated authoritative validation evidence; public write is currently GATE_DENIED. |
| HG-10 | Product admission | Independent verifier binds review to candidate SHA and contract digest; distinct authorized promoter decides integration/release. No CERTIFICATION command fabrication. |

Autoryzowany HUMAN operator inicjuje operacje; host provisioning nie jest ludzką decyzją prawną. AI może jedynie zaproponować treść/review. Odwołanie, supersession albo zmiana exact input/hash unieważnia zależną skuteczność bramki. RISK_ACCEPTANCE nie usuwa wymaganego check ani ERROR/BLOCKER/CRITICAL. Strategy/request approval jest wymaganiem kontraktu; pełna egzekucja HG-04 w produkcie nie została wykazana.

Builder przygotowuje kontrakt/kod/fixture. Inny verifier odtwarza testy i ocenia exact SHA oraz zastosowanie prawne każdego typu. Jeszcze inny promoter zatwierdza integrację/wydanie. CI jest dowodem wykonania testów, nie ludzkim review ani certyfikacją. Dokument approval przez operatora sprawy nie zastępuje product admission przez niezależnego verifiera/promotera.

## 4. Final package

| Plik | Treść i verifier |
|---|---|
| final.docx | Validated editable bytes, exact render receipt and HUMAN approval. |
| final.pdf | Validated PDF bytes, same semantic content, exact render receipt and HUMAN approval. |
| document.json | Exact SemanticDocument, case/snapshot/draft/plan refs and hashes, type/version and reproduction pins. |
| validation.json | Full pre/post-render checks, runs/manifests/reviews/findings, freshness and policy pins; no caller-supplied PASS. |
| sources.json | Source identities, hashes, locators, verified legal versions/dates/applicability; original bytes accessible under scoped retention, not automatically exported. |
| evidence-map.json | Output statements -> Fact -> accepted Evidence -> extraction -> immutable Source refs/locators. |
| argument-map.json | Requests/position -> Arguments/Claims -> Facts/Evidence/LegalRules/Citations, with explicit human approvals. |
| audit.json | Verified Stage 12 AuditPackage plus references to render/approval/release/package operations. |
| release.json | Durable repository-issued FINAL ReleaseResult/ReleaseReceipt binding approval, run pins, hashes, policy and case sequence. |
| manifest.json | Versioned package manifest: SHA-256/length of the other nine members, media types, scope, release id, code SHA and contract digest. Does not hash itself; manifest digest stored separately in authoritative package receipt to avoid cycles. |

Pakiet wymaga wszystkich dziesięciu członów. Pierwsze osiem pochodzi z docs/00 §44; release.json i manifest.json konkretyzują istniejące ReleaseReceipt oraz wymóg integralności. To wymaganie produktu, nie dzisiejszy serializer.
Manifest zawiera hashe/długości pozostałych dziewięciu członów; sam siebie nie hashuje. Osobny autorytatywny package receipt przechowuje digest manifestu; release.json nie wprowadza cyklu przez hash manifestu. DoD obejmuje schema version, exact code SHA, contract digest, scope i trwały odczyt wszystkich bytes.
Oryginały źródeł pozostają pod kontrolą dostępu/retencji; sources.json to tożsamości i references. Eksport oryginałów wymaga osobnej capability. Pakiet wewnętrzny może zawierać dane sprawy, więc jego odczyt też jest scoped. Bezpośrednie pliki DOCX/PDF przed release są draft artifacts, nie FINAL.

## 5. Wymagania i Stage 03–13

Każdy wymóg ma ID, źródło, verifier i DoD. Source paths/blob SHAs są w source_index kontraktu na exact base. Impl oznacza stan komponentu na base; **nie oznacza przyjęcia całego wymogu produktu**. Wszystkie mają Planned=true i Certified=false. Walidacja dotąd to dowody komponentowe lub NOT VERIFIED, nie E2E.

| ID | Cel | Stage | Impl na base | Źródło | Wymagany verifier / acceptance | Definition of Done |
|---|---|---|---|---|---|---|
| PB-001 | Zakres typów i jurysdykcji | 03, 06, 07 | PLANNED | docs/00-baseline.md §1, §49; explicit LW-PB-01 mandate | V-CATALOGUE; T01, T03 | Wszystkie trzy typy mają versioned pins i schematy; nieobsługiwane typy/jurysdykcje odrzucone przed generacją. |
| PB-002 | Kompletność wejść i danych formalnych | 06, 08, 11 | PARTIAL | docs/00-baseline.md §22, §39 | V-INPUTS; T01, T03 | Brak dowolnego pola wspólnego/typowego blokuje; daty, kwoty, adresy, umocowanie i załączniki są source-bound lub jawnie HUMAN-attested. |
| PB-003 | Izolacja i autoryzacja | 03, 05, 06, 07, 08, 09, 10, 12 | IMPLEMENTED_COMPONENT | AGENTS.md §11; Core execution | V-AUTH-RLS; T02 | Nieautoryzowany, AI i cross-case write/read odrzucone; brak zmiany ledger/bytes. |
| PB-004 | Trwałe źródła i retencja | 03 | IMPLEMENTED_COMPONENT | Stage03 implementation | V-STORAGE; T01, T10 | Exact source bytes/hash/length dostępne; retention/hold/backup/restore i scoped export działają na supported deployment. |
| PB-005 | Ekstrakcja z jawnością niepewności | 04 | IMPLEMENTED_COMPONENT | Stage04 implementation | V-INGESTION; T01, T03 | TXT UTF-8 supported quotation route; DOCX/email/text PDF tylko przy potwierdzeniu extraction completeness; scan NEEDS_OCR blokuje. |
| PB-006 | HUMAN tożsamość/fakty/dowody | 05 | IMPLEMENTED_COMPONENT | docs/00 §26; Stage05 | V-FACTS; T01, T04 | HG-01/02 current; żadne allegation/inference/niezaakceptowane evidence nie zaspokaja fact requirement. |
| PB-007 | Rejestr i tożsamość pisma | 06 | PARTIAL | Stage06 implementation | V-REGISTRY; T01, T11 | Filing/source identities i versioned type preserved; FINAL nie oznacza SUBMITTED/ACKNOWLEDGED. |
| PB-008 | Wersjonowane prawo i applicability | 07, 09, 10 | PARTIAL | Constitution §18, §57; Stage07/09/10 | V-LEGAL-HUMAN; T01, T05 | HG-03; źródła mają jurisdiction/version/effective interval/retrieval/supersession; błędna jurysdykcja/data/interpretacja blokuje. Real PL content requires independent legal review. |
| PB-009 | Jawna procedura i terminy | 07, 10 | PARTIAL | Stage07/10 implementation | V-PROCEDURE; T01, T05 | Completeness/application nawet dla pisma przedprocesowego; missing rules = UNKNOWN; brak business calendar lub trigger blokuje; ręczna data nie jest automatycznym ustawowym terminem. |
| PB-010 | Stanowisko, żądania i argumenty | 08, 09, 10 | PARTIAL | docs/00 §26, §46 | V-POSITION; T01, T04 | HG-04 current; każda pozycja/Request/Argument mapped i HUMAN-approved; zmiana unieważnia dalsze decyzje. |
| PB-011 | Accepted snapshot | 08 | IMPLEMENTED_COMPONENT | Stage08 implementation | V-SNAPSHOT; T01, T06 | HG-05 exact id/hash and current refs; changed inputs/revocation/supersession block. |
| PB-012 | Approved plan i safe sections | 08 | IMPLEMENTED_COMPONENT | Stage08 implementation | V-PLAN; T01, T06 | HG-06 exact reviewed plan; Section allowlist, required inputs, no new facts/rules; public Stage08 operations only. |
| PB-013 | Controlled drafting i reproduction | 09 | IMPLEMENTED_COMPONENT | Stage09 implementation | V-DRAFTING; T01, T04 | Provider untrusted, all statements traceable; prompt/model/generator/parameters/raw output pinned; rejected output cannot persist a trusted draft. |
| PB-014 | Pinned runtime and privacy | 13 | PARTIAL | Stage13 implementation | V-RUNTIME; T12 | Conformance fixture separately from real pinned local model; mismatch/timeout/malformed/offline fail closed; exact model-byte-use ceiling explicit; no privacy leak. |
| PB-015 | HUMAN semantic/adversarial review | 10 | IMPLEMENTED_COMPONENT | Stage10 implementation | V-REVIEW; T01, T04 | HG-07 all seven assessments exact draft/hash/snapshot/policy/date; semantic truth not asserted by machine. |
| PB-016 | Findings and all checks | 10, 11 | PARTIAL | Stage10 + REQUIRED_CHECKS | V-VALIDATION; T01, T07 | HG-08 if used; complete twelve PASS, no ERROR/BLOCKER/CRITICAL; UNKNOWN/NOT_RUN/FAIL blocks; fresh runs after remediation. |
| PB-017 | Authoritative semantic/render boundary | 10, 11 | PLANNED_PRODUCT_BOUNDARY | Stage11 implementation and code | V-TRUSTED-RENDER; T01, T08 | Public authorized host loads current trusted records/validation, derives SemanticDocument/RenderRequest, prevents caller PASS/authority injection. |
| PB-018 | Persistent DOCX/PDF and post-render evidence | 03, 11 | PARTIAL | Stage03 + Stage11 | V-RENDER-STORAGE; T01, T08, T10 | Actual exact bytes + receipt + metadata stored atomically/recoverably; validated formats, polish glyphs, contents and attachment list; render PASS repository-derived; no watermark. |
| PB-019 | Final HUMAN document approval | 10, 11 | PLANNED_PUBLIC_WRITE | RenderTarget; public Core deny | V-FINAL-APPROVAL; T01, T08, T09 | HG-09 current HUMAN approval targets exact draft/snapshot/DOCX/PDF and bound run; revocation/tamper drift blocks; public endpoint audited, CAS/replay safe. |
| PB-020 | Public release and durable FINAL receipt | 10, 11, 12 | PLANNED_PUBLIC_WRITE | evaluate_release and ReleaseReceipt | V-RELEASE; T01, T09, T10 | Authorized repository-loaded release produces immutable receipt only after all gates; FINAL eligibility distinct from Draft.status and Filing.status; legacy bypass remains denied. |
| PB-021 | Complete final package | 03, 11, 12 | PLANNED_PRODUCT_BUNDLE | docs/00 §44, §46; Stage12 | V-PACKAGE; T01, T08, T10, T11 | All ten members schema/version/hash/length bound; maps resolve; read after restart; package not FINAL on missing/corrupt member. |
| PB-022 | Audit/provenance and recoverability | 03, 12 | PARTIAL | Stage12 implementation; Constitution §17 | V-AUDIT; T01, T10, T11 | Audit hash chain + domain/object/command pins cover accepted inputs through package; privacy-preserving; verified read-only audit not mistaken for a full bundle. |
| PB-023 | Replay, CAS and failure atomicity | 03, 05, 06, 07, 08, 09, 10, 12 | PARTIAL | Core/Postgres; Constitution §13/14 | V-TRANSACTIONS; T09, T10 | Public render/approval/release/package and existing stages have actor-bound replay, exact CAS, conflict/no partial FINAL, concurrent stale/race/restart coverage on real PG. |
| PB-024 | Independent product admission | 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13 | PLANNED | AGENTS §20/21; Constitution §7/28/42 | V-INDEPENDENT; T13 | HG-10 distinct builder/verifier/promoter; clean exact candidate SHA CI zero skip and independent technical + legal/type review; promoter approval recorded; no Stage14/ROS dependency. |

Mapowanie komponentów: Stage03 storage, Stage04 ingestion, Stage05 facts/evidence, Stage06 filing registry, Stage07 procedure, Stage08 planner, Stage09 controlled drafting, Stage10 validation, Stage11 pure rendering, Stage12 audit/provenance, Stage13 local runtime. Nie reinterpretujemy historycznej numeracji architektury jako dowodu implementacji.

## 6. E2E acceptance contract

Test T01 uruchamia się **dla każdego z trzech typów** z własnym syntetycznym materiałem, wymaganiami i oczekiwanym tekstem/żądaniami. Kwoty/datę/stanowisko fixture wybiera test, nigdy LLM. Przykładowy zestaw: potwierdzona umowa i rozliczenie 100,00 PLN; udokumentowana wada usługi i HUMAN żądanie; wezwanie 100,00 PLN z HUMAN wskazaniem części przyznanej/kwestionowanej. To techniczne fixture, nie rzeczywiste podstawy prawne. Nie zastępuje źródeł PL i osobnego legal/type review.

Sekwencja wymagana, z zachowaniem authenticated session, scope, expected_case_sequence, actor-bound idempotency i exact hashes:

1. Core execute(CreateCase) dla scope/retencji PL; zweryfikowane strony i HG-01.
2. Core execute(RegisterSource) przy storage=True; Stage03 bytes/hash/length; Stage04 IngestionService.ingest/read.
3. Stage05 ReviewCandidate i evidence/fact lifecycle przez FactEvidenceService; HG-02; odczyt macierzy. Wykluczone legacy bypassy nie należą do product profile.
4. Stage06 Filing + versioned type, Issue/Claim/Request/Argument i żądania; explicit HG-04; Stage07 verified sources/rules, HG-03 i AssessProcedure. Stare Core nie udostępnia wszystkich potrzebnych zapisów tych encji — brak adaptera jest gapem, nie zgodą na private append.
5. Core CreateSnapshot, RecordDecision(SNAPSHOT_ACCEPTANCE), AcceptSnapshot; HG-05 exact id/hash.
6. Stage08 PlanDocument, ReviewDocumentPlan, RecordDecision(PLAN_APPROVAL), ApproveDocumentPlan; HG-06.
7. Stage09 ControlledDraftingService.generate: przyjęty structured output + provenance/reproduction; zero dowolnych nowych faktów/prawa.
8. Stage10 RecordValidationReview, ValidateDraft, GetValidation; HG-07/08; eligible_for_approval/current; render pozostaje NOT_RUN.
9. **Planowana publiczna granica zaufanego renderingu** ładuje current canonical records i ValidationProjection, buduje SemanticDocument/RenderRequest, wywołuje istniejący RenderingEngine, zapisuje rzeczywiste DOCX/PDF/receipt, uzyskuje post-render check evidence. Nie wymyślamy w PB01 nowego endpoint name/URN.
10. **Planowana publiczna final approval** zapisuje HG-09 exact bytes/draft/snapshot/validation binding. Obecny Core RecordDecision(DOCUMENT_APPROVAL) odmawia.
11. **Planowany publiczny release** z autorytatywnie pobranych danych wylicza eligibility i utrwala receipt. Obecny Core RequestRelease odmawia. FINAL nie oznacza wysłania.
12. Stage12 AuditService.package/trace i **planowany final package assembler/read**; dziesięć członów, manifest, pełne mapy; restart/read/backup verification. Product admission HG-10 dopiero po niezależnym exact-SHA review.

Zakaz przejścia przez tx.append/SQL/model_copy w kroku domenowym odbioru. Trusted repository ports służą implementacji serwisu, a nie fixture „udającej” publiczny happy path. Tak samo samodzielne evaluate_release nie jest endpointem, a budowa ValidationProjection w tests/stage11_render_fixture.py nie jest pełnym E2E. Identity provisioning i migracje należą do zaufanego setup hosta, nie do obchodzenia domenowych bramek.

| ID | Scenariusz | Procedura | Oczekiwany wynik | Stan na base |
|---|---|---|---|---|
| T01 | CreateCase → complete final package for each of the 3 supported types | All common/type inputs, scoped HUMAN, approved facts/evidence/legal coverage; use public Stage03–13 boundaries; reach snapshot/plan/draft/review/validation, trusted render, final approval, RequestRelease, audit+package read. | FINAL + ten durable members; twelve PASS; HG01–09 current; no fabrication; restart read identical hashes. | BLOCKED |
| T02 | Unauthorized / AI / cross-tenant or case | Replace principal/token/scope at every public step. | FORBIDDEN/CROSS_CASE or equivalent safe typed denial; no state/bytes leak or write. | PARTIAL_COMPONENT |
| T03 | Unsupported type/jurisdiction; missing formal input; scan/partial extraction | Each excluded case; remove each required input; include NEEDS_OCR and incomplete extraction. | Blocked before dependent generation/release; precise missing dependency; never fabricated default. | PLANNED |
| T04 | Unaccepted fact/evidence; unsupported prose; position drift; no semantic HUMAN review | Change/revoke exact input approvals, provider assertion, strategy/request or any of seven reviews. | Reject or GENERATED with blocking findings; never validated/FINAL. | PARTIAL_COMPONENT |
| T05 | Wrong/expired authority; missing procedure coverage; unknown deadlines | Change jurisdiction/effective period/interpretation/calendar/trigger; no actual applicable rules. | UNKNOWN/ABSTAIN/FAIL blocks; human PASS cannot manufacture quotation/coverage. | PARTIAL_COMPONENT |
| T06 | Snapshot/plan/source/policy drift | Revoke acceptance/plan approval or change source/current revisions/profile/policy before and during next step. | STALE/GATE_DENIED/CONFLICT; rebuild dependent evidence; historical bytes unchanged. | PARTIAL_COMPONENT |
| T07 | Finding resolution or omitted render/check coverage | Every outcome FAIL/UNKNOWN/NOT_RUN; missing/duplicate checks; critical findings; resolve without fresh run. | No FINAL; resolution not historical PASS; render NOT_RUN after Stage10 explicitly reported. | PARTIAL_COMPONENT |
| T08 | Forged render authority; DOCX/PDF/receipt tamper; missing package member | Supply caller records/projection/PASS/hash; swap bytes/approval/one member after render. | Reject; trusted state only; no FINAL or partial downloadable FINAL. | BLOCKED |
| T09 | DOCUMENT_APPROVAL / RequestRelease current denial; future revocation/race/replay | At current base valid open case + authorized HUMAN; call real Core execute. Future: exact validated/rendered persistent case, concurrent approval/release, idempotency actor conflict. | CURRENT: GATE_DENIED with unchanged ledger (real PG verifier required). FUTURE: authorized FINAL or safe refusal; no fake receipt. | CURRENT_DENIAL_LOCAL_ONLY |
| T10 | Rollback, restart, retention, backup/restore and corrupted storage | Failure at render/persist/approval/release/package commit; restart/revoke; read deleted/corrupt bytes. | No partial FINAL; recover safely; byte/hash identity exact; denial without inconsistent audit/outbox. | BLOCKED |
| T11 | Provenance and registry/export semantics | Resolve every map and audit pin; wrong permissions; FINAL vs SUBMITTED. | Complete scope-bound provenance; no original-source export without capability; no fictional submission or signature. | BLOCKED |
| T12 | Model runtime acceptance | Deterministic conformance separately; then real local pinned Ollama/prompt for each type; mismatch/outage/invalid output/network attempt. | Never transfer fixture PASS to real model; receipt version/pins valid; legal semantic content HUMAN-approved. | NOT_VERIFIED |
| T13 | Independent verification and promotion | Different verifier checks exact candidate SHA, source diff, actual PG integration/E2E logs and package bytes; distinct promoter. | Technical + per-type legal review recorded; no skipped gate; explicit promotion authorization; certification then only within frozen scope. | NOT_VERIFIED |

Verifier każdej pozycji: niezależny verifier techniczny z PostgreSQL dla zapisów i osobny HUMAN legal/domain reviewer dla zastosowania typów. DoD: wynik uzyskany bezpośrednim wykonaniem, z exact SHA i hashes inputs/policy/artifacts, bez SKIP/UNKNOWN jako PASS. Dokładne pola są w acceptance JSON.

## 7. Dowód obecnego braku publicznej ścieżki FINAL

Na exact base w core/service.py _apply:
- GenerateDocument/ValidateDraft/RequestRelease na legacy Core zawsze rzucają GATE_DENIED.
- RecordDecision dla DOCUMENT_APPROVAL i CERTIFICATION zawsze rzuca GATE_DENIED po sprawdzeniu HUMAN/metadata.
- Stage10 ma własny publiczny ValidateDraft, lecz kończy na pre-render eligible_for_approval, render NOT_RUN i pustych render_hashes.
- RenderingEngine jest czystym rendererem, przyjmującym records/validation od hosta, bez autoryzowanego zapisu domenowego.
- evaluate_release jest czystym evaluatorem; AST inventory nie znajduje jego call site w produkcyjnym Pythonie. Istnienie return FINAL w czystym evaluatorze nie upoważnia Core RequestRelease; testy PB01 nie fabrykują dla niego pozytywnego ValidationRun/Approval.
- ReleaseReceipt opisuje brak publicznego persistence/auth endpoint. AuditService jest read-only projekcją ledger, nie assembleriem wszystkich dziesięciu plików.

Wnioski ograniczone do wersjonowanego repo na base; nie twierdzimy nic o nieobejrzanym zewnętrznym deployment. Pinned source verification + dynamic Core/auth/request tests + wymagany test PostgreSQL wykazują blokadę, zamiast zakładać działający FINAL.

Testy portable tworzą Case przez real CommandService.execute, używają prawdziwego parsera/TokenAuthority i jawnie test-only MemoryRepository. Odtwarzają dwie odmowy dla scoped HUMAN, brak obejścia caller PASS i brak legacy authority. Brak zapisów dotyczy tego portu pamięciowego; nie dowodzi SQL rollback/RLS/durability.
Osobne PostgreSQLGateTests odtwarzają odmowy i porównują wszystkie scoped tabele; drugi scenariusz dociera do rzeczywistego Stage10 VALIDATED. Jego upstream fixture ma privileged legal-authority setup, więc nawet PASS nie certyfikuje supported-letter public E2E. Pełny T01 pozostaje BLOCKED.

## 8. Komendy verifiera

```bash
python -B -X utf8 scripts/verify_product_baseline.py --portable --output build/pb01/portable
python -B -X utf8 scripts/verify_product_baseline.py --output build/pb01/full
python -B -X utf8 scripts/verify_product_baseline.py --product-e2e --output build/pb01/product-e2e
```

Portable exit 0 oznacza tylko PASS_LIMITED. Default bez PostgreSQL testów z oboma isolated DSNs zwraca BLOCKED/exit 1; SKIP nie jest PASS. Product-e2e na obecnym base zawsze zwraca BLOCKED/exit 1, ponieważ adapterów finalizacji nie implementujemy w PB01. To jawny brak implementacji pełnego test drivera, nie wykonany pełny happy path. Matrix/spec i current-denial probes są gotowe do dalszego wykonania; driver publicznego happy path powstanie dopiero wraz z brakującymi granicami w późniejszych pakietach.

Exact Git blob SHA weryfikowany jest z HEAD. Treść checkoutu porównuje się według istniejącego profilu source identity CRLF→LF; canonical source/contract hashes i dodatkowe raw file hashes są zapisane oddzielnie. Normalizacja dotyczy wyłącznie tekstowych plików źródłowych kontraktu/testów, nigdy rzeczywistych bytes DOCX/PDF/source artifacts.

Przy configured disposable PostgreSQL (runtime NOSUPERUSER/NOBYPASSRLS, nie właściciel tabel), uruchomić existing scripts/prepare_ci_database.py oraz testy PostgreSQLGateTests. Nigdy nie podawać realnej produkcyjnej bazy. Istniejące verify_stage13.py uruchamia także nowy moduł przez unittest discover i wymaga zero skip. CI evidence musi dotyczyć exact candidate SHA; PASS starego main nie przenosi się na nowy branch.

## 9. Dokładny handoff do przyszłego LW-PB-02

Wejście: zaakceptowany po niezależnym review kontrakt v1 i jego SHA-256; exact nowy base/candidate SHA po ponownej live weryfikacji; wymagania PB-017–PB-023; istniejące Core/Postgres, Stage03 storage, Stage08/09 exact derived data, Stage10 ValidationProjection i policy, Stage11 renderer/profile/receipt, Stage12 AuditService i ReleaseResult/Receipt/RenderTarget.
Pierwszy pionowy wycinek może używać syntetycznego przypiętego typu; nie nadaje mu wsparcia prawnego ani nie zastępuje LW-PB-03.

Wyłącznie przyszły zakres PB02:
- zaufana publiczna granica derive semantic → render → persist exact bytes/receipt/metadata;
- server-side post-render evidence i jawne rozwiązanie lifecycle/run rebind, z wersjonowaniem i compatibility tests;
- HUMAN DOCUMENT_APPROVAL i current exact render/run binding;
- authenticated RequestRelease z trwałym receipt, CAS/idempotency/audit/outbox i fail-closed;
- scoped odczyt trwałych render artifacts i release receipt; wiązanie istniejącego Stage12 audit; pełny assembler sources/evidence/argument maps pozostaje późniejszym pakietem integracyjnym;
- real PostgreSQL tests: stale/revoked approvals, scope/auth, forged caller PASS, sources/policy drift, tamper/missing bytes, concurrent CAS/race, replay actor conflict, rollback i restart.

Nie jest wejściem do PB02: Stage14/ROS, OCR, szeroki katalog, realne reguły PL/prompt registry i legal certification (PB03), UI/login/deployment czy zewnętrzna wysyłka. Pełny final package assembler i type/profile/domain sources muszą być później oddzielnie odebrane. Nie wolno wyłączyć obecnych odmów bez zamknięcia równoważnej zaufanej granicy. Builder PB01 nie jest verifierem ani promoterem PB02.

## 10. Formalny kontrakt każdego typu

Poniższe pola mają osobne requirement ID w katalogu JSON, źródło, support, implementation mapping, verifier, test i DoD. Całe typy pozostają NOT SUPPORTED / FUTURE. Role: PL-PRE-PAYMENT-1: wierzyciel/nadawca → dłużnik/adresat; PL-PRE-COMPLAINT-1: strona składająca reklamację → druga strona umowy; PL-PRE-REPLY-1: adresat pierwotnego wezwania/nadawca odpowiedzi → nadawca pierwotnego wezwania/adresat odpowiedzi. Organ publiczny poza baseline.

| Sufiks requirement ID (dla każdego document_type_id) | Warunek | Obecne mapping | Verifier |
|---|---|---|---|
| .document_type_id | Planowany id z katalogu; pin wersji i treści wymagany przed wsparciem typu. | Type pin/schema absent | V-CATALOGUE; T01/T03 |
| .recipient_organ | Zweryfikowana prywatna strona umowy/wezwania, adres doręczeń; organ publiczny poza zakresem. | Party refs exist; formal recipient/address type contract absent | V-INPUTS; T01/T03 |
| .parties_roles | Nadawca, adresat, role względem umowy/roszczenia i podpisująca strona, exact Party revisions. | Generic Party/SemanticDocument; per-type role binding absent | V-FACTS; T01/T03 |
| .place_date | Miejscowość pisma, data ISO, evaluation date/timezone; jawne źródło/deklaracja HUMAN. | No dedicated complete formal semantic envelope | V-INPUTS; T01/T03 |
| .case_reference_signature | Wewnętrzny case_id obowiązkowy; numer umowy/korespondencji z exact source, jeśli istnieje; brak zewnętrznej sygnatury jawny, bez wymyślania. | Generic Case/Filing; per-type reference presentation absent | V-INPUTS; T01/T03 |
| .title | Deterministyczny tytuł właściwego typu, bez dopisywania nowej kwalifikacji prawnej. | SemanticDocument.header generic; type heading profile absent | V-CATALOGUE; T01/T03 |
| .requests_demands | HUMAN-approved żądania/stanowisko, powiązane z Request refs i dowodami; zakres kwot/daty jawny. | Request/plan exist; full strategy/request product enforcement partial | V-POSITION; T01/T03 |
| .reasoning | Uzasadnienie z zaakceptowanych facts/arguments/rules; żadnych nowych twierdzeń modelu. | Sections/drafting guards exist; per-type profile absent | V-DRAFTING; T01/T03 |
| .facts | Exact CONFIRMED SOURCE_BACKED Facts i bieżące akceptacje; timeline tylko source-bound daty, brak automatycznej prawdziwości. | Fact lifecycle implemented; type-specific required facts absent | V-FACTS; T01/T03 |
| .evidence | ACCEPTED Evidence, extraction completeness i dostępne oryginalne bytes/locators. | Component implemented; full type path not accepted | V-INGESTION; T01/T03 |
| .legal_authorities | Verified PL sources, wersje/okres/datowanie/applicability i exact aktywne reguły/citations; ocena HUMAN, bez nieprzypiętych przepisów. | Synthetic authority enforcement; real supported type rules/content not certified | V-LEGAL-HUMAN; T01/T03 |
| .attachments | Jawny spis z numerami, opisem i exact source/artifact identities; bytes dostępne w scoped storage; pusty spis tylko jawnie zatwierdzony. | Renderer list exists; public attachment/package binding incomplete | V-PACKAGE; T01/T03 |
| .signature_requirements | Zweryfikowana podpisująca strona/imienne miejsce na podpis; podpis ręczny poza generatorem. Bez automatycznej grafiki podpisu i deklaracji e-signature. | SemanticDocument.signature_party only; full type attestation absent | V-FINAL-APPROVAL; T01/T03 |
| .representation_power | Jeśli reprezentant: explicit scope, accepted power evidence, exact principal/representative refs; jeśli nie: jawnie personal action. | Representation controls not demonstrated per type | V-LEGAL-HUMAN; T01/T03 |
| .render_requirements | OFFICIAL_PL_V1 DOCX/PDF, polskie znaki, zgodność semantyki/paginacji/załączników, bez watermark; actual durable bytes/receipt/hashes. | Pure Stage11 renderer implemented; authoritative persisted route missing | V-RENDER-STORAGE; T01/T03 |
| .final_approval_requirements | Current HUMAN DOCUMENT_APPROVAL, exact draft/snapshot/DOCX+PDF and validation binding, durable receipt/audit; bez tego nie FINAL. | Public Core GATE_DENIED | V-FINAL-APPROVAL; T01/T03 |

Źródła: pole source każdego child requirement + pinned domain/models.py, contracts/messages.py i docs/00 na exact base. Child ID to np. PL-PRE-PAYMENT-1.recipient_organ. DoD wymaga publicznego testu konkretnego typu, źródłowych danych, negative missing/invalid test i independent legal/type review. Żadne optional sygnatura/załącznik/reprezentant nie jest cichym domyślnym faktem.

## 11. Koperty każdego kroku E2E

Każda pozycja ma osobno input, preconditions, authority, state_transition, output, evidence i negative_cases w full_path_steps kontraktu; nie jest symulowanym execution log. Wymagany verifier: niezależny techniczny na exact SHA i prawdziwym PG dla zapisów; HUMAN legal/type reviewer dla applicability/treści. DoD każdego kroku = bezpośrednio zaobserwowane warunki/wyniki przez publiczny boundary i negatywne odmowy, bez fabricated authority.

| ID / krok | Input / preconditions | Authority / transition | Output / evidence | Negative cases | Stan |
|---|---|---|---|---|---|
| S01 CreateCase | scope ids; jurisdiction PL; title; retention pin / authenticated HUMAN capability; expected sequence 0 | Core.execute(CreateCase), HUMAN; none → OPEN Case / sequence+1 | CommandResult; Case ref; audit/outbox; case revision hash; event/command IDs | invalid token; AI; duplicate different payload; cross-case | IMPLEMENTED |
| S02 Intake and supported-type inputs | catalogue id; all common/type/formal inputs; incoming refs / supported scope; identity/power evidence available | HUMAN HG01/04; planned product intake boundary; unknown input → explicitly complete supported envelope | type/role/formal input envelope; type schema/profile pins; HUMAN attestations | unknown type; foreign scope; missing address/date/power; unsupported defaults | MISSING_PRODUCT_BOUNDARY |
| S03 Documents and ingestion | original bytes; media type; retention pin; run id / storage=True; scoped RegisterSource/IngestSource/ReadIngestion | Core.RegisterSource; IngestionService.ingest/read; source registered → immutable extraction/candidates | SourceDocument; IngestionResult; stored originals/raw output; source hash/length; extractor pin; locators/result hash | tampered bytes; NEEDS_OCR; PARTIAL ignored; run/source mismatch | IMPLEMENTED_COMPONENT |
| S04 Facts/evidence and timeline review | candidate refs; result hashes; HUMAN statements; accepted evidence; event dates / HG01; complete extraction or explicit valid evidence route | FactEvidenceService + Core.RecordDecision; HUMAN HG02; candidate → REVIEWED/CONFIRMED Fact; ACCEPTED Evidence | canonical refs; fact/evidence matrix; review receipts; acceptance decisions; source→extraction→evidence→fact binding | unsupported inference; revoked acceptance; disputed evidence; recorded_at as event date | IMPLEMENTED_COMPONENT_TIMELINE_PARTIAL |
| S05 Legal/procedural scope and position | verified PL source versions/dates; rules/citations; Issue/Claim/Request/Argument; position / source applicability verified; complete rule coverage; HG03/04 | ProceduralEngineService + authorized domain writes; HUMAN; source/rule PROPOSED→VERIFIED/ACTIVE; approved position | AssessProcedure; exact rule/argument/request refs; INTERPRETATION/strategy approvals; coverage and source pins | expired/wrong jurisdiction; missing rules; unknown trigger; no legal authority; unsupported domain write | PARTIAL_REAL_CATALOGUE_AND_WRITES_MISSING |
| S06 Snapshot acceptance and planning | case heads; Filing/type; objectives/arguments; safe section blueprints / current HG01–04; all semantic refs canonical | Core.CreateSnapshot/AcceptSnapshot; Planner Stage08; HUMAN HG05/06; snapshot frozen/accepted; plan PROPOSED→REVIEWED→APPROVED | snapshot id/hash; plan/sections refs; SNAPSHOT_ACCEPTANCE; PLAN_APPROVAL; dependencies | post-snapshot ref injection; revocation/supersession; unsafe sections; stale heads | IMPLEMENTED_COMPONENT |
| S07 Controlled drafting | approved exact plan/snapshot; pinned provider/model/prompt/generator/parameters / HG05/06 current; provider receipt matches; no unsupported input | ControlledDraftingService.generate; HUMAN authorized invocation; AI proposal only; approved plan → GENERATED Draft | draft sections/statements; reproduction manifest; raw output trace; actual invocation/result hashes; Statement refs/citations | new facts/rules; malformed output; provider pin mismatch; timeout; unsupported assertions | IMPLEMENTED_COMPONENT_PROFILES_PARTIAL |
| S08 Pre-render validation | current GENERATED Draft/hash; snapshot hash; policy pin; HG07 review/context / current input/plan/snapshot/legal authority; all seven HUMAN assessments | ValidationEngineService; HUMAN HG07/08; GENERATED → VALIDATED only if pre-render PASS; render remains NOT_RUN | ValidationProjection; run/manifest/findings; derived draft revision; twelve-check universe with explicit render NOT_RUN; review/run dependency hashes | missing HUMAN review; FAIL/UNKNOWN/NOT_RUN; unresolved blockers; stale quotation/source; finding waiver | IMPLEMENTED_PRE_RENDER_ONLY |
| S09 Render | server-loaded exact current records/ValidationProjection; semantic/profile binding / eligible_for_approval CURRENT; no caller supplied PASS/authority | Planned authenticated trusted boundary → existing pure RenderingEngine; VALIDATED input → validated in-memory DOCX/PDF bundle; domain lifecycle unresolved | DOCX/PDF bytes; RenderReceipt/meta/layout; artifact hashes; renderer/font/profile/validation bindings | forged projection; semantic drift; stale policy; unsupported visual content; bad glyph/format | MISSING_PUBLIC_BOUNDARY_PURE_RENDERER_EXISTS |
| S10 Artifact persistence and post-render validation | actual bundle bytes; receipt/meta; validation evidence / atomic/recoverable authorized storage; scoped identity; valid hashes/lengths | Planned trusted application service; repository runtime role; in-memory artifacts → durable render; explicit versioned lifecycle/run rebind required | durable artifact IDs; post-render PASS evidence; exact rendered draft identity; stored bytes reread hashes; transaction/audit/outbox; fresh runs | partial save; tamper/missing bytes; wrong case; caller PASS; restart | MISSING |
| S11 HUMAN final approval | exact stored DOCX/PDF; draft/snapshot hashes; current validation bindings / all required checks PASS; no blockers; HG01–08 current | HUMAN HG09; planned public approval endpoint; current Core denies; no final approval → current recorded exact approval (FUTURE) | Decision/ref/hash; bound RenderTarget; actor/time; exact byte/run bindings; audit event | AI approval; wrong/stale hashes; revocation; source drift; not rendered | GATE_DENIED_CURRENT |
| S12 RequestRelease | release intent; scope/CAS/idempotency; exact authoritative approval/render/run ids / twelve PASS; CURRENT inputs/approval; no ERROR/BLOCKER/CRITICAL; durable bytes | Planned authenticated repository-loaded release boundary; current Core denies; DRAFT eligibility → FINAL only after trusted successful persistence (FUTURE) | ReleaseResult; durable release receipt identity; exact approval/run/policy/sequence/artifact hashes | caller fabricated PASS/receipt; race; stale approvals; cross-case; missing check/artifact | GATE_DENIED_CURRENT |
| S13 Final release receipt and recovery read | repository-issued release identity; scope/read capability / successfully committed release; no partial package/FINAL | Planned scoped read; distinct promoter only for product integration; committed release → stable read/replay; not SUBMITTED | same immutable receipt and artifact identities; restart/replay equality; failure/rollback evidence | lost receipt; different actor replay; corrupted byte; revoked token; ambiguous commit | MISSING |
| S14 Audit and full final package | release id; all canonical outputs/source/argument maps; Stage12 audit / all ten members exist; hash/schema/scope valid; source export permission explicit | AuditService.package/trace plus planned scoped final assembler/read; FINAL receipt → complete package; admission HG10 separately | ten members; manifest; package identity/digest; map resolution; audit/event/command/object pins; package hashes/version/code SHA/contract digest | missing member; hash mismatch; untraceable argument; data leak; false submission/e-signature | AUDIT_IMPLEMENTED_FULL_PACKAGE_MISSING |

## 12. Component state i ograniczenia

IMPLEMENTED = komponent istnieje. VALIDATED = tylko wskazane testy komponentowe, nie całe pismo. PARTIAL = część wymogu/ścieżki istnieje. MISSING = wymagana granica nie istnieje. NOT IN BASELINE = jawnie wyłączone. Certified nie jest nadawane.

| Komponent | Implementation mapping | Stan | Evidence ceiling / validation | Ograniczenie |
|---|---|---|---|---|
| Case Core | lukart_work/core/service.py | IMPLEMENTED | Existing main CI component evidence; new candidate pending | Public FINAL operations denied |
| Storage Stage03 | lukart_work/storage/objects.py | IMPLEMENTED | Existing scoped storage tests | Trusted persistence of render/package missing |
| Ingestion Stage04 | lukart_work/ingestion/service.py | IMPLEMENTED | Synthetic adapter tests | Scans NOT IN BASELINE; DOCX/email/PDF extraction partial |
| Facts/Evidence Stage05 | lukart_work/facts/service.py | IMPLEMENTED | Existing human lifecycle tests | No legal truth certification |
| Timeline | lukart_work/domain/models.py Fact.event_date | PARTIAL | Source-bound field/lifecycle evidence | No dedicated complete Timeline service; advanced automation NOT IN BASELINE |
| Registry Stage06 | lukart_work/registry/service.py | IMPLEMENTED | Existing identity/submission receipt tests | Type catalogue/product controls partial; external filing NOT IN BASELINE |
| Procedure Stage07 | lukart_work/procedural/service.py | PARTIAL | Implemented engine validated on synthetic rules | Real PL rule catalogue/coverage MISSING; business calendar NOT IN BASELINE |
| Planner Stage08 | lukart_work/planner/service.py | IMPLEMENTED | Existing snapshot/safe section/current approval tests | Supported-type profiles MISSING |
| Drafting Stage09 | lukart_work/drafting/service.py | IMPLEMENTED | Synthetic provider/replay/authority guard tests | Real per-type legal output NOT VERIFIED |
| Model/provider/prompt Stage09/13 | lukart_work/model_runtime/ollama.py | PARTIAL | Adapter conformance/failure tests | Type prompts/live runtime acceptance MISSING; atomic model-byte-use attestation incomplete |
| Validation Stage10 | lukart_work/validation/service.py | IMPLEMENTED | Existing structured + HUMAN semantic review tests | Pre-render only; post-render persistence/binding MISSING |
| Rendering Stage11 | lukart_work/rendering/service.py | PARTIAL | Pure DOCX/PDF renderer tests | Trusted public semantic assembly and persisted render MISSING |
| Audit Stage12 | lukart_work/audit/service.py | IMPLEMENTED | Read-only ledger projection/trace tests | Full final-package assembly MISSING |
| Release/finalization | lukart_work/validation/rules.py evaluate_release | MISSING | Pure evaluator guards only; dynamic public denials | No authorized public durable FINAL endpoint |
| Advanced knowledge/autonomous adversarial | docs/00-baseline.md roadmap | NOT IN BASELINE | NOT VERIFIED | HUMAN semantic/adversarial/legal controls mandatory instead |

Dodatkowy PB-025 (chronologia): PARTIAL, Stage05/06/07/08; source docs/00 §22/49 oraz Fact.event_date/Filing dates; verifier V-TIMELINE, T01/T04/T05. DoD: HUMAN akceptuje source-bound dates/rozbieżności; received_at/recorded_at nie zastępują dat zdarzeń. Automatyczny Timeline engine nie jest obietnicą baseline.

Windows ingestion nie zapewnia limitu pamięci parsera jak Linux; hosting isolation jest zależnością późniejszego admission, nie zadaniem PB01. DOCX headers/footnotes/drawings i PDF wizualna kolejność/pokrycie obrazów nie są dowiedzione. Render profilu ma własną prostą paginację; nie obiecujemy arbitrary custom source layouts. Stage13 pre/post model digest observation nie jest atomic proof użytych bytes. Wszystkie te granice pozostają jawne; PB01 ich nie naprawia.
