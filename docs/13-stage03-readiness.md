# Stage 03 — Storage + Versioning: gotowość i macierz

Data: 2026-09-16. Punkt wejścia lokalny i zdalny main:
`f80ac2efda722ff9a8a0ec1c986906f7c199a6bc` (potwierdzony git ls-remote i API).
Brak AGENTS.md w repo i katalogach nadrzędnych. Zastany nieśledzony egg-info
pozostaje nietknięty. Przeczytano baseline, specyfikację z ADR-01–09,
uzupełnienie AGR-01-001–007 i raporty 08–12 Stage 02.

CI wejścia: [35062407371](https://github.com/marcusdd720-ui/lukart-work/actions/runs/35062407371),
head_sha zgodny, completed/success; wszystkie kroki job 104685321054 SUCCESS.
109 testów i 61 kontroli wskazuje przekazany odbiór Stage 02. GO niezależnego
review dokładnego wejściowego SHA pochodzi z instrukcji użytkownika; raport 12
zachowuje wcześniejszy stan i nie zawiera tego późniejszego potwierdzenia.
API main: protected=false, required checks puste. API rulesets: 403, funkcja
niedostępna dla planu prywatnego repo. Nie zmieniamy ustawień ochrony.

**Gotowość implementacji: GO. Odbiór Stage 03: jeszcze niewykonany.**

## Granica zakresu i decyzje wykonawcze

Baseline §28–29 i §50 nazywa etap, nie dostarcza osobnego backlogu.
Poniższa macierz wyprowadza konkretne minimum z baseline i specyfikacji;
nie przypisuje wszystkich zaległości projektu do Stage 03.
Stage 02 już dostarcza rewizje, snapshoty, CAS, idempotencję i atomowy outbox.
Stage 03 rozwija persystencję bez zmiany ich historycznych kontraktów.

Modularny monolit zachowuje PostgreSQL. P0 Object Storage będzie osobnym
modułem i schematem PostgreSQL, z nieprzezroczystymi bytes, scoped identyfikacją
i portem odczytu/zapisu. Wspólna transakcja usuwa problem częściowego zapisu
metadanych i pliku. Jest to świadomy adapter P0, nie deklaracja S3 ani
infrastruktury chmurowej. Zewnętrzny backend wymaga później równoważnego
protokołu trwałości i izolacji. Limit rozmiaru jest jawny.

## Macierz wymagań i kryteriów odbioru

| ID | Podstawa | Zakres implementacji | Kryterium / test |
|---|---|---|---|
| S03-01 | baseline §29, spec źródła/snapshoty | scoped immutable object bytes dla nowych źródeł i artefaktów | bytes roundtrip, hash/length, uszkodzenie denied, rollback, restart |
| S03-02 | baseline §28/43, ADR-09 | append-only rejestr pinów niezależnych kategorii artefaktów | ta sama nazwa/wersja nie może zmienić bytes; wiele wersji, replay surowego wyjścia; brak automatycznej akceptacji |
| S03-03 | spec Machine-readable strategy, remediation Compatibility | jawna migracja schematu z ledgerem i checksum; rozpoznawanie kontraktów fail-closed | upgrade Stage 02 zachowuje payload/URN/hash/approval; powtórzenie idempotentne; drift/nieznana wersja odrzucone; rollback DDL |
| S03-04 | spec isolation, I03 | autoryzacja hosta i RLS/FK nowego storage | cross-tenant/case read/write denied, runtime bez owner/BYPASSRLS; brak danych w błędach |
| S03-05 | baseline §36, spec retencja, I17 | przypięta polityka, legal hold, uprawnione usunięcie bytes z trwałym tombstone | przed terminem/hold/brak grantu denied; po usunięciu historyczne metadane i hashe niezmienione, brak replay usuniętych bytes |
| S03-06 | spec backup/audit, baseline §47 | kopia PostgreSQL obejmująca core i storage, kontrolowany restore do nowej izolowanej bazy | rzeczywisty backup/restore, zgodność payloadów i bytes, snapshotów, akceptacji i replay; niezależny hash kopii |
| S03-07 | baseline §47, instrukcja odbioru | focused/golden/full regression, package/schema/report/manifest/diff | zero failures/errors/skips, niezależny review zamrożonego SHA, max 3 naprawy, CI dokładnego końcowego SHA, merge/post-merge |

## Poza zakresem

Stage 04 ekstrakcja/ingestion; search/vector retrieval jako indeksy pochodne;
silniki prompt/model/drafting/renderingu i release; rozstrzygnięcia prawne
dotyczące okresów retencji; zewnętrzny login, szyfrowanie infrastruktury,
produkcja/DR SLA (18/20), zewnętrzne anchoring audytu (12), ROS (19).
Nie implementujemy fikcyjnych transformacji nieistniejących starych schematów:
nieznane kontrakty pozostają dowodem raw, nie są reinterpretowane ani
automatycznie zatwierdzane. Dotychczasowe źródła inline Stage 02 pozostają
odczytywalne bez mutacji; ich fizyczne kasowanie wymaga odrębnej migracji
retencji i nie będzie wykonywane po cichu.
AGR-01-008–010 nie mają w repo treści ani ustalonego przypisania; nie są
deklarowane jako naprawione. Żadnego deploymentu, ROS ani Stage 04.
