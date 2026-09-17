# Stage 05 — Facts / Evidence: interfejs i granice

Moduł `lukart_work.facts`, pakiet 0.5.0. Nowe kontrakty 1.0.0:
FactEvidenceRequest, CandidateReviewRecord, FactEvidenceQuery, FactEvidenceMatrix.
Historyczne CoreRequest, Fact, Evidence, Decision, SourceDocument, IngestionResult,
schematy i SQL pozostają niezmienione. Pin bieżącej implementacji Core: 1.0.4,
obejmuje nowy serwis i kontrakty. Stare piny i zapisy nie są przeliczane.

## Host i autoryzacja

`FactEvidenceService(repository, authority).execute(raw_json, token)` dziedziczy
transakcję/CAS/idempotencję/audyt/outbox `CommandService`. Wspólny Core otrzymał
jedynie chroniony punkt wyboru parsera; domyślnie nadal parsuje stary CoreRequest.
Nowy serwis przyjmuje wyłącznie FactEvidenceRequest:1.0.0. Koperta zachowuje
CommandMeta (scope, command_id, expected_case_sequence, idempotency_key,
correlation_id), target i wymagane jawne rationale. Inputs/anchors użytkownika
są zakazane: wiązanie pochodzenia ustala serwer. Wszystkie zapisy wymagają
HUMAN, capability zgodnej z operation i sprawy niezamkniętej/niezarchiwizowanej.

`matrix(raw_json, token)` przyjmuje FactEvidenceQuery:1.0.0 z operacją
GetFactEvidenceMatrix, tenant_id i case_id. Wymaga scoped capability o tej
nazwie; HUMAN/SERVICE może czytać, AI nie. Odczyt zamkniętej sprawy dozwolony.
Host nie wystawia SQL/ObjectStore/provisioningu ani chronionych metod serwisu.
Nie dodano HTTP/UI ani produkcyjnego logowania użytkowników.

## Przegląd kandydata

ReviewCandidate.data zawiera source_id, run_id, result_hash (digest całego
IngestionResult), candidate_index, expected_review_revision i disposition
ADMIT/REJECT. Obsługiwane są tylko FACT/EVIDENCE, nie pozorna automatyczna
weryfikacja dat/kwot/tożsamości. Dla ADMIT wymagany jest opis dowodu; dla FACT
także jawne statement człowieka i opcjonalne subjects Ref. To oceniona przez
człowieka treść, nie dowód, że dokument obiektywnie ją potwierdza.

Serwer sprawdza scope, bytes oryginału i hash ekstrakcji, status EXTRACTED,
indeks/rodzaj, wersję przeglądu i historię receipt. Odczyt wyniku wymaga
storage=True, jak Stage 04. W jednej transakcji powstają:

- dla FACT: REGISTERED Evidence (authenticity UNKNOWN) i CANDIDATE Fact;
- dla EVIDENCE: tylko REGISTERED Evidence;
- dla REJECT: receipt bez nowych encji;
- wspólny sequence, CommandResult, audit i outbox.

SourceAnchor wskazuje ID/hash oryginału. Locator RECORD zawiera canonical JSON
z ingestion_run/result_hash/candidate_index/fragment/start/end. fragment_hash
jest hashem UTF-8 cytatu ekstrakcji, nie bytes strony PDF. Kandydat i source
nie są nadpisywane. Provenance ma HUMAN/MANUAL, rationale i pin ekstraktora;
nie udaje nowego automatycznego wyniku AI. Statement i opis podlegają limitom
domenowego Text; dłuższy fragment wymaga świadomego streszczenia przez człowieka.

CandidateReviewRecord jest append-only w scoped `lw_core.objects`, z własnym
URN/hash, actor/czasem, anchor, created Ref, revision i previous_hash. To nie
nowa kanoniczna encja Decision. Po REJECT można ponownie ocenić kandydata
podając expected_review_revision; po ADMIT nie tworzy się ponownie encji.
Dalsze odrzucenie/zakwestionowanie dotyczy już Fact/Evidence. Retry identycznej
komendy zwraca historyczny CommandResult, bez nowego zapisu ani nowej akceptacji.
Zmiana treści/aktora przy tym samym kluczu jest konfliktem.

## Lifecycle faktów i dowodów

| Komenda | Dane poza target i rationale |
|---|---|
| MarkFactExtracted, ReviewFact, DisputeFact, RejectFact | puste data |
| ConfirmFact | decision: dokładny Ref ludzkiej FACT_ACCEPTANCE |
| UpdateFact | jawnie wybrane statement/support/evidence/subjects/event_date/amount/key_fact |
| ReviewEvidence, AcceptEvidence, ChallengeEvidence, ExcludeEvidence | puste data |
| UpdateEvidence | jawnie wybrane description/authenticity/submitted_in |

Przejścia pozostają w opublikowanej allowliście. CONFIRMED Fact nie może być
edytowany bez DisputeFact. REJECTED jest terminalny w tym serwisie.
ACCEPTED Evidence przed zmianą treści wymaga ChallengeEvidence; EXCLUDED jest
terminalny. Source dowodu nie może być podmieniony — inny materiał wymaga
nowego Evidence. AcceptEvidence jest ludzką audytowaną oceną, nie weryfikacją
sądową i nie zmienia automatycznie authenticity na VERIFIED.

ConfirmFact wymaga SOURCE_BACKED, dokładnie bieżących wersji ACCEPTED Evidence,
braku DISPUTED authenticity, dostępnego oryginału i (dla promocji) przypiętej
ekstrakcji. Akceptacja nie odnosi się do „latest”: po zmianie stanu dowodu
trzeba jawnie zaktualizować evidence Ref faktu. Następnie osobno ReviewFact,
Core RecordDecision(FACT_ACCEPTANCE, outcome=ACCEPT, target=reviewed Fact),
ConfirmFact z tym Ref. Dziedziczone guardy odrzucają złą decyzję, revocation,
supersedes, niewłaściwego aktora, zmienioną treść oraz nieaktualny target/CAS.

Historyczny CoreRequest zachowuje starsze zachowanie dla kompatybilności.
Nie zaostrzono po cichu jego kontraktu ani historycznej definicji CONFIRMED.
Host kieruje nowe operacje Stage 05 do FactEvidenceService; ocena macierzy
stosuje bieżące warunki również do faktów utworzonych dawniej i może oznaczać
historycznie CONFIRMED jako nieaktualny. Nie jest to produkcyjny release gate.

## Macierz i propagacja

FactEvidenceMatrix odczytuje jeden spójny stan pod blokadą sprawy i podaje
case_sequence, aktualne rewizje faktów i dowodów oraz historię przeglądów.
Pokazuje status/support, przypięte Evidence Ref, historyczną treść,
acceptance_live, confirmation_current, issues i used_in. Used_in obejmuje
aktualne encje odwołujące się do logicznej tożsamości faktu, także starszej
rewizji; Ref odbiorcy pozwala odczytać dokładne wiązanie. Provenance nie jest
traktowane jako aktualne użycie. Wiersze Evidence obejmują także dowody
niepowiązane jeszcze z faktem.

source_available dotyczy oryginału, provenance_available całego wymagającego
weryfikacji łańcucha. Oddzielne kody ORIGINAL_UNAVAILABLE/EXTRACTION_UNAVAILABLE
wyjaśniają brak, STALE_EVIDENCE wskazuje zmianę rewizji, NO_LIVE_ACCEPTANCE brak
aktywnej akceptacji. CHALLENGED/EXCLUDED i sporna authenticity blokują bieżące
potwierdzenie. DISPUTED fact pozostaje jawnie sporny. Pusty wynik nie oznacza
braku faktów w świecie, tylko brak zarejestrowanych rekordów w scope.

Każda nowa rewizja Fact z tego serwisu rejestruje DependencyEdge od dokładnych
Evidence i Decision. Dziedziczony Core emituje DependenciesInvalidated przy
zmianie tych wejść; istniejące krawędzie planów obejmuje domknięcie DAG.
Nie przepisujemy starych payloadów i nie zakładamy kompletnego historycznego
indeksu. Macierz zawsze sprawdza stan bieżący, także po retention delete,
który nie emituje domenowego zdarzenia zmiany dowodu. Przyszły FINAL wymaga
własnej pełnej walidacji (późniejsze etapy).

## Testy i granice

Synthetic PostgreSQL: golden source→ingestion→human admission→evidence review→
fact review→decision→confirmation→snapshot, współbieżność osobnych authority,
rollback po finish, restart, RLS, retencja, revoked approvals i zachowanie
historii. Pełny runner Stage 05 nie nadpisuje raportów Stage 01–04 i odrzuca
SKIP. Nowe schematy są eksportem, walidacja semantyczna komend jest serwerowa.
Matryca jest P0 bez UI/paginacji; automatyczna analiza sprzeczności, kwalifikacja
prawna dowodów, OCR, Stage 06, ROS i produkcja pozostają poza zakresem.
