# 01 — Domain Model & Contracts

Wersja pakietu: 0.1.0. Wersja kontraktów: 1.0.0. Data: 2026-09-14.
Baseline: pełny dokument `00-baseline.md`, sekcje 1–54. Status prac: DESIGNED + IMPLEMENTED (kontrakty i wybrane walidatory), lokalnie EXECUTED/VALIDATED w zakresie raportu. Nie jest to certyfikacja produktu ani zakończony Case Core.

## Executive Summary

Model zawiera wszystkie 23 encje Architektury 00. Case pozostaje kanoniczną granicą sprawy. Dane są izolowane przez tenant_id i case_id, referencje wskazują typ, UUID i rewizję, a każda rewizja ma provenance i łańcuch hashy. Nie ma zależności od UI, formatów dokumentu, SDK modeli ani integracji ROS. JSON Schema jest eksportem jawnych typowanych kontraktów Python. Walidacja semantyczna jest osobną warstwą; poprawny JSON nie oznacza prawdziwego twierdzenia prawnego.

Pakiet implementuje modele, allowlisty lifecycle, kontrolę referencji i ownership, wybrane guardy zatwierdzania, closure snapshotu, propagację po DAG, walidację struktury odpowiedzi AI, sekwencyjny model idempotencji/CAS oraz czystą funkcję oceny FINAL. Nie implementuje PostgreSQL, autoryzacji produkcyjnej, weryfikacji źródeł prawa, generowania tekstu, renderowania ani certyfikacji.

## Decyzje rozwijające baseline

| ADR | Problem / skutek | Decyzja | Podstawa |
|---|---|---|---|
| 01 | FINAL nie występuje w lifecycle §16, ale jest wymagane przez §39 | lifecycle Draft zachowuje sześć statusów; ReleaseResult.eligibility = DRAFT/FINAL jest oddzielną decyzją o wydaniu konkretnych bytes | §14–16, 22, 39 |
| 02 | Utrwalone drafty muszą być immutable, lecz §42 wymaga STALE | stan treści jest historyczny; FreshnessAssessment wyliczany wobec case_sequence oznacza CURRENT/STALE/UNKNOWN; nie zmieniamy starego pliku | §28, 42–43 |
| 03 | Wspólne źródła prawa vs izolacja spraw | LegalSource jest case-local admission dokładnej wersji rejestru; identyczne bytes mogą być współdzielone pod spodem bez ujawniania innej sprawy | §8, 29, 36 |
| 04 | Cykl plan → sekcja → plan uniemożliwiałby przypięcie immutable wersji | Section należy do Filing, plan wskazuje uporządkowane wersje Section. To samo logiczne pismo może mieć kolejne plany | §11–12, 28 |
| 05 | Decision zatwierdza treść, a encja wskazuje Decision; cykl rewizji | Decision wskazuje poprzednią ocenioną rewizję; kolejna rewizja zmienia status i link akceptacji, bez zmiany treści. Snapshot obejmuje historyczne zależności i jawne heads | §26–28 |
| 06 | Jedno enum źródłowości nie rozstrzyga prawdziwości faktu | SOURCE_BACKED/INFERRED/UNSUPPORTED jest niezależne od CONFIRMED/DISPUTED; dowód twierdzenia nie jest automatycznym dowodem jego prawdziwości | §7, 13, 35 |
| 07 | CRITICAL i ERROR bez jawnej reguły wydania mogłyby przejść obok BLOCKER | ERROR, BLOCKER, CRITICAL blokują wydanie; UNKNOWN/NOT_RUN również. Ręczne RESOLVED nie usuwa wyniku negatywnego z bieżącego run | §15, 39 |
| 08 | Wszystkie dane w jednym obiekcie Case tworzą monolityczny aggregate | Case jest root kanonicznego stanu i spójności; poniższe mniejsze agregaty działają w jednej transakcji monolitu z CAS case_sequence | §4, 30–31 |
| 09 | Odtworzenie warunków LLM nie zapewnia identycznych odpowiedzi | utrwalamy wejście, surowe wyjście, wersje i parametry; replay artefaktów jest deterministyczny, ponowne generowanie LLM nie ma gwarancji bitowej identyczności | §27–28, 43 |

Żadna decyzja nie zastępuje baseline. Zaostrzenie §15 jest jawnie opisane w ADR-07. Gdyby użytkownik wymagał FINAL mimo ERROR, byłaby to zmiana baseline wymagająca osobnej decyzji. Nie wprowadzamy mikroserwisów ani event sourcingu jako warunku budowy.

## Typy wspólne i tożsamość

- `Entity`: schema_version=1.0.0, id: UUID, tenant_id: UUID, case_id: UUID, revision: integer≥1, previous_hash: SHA-256|null, created_at i recorded_at: datetime ze strefą, provenance: Provenance. Wszystkie pola są wymagane. W rev1 previous_hash=null; w następnych jest hashem poprzedniej rewizji. created_at jest stały; recorded_at nie maleje.
- UUID generuje application service, nie model AI. Rozstrzygnięcie identity nie korzysta z nazwy ani adresu. Krótkie etykiety CASE-0001/FACT-0041 są projekcją, nie kluczem. PII nie należy umieszczać w identyfikatorze.
- `Ref`: kind z zamkniętej listy 23 encji + id + revision. Brak „latest” w utrwalonych referencjach. Klucz persystencji: tenant_id, case_id, kind, id, revision. Resolver zawsze dostaje scope z uwierzytelnionego kontekstu.
- `VersionPin`: id, version, content_hash; prompt, model, provider, validator, reguły, policy i render_profile są przypinane niezależnie. Wersja semantyczna i hash pełnią różne funkcje.
- `Money`: nieujemny dziesiętny string, do czterech miejsc po przecinku, currency: trzy wielkie litery. Dopuszczalność kodu waluty i dokładność rozliczeń rozstrzyga wersjonowany rejestr; float jest zakazany. Korekta ujemna wymaga odrębnego zdarzenia/ref, nie ujemnego roszczenia.
- `TimeRange`: data początku + nullable data końca, end≥start, zakres domknięty. Następny przedział musi zaczynać się po końcu poprzedniego, chyba że są różne zakresy zastosowania. Brak end oznacza open-ended, nie potwierdzenie aktualnej mocy źródła.
- `Address`: country, niepuste lines, optional postal_code. Nie zgadujemy PESEL, adresów ani nazw. Niezweryfikowana tożsamość pozostaje UNVERIFIED.
- `SourceAnchor`: document_id, hash pełnego źródła, Locator(unit,value,fragment_hash). Locator ma PAGE/PARAGRAPH/ARTICLE/BYTE_RANGE/RECORD. Dla skanu zachowujemy obraz źródłowy oraz oddzielnie wersję ekstrakcji i jej mapę pozycji. Hash ekstrakcji nie zastępuje hasha oryginału.
- `Provenance`: actor, operation_id, method, inputs[], anchors[], rationale, optional tool pin. Puste źródła dopuszczalne dla ręcznej decyzji/metadanych, nie dla Fact. Deklaracja użytkownika to zarejestrowany SourceDocument typu tekstowego, nie niewidoczna wiadomość w czacie.
- `Assessment`: dimension, LOW/MEDIUM/HIGH/UNKNOWN, basis[], rationale. Nie reprezentuje prawdopodobieństwa wygranej.
- `null` oznacza nieustaloną lub nieprzypisaną wartość; status UNKNOWN/UNRESOLVED określa semantykę. Pusta lista znaczy brak zarejestrowanych elementów; nie dowodzi ich nieistnienia.
- Timestamps produkcyjnego adaptera: UTC; daty zdarzeń i terminów zachowują strefę biznesową i dokładność. Nie wolno zamieniać nieznanej daty dziennej na midnight UTC.

## Aggregate roots i transakcje

| Aggregate / owner | Encje | Granica |
|---|---|---|
| Case Core / Case | Case, Party, Institution | identity, scope, status sprawy, head map; odrębne rewizje dzieci |
| Procedural / Proceeding | Proceeding, Deadline | uczestnictwo i terminy; Deadline może odnosić się do pre-litigation Filing bez Proceeding |
| Evidence / Evidence | Evidence, rejestr SourceDocument | immutable source bytes i opis dowodu |
| Facts / Fact | Fact | twierdzenie, support, akceptacja; dowody tylko przez Ref |
| Legal / LegalSource, LegalRule | LegalSource, LegalRule | source admissions i zrecenzowane reguły; rejestr globalny poza Case |
| Reasoning / Issue | Issue, Claim, Defence, Argument, CounterArgument, Risk | jawne stanowiska, relacje i ich wersje |
| Documents / Filing | Filing, Request, DocumentPlan, Section, Draft, Citation | cel pisma i jego wersje; draft nie edytuje Case |
| Validation / ValidationFinding | ValidationFinding, ValidationRun | immutable wynik konkretnego uruchomienia i scope |
| Governance / Decision | Decision, AuditEvent, Snapshot | decyzje i utrwalone wejścia; brak przepisywania historii |

Agregat nie oznacza ładowania całego grafu do RAM ani serializacji wszystkich dzieci w Case. W monolicie pojedynczy unit of work sprawdza expected_case_sequence i wszystkie expected_revision, zapisuje nowe rewizje, nowy head, audyt i outbox atomowo. Duża operacja buduje proposal poza transakcją, a w transakcji wykonuje ponowną kontrolę CAS. Case sequence jest celowym prostym punktem serializacji P0; optymalizacja granularności wymaga pomiaru konfliktów.

Case CLOSED nie przyjmuje zmian treści bez reopen przez uprawnionego człowieka; ARCHIVED jest terminalny dla domeny. Retention/deletion to odrębna operacja infrastrukturalna z audit tombstone. Historyczny hash nie uzasadnia bezterminowego przechowywania danych osobowych.

## Macierz źródeł prawdy

| Encje | Rola |
|---|---|
| Case, Party, Institution, Proceeding, Filing | kanoniczne dane zarejestrowane w Case; ich status opisuje jakość, nie obiektywną prawdziwość |
| Fact, Evidence | kanoniczne twierdzenia i rejestr dowodów; oryginalny SourceDocument ma pierwszeństwo przy weryfikacji |
| LegalSource, LegalRule | case-local kanoniczne przypięcie źródła i interpretacji; norma ma własną wersję i provenance |
| Issue, Claim, Defence, Argument, CounterArgument, Request, Deadline, Risk | wersjonowane kanoniczne analizy/decyzje/propozycje; pochodzenie analityczne nie czyni ich pierwotnymi faktami |
| Decision | kanoniczny zapis decyzji i jej podstawy; nie zmienia bytes zatwierdzanej rewizji |
| DocumentPlan, Section | pochodne, kanonicznie utrwalone instrukcje dokumentu; nie są źródłem danych Case |
| Citation | pochodne wiązanie źródła, fragmentu i wspieranego elementu |
| Draft | niezmienny artefakt pochodny, z osobnym lifecycle i oceną aktualności |
| ValidationFinding | niezmienny wynik kontroli konkretnego wejścia; zmiana rozwiązania to następna rewizja |

Żadna z 23 encji nie jest wyłącznie projekcją UI. Projekcjami są Timeline, Fact–Evidence Matrix, Issue Matrix, Argument Matrix, indeksy wyszukiwania i widok grafu. Typed relations w kanonicznych polach są źródłem dla Knowledge Graph. Nie utrzymujemy niezależnego drugiego edytowalnego zbioru tych samych relacji.

Trust chain pozostaje: SourceDocument → Case Data → Legal/Procedural Knowledge → Argument Graph → Document Model → Rendered Document. DOCX/PDF nigdy nie aktualizuje Case bez nowego procesu ingestion i akceptacji.

## Invariants i guardy każdej encji

Pola, typy, required/optional i komplet przejść: `02-entity-catalog.md`. Poniżej normatywne warunki dodatkowe. Guard w kodzie jest wskazany w macierzy implementacji; brak implementacji nie znosi wymogu.

| Encja | Invariant / warunek przejścia |
|---|---|
| Case | id=case_id; owner uprawniony w tenant; archive tylko z CLOSED; reopen audytowane; retencja przypięta |
| Party | role należy do Participation, nie do osoby; VERIFIED wymaga decyzji IDENTITY o poprzedniej rewizji; zmiana tożsamości przy VERIFIED wymaga powrotu do UNVERIFIED/DISPUTED |
| Institution | VERIFIED wymaga weryfikacji rejestru/źródła; właściwość sądu nie wynika z statusu VERIFIED; brak instytucji UNKNOWN nie może zostać zastąpiony fikcyjnym sądem |
| Proceeding | institution=Institution, participants≥1; parent nie może być sobą ani tworzyć cyklu; sygnatura nie jest globalnym ID; STAYED nie oznacza automatycznego zatrzymania wszystkich terminów |
| Filing | dokładnie jeden Case; proceeding optional dla przedprocesowych; authors≥1; recipient Party/Institution; SUBMITTED wymaga daty i receipt; READY wymaga konkretnego dopuszczonego wydania przez adapter |
| Fact | SOURCE_BACKED wymaga Evidence; provenance niepuste; CONFIRMED wymaga SOURCE_BACKED i decyzji o niezmienionej poprzedniej rewizji; DISPUTED pozostaje dozwolonym materiałem tylko z oznaczeniem sporności |
| Evidence | dokładne source bytes i locator; ACCEPTED nie oznacza judicial admissibility; excluded/challenged evidence nie może po cichu wspierać bezwarunkowego twierdzenia; brak oryginału blokuje provenance |
| Issue | RESOLVED wymaga Decision; nierozstrzygnięte zagadnienie pozostaje UNRESOLVED; ponowna analiza tworzy rewizję |
| LegalSource | content_hash=registry_pin.content_hash=anchor.document_hash; zakres czasowy i jurysdykcja są jawne; SUPERSEDED nie unieważnia historycznego zastosowania; RETRACTED blokuje użycie do czasu przeglądu |
| LegalRule | sources≥1, właściwe wersje; ACTIVE wymaga review_decision; PROCEDURAL wymaga Requirement; interpretacja DISPUTED wymaga ludzkiej decyzji i oznaczenia |
| Claim | issues≥1, claimant=Party; ADOPTED wymaga STRATEGY acceptance; UNSUPPORTED blokuje przyjęcie; REMEDY amount nie zastępuje Request |
| Defence | dokładnie jeden Claim i Party; ADOPTED wymaga STRATEGY acceptance; nie nadpisuje Claim przeciwnika |
| Argument | target Claim/Defence; premises≥1; supports/opposes jawne; wszystkie przesłanki rozwiązywalne; SOURCE_BACKED nie wynika z confidence |
| CounterArgument | jeden target Argument; ANSWERED wymaga response_argument; odpowiedź nie usuwa kontrargumentu ani nie dowodzi jego obalenia |
| Request | Filing i claims≥1; APPROVED wymaga REQUEST_APPROVAL; żądanie proceduralne ma Claim typu ASSERTION, nie sztuczne roszczenie pieniężne |
| Deadline | trigger=Fact; UNKNOWN dopuszcza brak due_at; CALCULATED/VERIFIED wymagają due_at; weryfikacja ma pin reguł/kalendarza i trace; SATISFIED wymaga satisfaction; EXPIRED→SATISFIED zachowuje historię uchybienia |
| Risk | affected≥1; ACCEPTED wymaga decyzji; akceptacja ryzyka nigdy nie nadpisuje BLOCKER; zmiana źródła ponownie otwiera ocenę |
| Citation | źródło LegalSource oraz locator i supported; VERIFIED wymaga zgodności fragmentu i sensu twierdzenia; sam URL lub podobieństwo semantyczne nie wystarcza |
| DocumentPlan | objectives, section_order≥1; kolejność unikalna; Sections należą do tego samego Filing; APPROVED wymaga decyzji; zatwierdzona treść jest zamrożona |
| Section | należy do Filing; required_inputs⊆allowed_inputs; allowed_claims jawne; READY oznacza gotowy kontrakt, nie wygenerowany tekst |
| Draft | plan musi być APPROVED przed GENERATION; sekcje odpowiadają planowi; GENERATION nie implikuje VALIDATION; każde znaczące Statement ma refs/citations lub jawne inference; zmiana treści po GENERATED tworzy nowy Draft ID z supersedes |
| ValidationFinding | run_id, target i target_hash niezmienne; resolution wymaga Decision; samo oznaczenie RESOLVED/FALSE_POSITIVE nie daje FINAL bez ponownego pełnego run |
| Decision | RECORDED nieedytowalne; ACCEPT/REJECT/ABSTAIN; kluczowe decyzje HUMAN; supersedes/revoke zachowują oryginał; revocation unieważnia zależne dopuszczenia |

## Lifecycle i niezmienność

Dozwolone przejścia są zamknięte w `schemas/lifecycle.json`. Guardy są koniunkcją: schema ∧ scope ∧ references ∧ legal transition ∧ provenance ∧ state-specific preconditions ∧ authorization ∧ CAS. Zmiana statusu to nowa rewizja. Nie ma PATCH pomijającego walidację. `model_copy` służy w testach do konstrukcji wejść adversarial; adapter wejściowy musi ponownie parsować JSON, nie traktować obiektów z pamięci jako zaufanych.

Historyczne rewizje wszystkich encji są append-only. Zatwierdzony plan, wygenerowany draft i zarejestrowana decyzja zamrażają również treść logiczną; nowe teksty wymagają nowych ID (plan przez nowy plan, draft przez supersedes). Wersja snapshotu nie jest nadpisywana. Lifecycle statusu nie może kasować dowodów starszego zatwierdzenia.

Dla legal source pozostają dwa czasy: effective_period (czas obowiązywania) i retrieved_at/recorded_at (czas wiedzy systemu). Applicability zależy od daty zdarzenia i reguł intertemporalnych; pojedynczy zakres jest minimum modelu, nie silnikiem rozstrzygania prawa.

## Snapshoty i reproducibility

Snapshot ma id, scope, case_sequence, timestamp, members(ref+hash), heads, sources oraz piny knowledge/rules/policy. `members` obejmuje closure historycznych referencji; `heads` identyfikuje jeden wybrany aktualny wpis na identity. Historyczne approval links nie powodują błędnego odrzucenia kilku rewizji tej samej encji. Snapshot powinien zawierać wszystkie wybrane heads dla scope operacji oraz pełną closure; szerszy snapshot całej sprawy jest dozwolony.

Snapshot hash liczymy z deterministycznego JSON: UTF-8, klucze sortowane, bez whitespace, ensure_ascii=false, bez NaN/Infinity, kolejność list zachowana. To jawny lokalny profil `LW-CJSON-1`, nie deklaracja implementacji RFC 8785. Daty/czasy adapter normalizuje do UTC przed zapisaniem; pieniądze nie są float. Inny język musi przejść te same golden vectors, zanim jego hash będzie akceptowany. Body nie zawiera swojego hasha. Źródła plikowe haszujemy z oryginalnych bytes, nie reprezentacji JSON.

Snapshot acceptance jest osobnym Decision/AcceptSnapshot. Snapshot ID/hash jest pinem w DocumentPlan i Draft; nie wczytujemy bieżących faktów do draftingu po zamrożeniu wejścia. Prompt/model/rule/validator/provider/generator i RenderProfile są osobno przypięte w ReproductionManifest; parameters, raw output i input mają hashe. Zachowanie bytes raw output w kontrolowanym object store jest konieczne do replay. Reproducibility nie obiecuje deterministycznego ponownego wywołania modelu.

## Knowledge Graph i Dependency DAG

KnowledgeEdge opisuje znaczenie relacji i może reprezentować wzajemne stanowiska. Macierz dozwolonych par jest w kodzie `KG_PAIRS`. Relacje kanoniczne są polami encji; eksport grafu musi im odpowiadać. To nie jest harmonogram wykonania.

DependencyEdge oznacza input revision → output revision oraz input_hash. Graf wykonawczy musi być acykliczny; self-loop jest cyklem. Powstaje z rzeczywiście użytych wejść manifestu, nie ze wszystkich semantycznych relacji KG. Argument może polemizować z innym argumentem w KG, ale wynik generowania nie może zależeć od własnej przyszłej wersji.

Change propagation: po zapisie nowej rewizji wyszukujemy consumers starej rewizji, wyliczamy przechodnie domknięcie DAG i zapisujemy DependenciesInvalidated wraz z case_sequence. Zmiana wyłącznie metadanych również konserwatywnie unieważnia wynik P0. Przy brakującym indeksie dependencies stan UNKNOWN blokuje FINAL. Historyczne FINAL zachowuje historyczny release receipt, lecz nie jest CURRENT do ponownego użycia. Bezpośrednio przed wydaniem powtarzamy kontrolę case_sequence, bieżących approvals oraz policy. Nie czekamy na asynchroniczny UI.

## Komendy, zapytania i zdarzenia

Wspólny CommandMeta: command_id, tenant_id, case_id, idempotency_key, expected_case_sequence, correlation_id. Tenant/case z payload porównujemy z context, nigdy nie ufamy samemu polu. Actor jest przypisywany po uwierzytelnieniu. expected_revision chroni konkretną encję. CreateCase wymaga expected_case_sequence=0; AppendRevision jest wewnętrznym portem repozytorium, nie dowolnym publicznym API.

| Komenda | Wejście domenowe | Warunki i rezultat |
|---|---|---|
| CreateCase | Case rev1 | uprawniony owner, unikalny ID; APPLIED + sequence + RevisionAppended |
| AppendRevision | EntityPayload, expected_revision | schema, scope, CAS, wszystkie guardy; nowa immutable revision i audyt |
| AcceptSnapshot | Snapshot, Decision ref | closure/hash, SNAPSHOT_ACCEPTANCE i uprawnienia; SnapshotAccepted |
| GenerateDocument | document_type pin, objective_ids, snapshot ID/hash, approved plan, profile | accepted snapshot; immutable input; DraftGenerated lub ABSTAIN/error; nigdy FINAL |
| ValidateDraft | draft ref, snapshot hash, validation_policy | pełny jawny zestaw validatorów; ValidationRun + findings + ValidationCompleted |
| RequestRelease | draft, render_hashes, run_ids, approval | authoritative run resolution, gate, CAS; ReleaseGranted/Denied |

Specjalistyczne use cases 02 (VerifyParty, ConfirmFact, ApprovePlan, RecordDecision) są application handlers budującymi AppendRevision/Decision; nie dodajemy jednej publicznej komendy do każdego pola. Operacja zatwierdzania musi wykonać guard akceptacji, a nie tylko guard przejścia.

Queries: GetRevision(target), GetSnapshot(snapshot_id), GetCaseHead, GetProvenance(target), GetAffectedDrafts(target). Wynik to EntityPayload/Snapshot/lista Ref lub DomainError. GetCaseHead zwraca case_sequence i heads; dla pustego wyniku podaje [] i odczytaną sekwencję. Port musi kontrolować authorization zarówno przed resolve, jak i przed zwróceniem danych. Odpowiedzi nie ujawniają istnienia ID innego tenantu.

DomainEvent to typ zdarzenia + AuditEvent + subjects. Consumer deduplikuje event_id; kolejność w ramach Case wyznacza sequence. Outbox jest atomowy z domeną, dostarczanie at-least-once. Nie twierdzimy, że transport gwarantuje exactly-once.

Idempotency scope: tenant + case + idempotency_key. Hash obejmuje pełne normatywne body oraz expected guards; ten sam key + ten sam body zwraca poprzedni rezultat bez nowego zdarzenia. Inne body → IDEMPOTENCY_CONFLICT. Dwa klucze aktualizujące tę samą expected sequence: jeden commit, drugi CONFLICT. Replay jest sprawdzany przed CAS, ale dopiero po sprawdzeniu uprawnień. Retry po konflikcie wymaga nowego odczytu i ponownej decyzji użytkownika/handlera, nie ślepego zastąpienia expected_revision. Retencja deduplikacji musi obejmować okno retry zadania, a decyzje/release keys są przechowywane z audytem.

## Structured AI contracts

AIRequest zawiera scope, task, snapshot ID/hash, allowed input refs, optional SectionContract, piny prompt/output contract/data policy. Adapter modelu rozwiązuje treść dopuszczonych wejść pod tym samym scope. AIResult identyfikuje request i snapshot, ma disposition=PROPOSE/ABSTAIN, proposals[], optional SectionText, missing_information i reason. ABSTAIN wymaga reason i pustego output; nie jest błędem transportu.

AIProposal nie ma statusu APPROVED/CONFIRMED, aktora człowieka ani prawa do zapisania domeny. Candidate mapper przypisuje ID, scope, provenance operation i stan CANDIDATE/PROPOSED. source_refs muszą należeć do request.input_refs, anchors muszą zostać sprawdzone względem dozwolonych source documents. Propozycja z nieznanym anchor nie staje się source-backed po samym przejściu schematu.

Dla drafting: kolejność Section odpowiada planowi, required⊆used⊆allowed, Claim refs⊆allowed_claims, UNSUPPORTED nie jest dopuszczone, INFERRED wymaga label i podstawy. Coverage checker sprawdza każde zdanie, cytat i żądanie, nie tylko deklarowaną listę refs. Znacznik STRUCTURAL nie może służyć do ukrywania nowego faktu; wymagany semantyczny validator i/lub przegląd człowieka.

Prompt injection w źródle jest treścią źródła. AI nie otrzymuje zdolności wykonywania komend, zwalniania blockerów ani edytowania policy. Brak treści źródła prowadzi do ABSTAIN/UNKNOWN. Parsing: extra fields, duplicate JSON keys, niedozwolone enum, wielkość >2 MB i NaN odrzucane. W produkcji parser wszystkich messages musi użyć strict_json oraz limitu głębokości/zasobów z transportu, a nie wyłącznie BaseModel.validate_json.

## Walidacja i FINAL

ValidationRun wiąże dokładny draft ref/hash, snapshot hash, policy, check results, komplet finding refs, hashes renderu i manifest wykonania. PASS jest wynikiem zaufanego adaptera validatora, nie flagą podaną przez klienta lub AI. Wszystkie kontrole §39 oraz document/adversarial są wymagane. ERROR/BLOCKER/CRITICAL, brak kontroli, UNKNOWN, nieaktualne wejścia lub zmienione bytes uniemożliwiają FINAL.

Pre-render: po V1–V9 i ludzkiej akceptacji walidowanej wersji powstaje autoryzacja RenderRequest; renderer ma wyłącznie SemanticDocument+profile. Wynik jest roboczy do czasu kontroli renderu. Post-render: run wiąże wyrenderowaną wersję i jej bytes; potwierdzenie DOCUMENT_APPROVAL odnosi się do tej dokładnej wersji. Wersja wcześniejsza może posłużyć do renderowania, ale nie do ominięcia akceptacji zmienionej treści. Finalne potwierdzenie może nastąpić w jednym ekranie przeglądu wyniku. CERTIFIED wymaga dodatkowego, niezależnego procesu/policy; etap 01 nie definiuje ani nie przyznaje certyfikacji prawnej.

Czysta funkcja evaluate_release ocenia zgodność kontraktów. Nie pobiera autoryzacji, nie wykonuje V2–V9 i nie dowodzi prawdziwości dostarczonych PASS. Musi być wywołana wyłącznie przez ReleaseService z authoritative repozytoriów. Publiczne przyjmowanie ValidationRun od użytkownika byłoby krytycznym naruszeniem. ReleaseService w 02/10 musi dodatkowo sprawdzić: komplet wymaganych findingów, aktualne heads/revocations, snapshot acceptance, approved plan, source verification, graph/state validators, evidence/citation coverage, execution identity validatorów oraz atomowy CAS i outbox. Brak implementacji tych portów jest NO-GO dla wydawania prawdziwego FINAL.

Risk ACCEPTED ani Finding RESOLVED nie mają prawa override. Naprawa wymaga nowego run z ponowną weryfikacją i nadal obecnymi nierozwiązanymi problemami. Dla nieaplikowalnej reguły validator może zwrócić PASS wyłącznie z audytowaną podstawą applicability; brak wiedzy to UNKNOWN.

## Error model i bezpieczeństwo

DomainError zawiera code, path (JSON pointer), bezpieczny message, retryable i correlation_id. API mapuje SCHEMA_INVALID/INVALID_TRANSITION na 422, CONFLICT/IDEMPOTENCY_CONFLICT na 409, FORBIDDEN na 403 lub nieujawniające 404, nieznany snapshot/ref na 404, brak dowodu/STALE/GATE_DENIED na kontrolowaną odpowiedź domenową. Szczegóły wewnętrznych Violation są mapowane na zamknięty publiczny code; np. REFERENCE_TYPE→BROKEN_REFERENCE, APPROVAL_CONTENT_CHANGED→GATE_DENIED. Taki mapper jest wymaganym adapterem 02, nie gotowym HTTP serwerem pakietu.

Case isolation obowiązuje encje, source bytes, snapshots, cache keys, idempotency, logi, odczyty i indeksy. PostgreSQL composite FKs i RLS oraz authorization middleware muszą zostać wdrożone w 02/03/18; sama obecność tenant_id nie daje izolacji. Wyszukiwanie globalnego prawa nie może ujawniać użycia źródła przez inną sprawę. Zwykły log zawiera code/correlation_id/hash, bez text/message z Pydantic zawierającego input_value. PII-aware logging jest warunkiem adaptera.

Audyt ma actor, scope, timestamp, sequence, input/output hashes, source_versions, provider/model, rule_version, previous_event_hash. Hash chain wykrywa zmianę względem zaufanego zakotwiczenia; nie chroni samodzielnie przed administratorem przepisującym cały łańcuch. Uprawnienia append-only, backup i niezależne anchoring są zadaniem storage/audit. Usuwanie artefaktów uwzględnia retencję i legal hold bez przenoszenia pełnych danych do logów.

## Machine-readable contract strategy

Pydantic strict/frozen + dodatkowe guardy stanowią wykonawczą definicję kontraktów. Każdy z 23 modeli oraz każdy message ma samodzielny JSON Schema 2020-12 z $defs, discriminator, required i additionalProperties=false. Nie wymagamy od dostawcy LLM obsługi pełnego schematu: adapter może ograniczyć schemat modelu, lecz serwer zawsze waliduje pełny kontrakt i reguły semantyczne. JSON Schema nie wyraża całej integralności, przejść i autoryzacji.

Zmiana usuwająca pole/enum lub zaostrzająca ograniczenia wymaga nowej głównej wersji kontraktu; nowy wariant enum też może łamać odbiorców i nie jest automatycznie minor. Schematy mają stabilne URN; produkcyjny registry kontraktów musi odmawiać nieznanej wersji. Migracja jest jawna, testowana na fixtures, zachowuje oryginalny payload i hash. Nie reinterpretujemy starych snapshotów nowymi regułami bez nowego raportu.

`python export_contracts.py` odtwarza schematy, lifecycle, macierz typów, katalog pól i fixtures. `python -m unittest discover -v` wykonuje lokalne testy. Schematy są produktami generatora; edycje ręczne nie są źródłem prawdy. Wyeksportowane JSON Schema nie zostały sprawdzone niezależnym silnikiem JSON Schema; lokalna walidacja wykonuje się przez Pydantic.

## Zakres implementacji a wymagania produkcyjne

| Obszar | DESIGNED | IMPLEMENTED lokalnie | EXECUTED / granica |
|---|---|---|---|
| 23 encje, typy, lifecycle | tak | modele, schematy, allowlisty | testy tworzenia schematów i kontraktów; nie wszystkie ścieżki 23 encji |
| Referential integrity / scope | tak | validate_graph, resolve, relation types, source hashes | syntetyczne grafy i błędne refs; brak RLS |
| Akceptacja | tak | validate_state: tożsamość, fakt, strategia, żądanie, plan, reguła, ryzyko | reprezentatywna weryfikacja party i próba podmiany treści; pozostałe wymagają integracji |
| Rewizje/immutability | tak | validate_revision; frozen modele | CAS/hash/lifecycle/content-lock testy |
| Snapshot | tak | struktura, head uniqueness, closure/hash | lokalny closure/hash; brak magazynu i snapshot approval handler |
| KG / DAG | tak | typed KG pairs; cycle i transitive affected | syntetyczny DAG; brak persystencji dependencies |
| AI | tak | payload schema, abstain, scope of refs, section boundaries | malformed/extra/unknown refs; semantic injection review nie jest zaimplementowane |
| FINAL | tak | pure evaluate_release | sztuczne check results; nie walidacja prawdziwego pisma |
| Idempotency/concurrency | tak | RevisionLedger sekwencyjny harness | replay i konkurencyjne expected seq; brak wielowątkowego/DB testu |
| PostgreSQL/transactions/RBAC/RLS/outbox | tak, granice kontraktowe | nie | NOT EXECUTED |
| Legal/procedural validators | kontrakty | nie | NOT EXECUTED; brak twierdzeń o poprawności prawa |
| Rendering/certification | granica kontraktowa | nie | NOT EXECUTED |

## Rekomendacja

CONDITIONAL GO do rozpoczęcia 02 — Case Core na podstawie kontraktów, po przyjęciu wskazanych ADR i z obowiązkowym wdrożeniem guard orchestration, autoryzacji oraz trwałych transakcji. Nie jest to zgoda na FINAL, certyfikację ani uznanie pełnego DoD §47. Merge i post-merge muszą zostać wykonane w świadomie wybranym repozytorium; bieżący pakiet nie jest zmianą w lukart-ros.
