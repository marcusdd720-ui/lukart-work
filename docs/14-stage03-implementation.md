# Stage 03 — implementacja Storage + Versioning

Zakres: 13-stage03-readiness.md. `lukart_work.storage` jest adapterem P0 Object
Storage w osobnym schemacie PostgreSQL. Oryginały i artefakty to nieinterpretowane
bytes, limit 16 MiB; źródła CoreRequest mają również dotychczasowy limit JSON.
Nie ma pobierania URI, ekstrakcji, generowania ani nadawania FINAL.

## Interfejs i wersje

Zaufany host jawnie wykonuje `migrations.migrate(connection)` jako właściciel
nowej/testowej bazy, potem `grant_runtime(connection, role)`. Konstruktor
repozytorium nigdy nie wykonuje DDL. `PostgresRepository(dsn, storage=True,
retention_policies=...)` włącza magazyn nowych źródeł; `storage=False` zachowuje
kompatybilność hosta Stage 02. Starsze inline bytes są dostępne także po
włączeniu storage. Nie przepisujemy starych danych.

`StorageService` współdzieli TokenAuthority i scoped transakcję Core.
Uprawnienia hosta: StorageWrite, StorageRead, StorageHold, StorageDelete.
AI nie może używać portu; usunięcie i hold wymagają HUMAN. SQL nie jest
publicznym interfejsem: host nie udostępnia użytkownikom połączenia/DSN.
Każda operacja używa tej samej blokady sprawy, również w odrębnych procesach.
RLS i złożone FK obejmują wszystkie nowe tabele. Runtime nie jest owner,
superuser ani BYPASSRLS. Błędy mają stały bezpieczny code bez bytes i DSN.

`put(token, category, name, version, bytes, retention_pin)` utrwala dokładne
bytes i metadane. Kategorie: source, raw_input, raw_output, render, prompt,
model, provider, rule, validator, render_profile, generator i knowledge.
To magazyn wersji, nie implementacja tych późniejszych silników. Tożsamość
jest scoped, deterministyczna, niezależna od hasha innej sprawy. Ta sama
kategoria/nazwa/wersja nie może zmienić treści ani polityki. Inny actor nie
przejmuje retry. `resolve(token, category, VersionPin)` wymaga dokładnej
nazwy, wersji i hasha; nie ma latest. Odczyt sprawdza hash i długość bytes.
`ArtifactRecord:1.0.0` jest nowym kontraktem; stare schematy nie zmieniły się.

Nowe źródło zapisuje metadane Core i bytes storage w jednej transakcji razem
z sekwencją, wynikiem komendy i audit/outbox. Inne artefakty mają niezależne
metadane z aktorem i czasem; nie modyfikują Case ani akceptacji. Hold jest
append-only, tombstone zapisuje aktora, czas i historyczny hash. Pełny
zewnętrznie zakotwiczony audyt pozostaje Stage 12.

## Migracje i historia

Ledger przechowuje kolejność i SHA-256 skryptów SQL po normalizacji LF.
Upgrade porównuje strukturę Stage 02 z pustym schematem wzorcowym utworzonym
transakcyjnie z opublikowanego SQL: typy/kolumny, constraints, RLS/policies,
aktywność triggerów i definicje funkcji. Schemat wzorcowy jest usuwany w tej
samej transakcji; nie zawiera danych i ma nową losową nazwę. Brak ledgeru
nie uprawnia do usunięcia istniejącej struktury. Powtórny migrate jest
idempotentny; nieznana wersja/drift checksum blokują, błąd DDL cofa transakcję.
Ledger jest administracyjny, bez grantów runtime. Nie jest dowodem ochrony
przed złośliwym właścicielem DB. Core migration.sql jest niezmieniony.

Historyczne raw payloady, URN, hashe, snapshoty i approvals są porównywane
przed i po upgrade oraz backup/restore. Nieznane kontrakty Core nadal są
odrzucane przez decode. Nie powstała fikcyjna migracja domenowego kontraktu,
którego nowej wersji etap nie definiuje. Pin implementacji Core ma wersję
1.0.2 i obejmuje storage; stare piny i zdarzenia nie są przeliczane.

## Retencja i ograniczenia

Host provisionuje `RetentionPolicies([(exact_pin, days), ...])`; zero dni
służy w testach do natychmiastowego wygaśnięcia, nie jest produkcyjną regułą.
Nieznany pin zachowuje bytes do 9999-01-01; użytkownik nie podaje deadline.
Zmiana konfiguracji nie skraca już zapisanych terminów. Legal hold blokuje
delete niezależnie od terminu. Tombstone i usunięcie bytes są atomowe; SQL
odrzuca delete bez tombstone oraz ponowne wstawienie usuniętych bytes.
Retry nie odtwarza zawartości. Plan/snapshot/approval zachowują historię,
ale odczyt usuniętego źródła jest PROVENANCE_MISSING; to nie nadaje release.

Inline bytes Stage 02 pozostają poza fizycznym delete tego adaptera; ich
kasowanie wymaga osobnego planu migracji retencji. Brak rekordu dla legacy ID
nie udaje sukcesu usunięcia. Nie wykonano takich operacji.

## Kopia i odtworzenie

`backup.py` używa pg_dump/pg_restore, bez haseł w argumentach i logach.
Odtwarzanie dostępne tu jest próbą do nowej bazy o prefiksie
lukart_stage03_test_; nigdy nie nadpisuje istniejącej bazy. Oczekiwany hash
kopii przekazywany osobno blokuje zmienione bytes. Kopia obejmuje Core,
storage, ledger i sekwencje. Test przywraca uprawnienia osobno, sprawdza raw
dane, replay, oryginały, legal hold i tombstone.

Kopie zawierają dane i wymagają własnej retencji. Stara kopia sprzed delete
może zawierać później usunięte bytes: produkcyjny restore musi uwzględnić
późniejsze tombstones i politykę kopii przed udostępnieniem danych. Etap nie
uruchamia produkcyjnego backup scheduler, DR SLA ani produkcyjnego restore.
Próby używają synthetic data i tymczasowych plików poza repo. SQL runtime
nie ma dostępu do plików kopii ani administracyjnego backup API.

CI używa klienta PostgreSQL 18 z [oficjalnego repozytorium PGDG](https://www.postgresql.org/download/linux/ubuntu/),
aby pg_dump obsługiwał serwer 18. CI dokładnego SHA jest osobnym kryterium.
