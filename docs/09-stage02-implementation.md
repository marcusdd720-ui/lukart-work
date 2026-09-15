# Stage 02 — Case Core implementation

Status: IMPLEMENTED, w odbiorze. `08-stage02-readiness.md` pozostaje historycznym wynikiem kontroli wejściowej SHA e278b97521731b8dc0395560db17e0e601a1d714; nie jest raportem odbioru obecnych zmian. Review i naprawy: `11-stage02-review.md`.

## Zakres

Stage 02 implementuje lokalny modularny serwis, bez serwera HTTP i bez UI: uwierzytelnione intencje, chronione queries, transakcyjny PostgreSQL, rewizje append-only, case sequence, CAS, trwałą idempotencję, snapshoty, decyzje, audit/outbox. Nie udostępnia publicznego AppendRevision. GenerateDocument, ValidateDraft i RequestRelease zwracają GATE_DENIED, dopóki późniejsze etapy nie dostarczą autorytatywnych usług.

### Jawne granice 02/03/18

Minimum persystencji wymagane dla poprawności Case Core jest w 02. Pełny storage, migracje historycznych wersji, backup, polityki retencji, niezależne anchoring, zewnętrzny login i produkcyjny hardening pozostają w późniejszych etapach. TokenAuthority jest lokalnym adapterem capability z jawnym provisionowaniem przez zaufany host; nie jest systemem logowania ani wymyślonym katalogiem ról biznesowych. Brak tokenu/grantu i restart adaptera odmawiają dostępu. W testach runtime bazy nie jest superuserem, właścicielem tabel ani BYPASSRLS.

## Interfejs aplikacji

`CommandService.execute(raw_json, token)` przyjmuje `CoreRequest:1.0.0`, zwraca CommandResult albo bezpieczny DomainError. `query(raw_json, token)` przyjmuje CoreQuery:1.0.0. Nowe kontrakty nie reinterpretują starych wire messages z Stage 01. AppendRevision pozostaje wewnętrznym kontraktem; nie jest operacją CoreRequest.

Host rezerwuje UUID sprawy przed provisionowaniem principal. Serwis generuje ID nowych encji deterministycznie jako UUIDv5(command_id, kind); źródła jako UUIDv5(command_id, "source"), snapshoty jako UUIDv5(command_id, "snapshot"). Są to identyfikatory techniczne, bez PII. Żądanie przekazuje expected_case_sequence, a zmiana istniejącej encji także dokładny target Ref. Serwis wyprowadza nowy numer rewizji i previous_hash z autorytatywnego rekordu, a aktora i UTC timestamps z kontekstu i zegara.

Operacje dodania przyjmują tylko pola domenowe, bez metadanych, statusu i linków akceptacji. Edycja jest ograniczona do Case, Party i Fact; zatwierdzona tożsamość/fakt wymaga najpierw jawnego zakwestionowania. VerifyParty, ConfirmFact i ApprovePlan otrzymują Ref decyzji i wykonują pełną koniunkcję guardów. RecordDecision zapisuje PROPOSED i RECORDED w jednej transakcji; historyczna propozycja i decyzja nie są nadpisywane. RevokeDecision tworzy nową rewizję. CERTIFICATION i DOCUMENT_APPROVAL nie są dostępne w tym etapie.

## Transakcje i reprezentacja dowodów

Jedno połączenie i transakcja obejmują scoped advisory lock sprawy, autoryzację, replay przed CAS, odczyt aktualnych heads, guardy, rewizje/obiekty, sequence, utrwalenie wyniku, audyt i outbox. RLS działa na wszystkich tabelach z tenant/case ustawionymi przez zaufany adapter. Nie przekazujemy dostępu SQL użytkownikowi. Composite FK obejmują scope. Runtime nie ma UPDATE/DELETE dla immutable tabel; trigger zabrania ich także po niezamierzonym szerszym grancie. Outbox zapewnia trwały odczyt zdarzeń do dostarczania at-least-once, nie exactly-once.

Payloady zapisujemy jako niezmienny tekst JSON LW-CJSON-1, wraz z pełnym URN i SHA-256 tych dokładnych UTF-8 bytes. Odczyt sprawdza hash i znaną wersję przed parsowaniem; nie dokonuje cichej migracji ani regeneracji historycznego hasha. Źródła zachowują oryginalne bytes oraz ich osobny hash. Core sprawdza integralność całego źródła; ocena znaczenia fragmentu/cytatu należy do późniejszych validatorów.

Obowiązek URN/hash obejmuje także CommandResult w replay oraz DomainEvent w audycie/outbox. Outbox korzysta ze wspólnej walidacji całego łańcucha poprzedników. Pin reguł 1.0.1 jest hashem jawnego manifestu plików implementacji w `core/policy.py`, z reprezentacją LF niezależną od platformy; nie jest hashem umownej nazwy reguły. Pakiet źródłowy używany przez uruchomiony proces powinien być niezmienny.

DisputeParty/DisputeFact usuwa aktywny link akceptacji tylko w nowej rewizji, dzięki czemu jawne zakwestionowanie działa także po revocation. Historyczna zatwierdzona rewizja i jej źródła pozostają zachowane. Dane provenance mogą wskazywać historyczne decyzje; nie nadaje im to aktualnych uprawnień zatwierdzania.

SupersedePlan realizuje już istniejące przejście APPROVED→SUPERSEDED wyłącznie dla uprawnionego człowieka. Zachowuje frozen treść i historyczny link approval, także po jego cofnięciu. Taki plan nie nadaje już aktywnego dopuszczenia i nie blokuje nowego snapshotu; zastąpienie wymaga nowego plan ID, snapshotu oraz nowej decyzji. To rozwinięcie nieopublikowanego jeszcze CoreRequest Stage 02, bez zmiany kontraktów Stage 01 i kanonicznego lifecycle.

Snapshot wybiera bieżące heads i domyka historyczne Ref, przypina źródła i wersje reguł/policy. Jest zapisywany przed jego akceptacją. Akceptacja rozwiązuje autorytatywną, aktualną decyzję i dokładny hash snapshotu; zmieniony input head blokuje nowe dopuszczenie. Nowe decyzje po zamrożeniu nie zmieniają snapshotu. Historia pozostaje odczytywalna także po odwołaniu akceptacji.

Dependency DAG jest oddzielony od relacji KG. Powstaje dla planu z jawnych wejść zamrożonego snapshotu, decyzji akceptującej snapshot oraz decyzji zatwierdzającej plan, nie z dowolnych semantycznych relacji. Zmiana użytej rewizji zapisuje DependenciesInvalidated atomowo z rewizją. Brak kompletnego indeksu przyszłych draftów skutkuje UNKNOWN, nigdy CURRENT ani FINAL.

## Lokalna baza testowa

Oficjalne archiwum Windows pochodzi ze [strony EDB](https://www.enterprisedb.com/download-postgresql-binaries), wskazanej przez [PostgreSQL](https://www.postgresql.org/download/windows/). Opcjonalny sterownik jest instalowany w istniejącej .venv, zgodnie z [dokumentacją Psycopg](https://www.psycopg.org/psycopg3/docs/basic/install.html). Archiwum, klaster i lokalne sekrety są wyłącznie w ignorowanym `.local-stage02/`; nie trafiają do repozytorium. Klaster nasłuchuje wyłącznie na 127.0.0.1:55432, z losowymi hasłami SCRAM; nie jest usługą Windows.

Po rozpakowaniu archiwum do `.local-stage02/runtime`:

```powershell
./scripts/start_stage02_postgres.ps1
./.venv/Scripts/python.exe -B -X utf8 scripts/prepare_stage02_database.py
./.venv/Scripts/python.exe -B -X utf8 -m unittest tests.test_stage02 -v
./.venv/Scripts/python.exe -B -X utf8 verify_package.py
./.venv/Scripts/python.exe -B -X utf8 -m unittest discover -v
```

Alternatywnie LUKART_TEST_DSN wskazuje izolowaną bazę ze schematem migration.sql i ograniczonym runtime role. Brak konfiguracji powoduje jawny SKIP testów integracyjnych i nie pozwala zamknąć etapu. Testy nie czyszczą obcych danych: każda metoda ma nowy tenant/case UUID.

Po pierwszym review uruchomiono schemat odbiorowy w nowej bazie `lukart_stage02_test_review1` przez `prepare_stage02_database.py --database lukart_stage02_test_review1`. Poprzednia baza syntetyczna pozostała bez zmian. `migration.sql` jest bootstrapem nowej bazy, nie automatycznym upgradem starszych payloadów bez wersji; produkcyjna migracja takich danych nie należy do tego etapu.

## Kryteria i dowody

Macierz wejściowa: docs/08-stage02-readiness.md. Bieżące wyniki, dokładny oceniony SHA, review i decyzja zamknięcia zostaną dopisane po wykonaniu testów; istniejące raporty Stage 01 nie są bieżącym dowodem Stage 02.
