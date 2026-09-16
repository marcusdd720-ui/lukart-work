# Stage 04 — interfejs, pochodzenie i granice

`lukart_work.ingestion` jest modułem monolitu. Instalacja adaptera:
`pip install '.[postgres,ingestion]'`. Nie ma nowej migracji SQL ani zmiany
historycznych URN. Jedyny nowy kontrakt: IngestionResult:1.0.0. Pakiet 0.4.0;
pin bieżącego Core 1.0.3 uwzględnia zastrzeżenie przestrzeni ingestion w storage.
Stare piny, payloady, hashe, decyzje i schematy pozostają historyczne.

## Przepływ hosta

1. Host rejestruje oryginał dotychczasowym `RegisterSource` (CAS, scoped
   SourceDocument, audit/outbox, atomowy zapis metadanych i bytes Stage 03).
   Duży upload nadal podlega limitowi dotychczasowej koperty Core; moduł nie
   rozszerza go po cichu. Nie ma pobierania plików z sieci.
2. `IngestionService(repository, authority).ingest(token, source_id, run_id)`
   wymaga capability `IngestSource`, sprawy niezamkniętej i storage=True.
   UUID uruchomienia nadaje zaufany host. Scope i actor pochodzą z capability.
3. Odczyt weryfikuje hash i długość oryginału. Parser działa w osobnym procesie
   z timeout 15 s; nie dostaje DSN/tokenów/zmiennych aplikacji. Stderr jest
   tłumiony, rezultat błędu nie zawiera treści wejścia. Linux dodatkowo ogranicza
   pamięć do 512 MiB i CPU do 10 s. Windows nie ma tu limitu pamięci procesu;
   izolacja OS dla produkcyjnego hosta pozostaje wymaganiem Stage 18/20.
4. Wynik jest jednym immutable artefaktem `raw_output`,
   `name=ingestion/<run_id>`, `version=1`. Zawiera source ID/hash/długość,
   actor/czas, pin kodu ekstraktora, pin kodu pypdf 6.10.0, wersję Python,
   hash body, fragmenty i kandydatów. Metadata i bytes są atomowe. Nie zmienia
   Case sequence, Fact, Evidence, Decision, snapshotu ani approval.
5. `read(token, source_id, run_id)` wymaga `ReadIngestion`, weryfikuje
   oryginał i wynik oraz ich wiązanie. Retry tego samego run zwraca historyczny
   wynik, także po aktualizacji parsera. Inny source/actor nie przejmuje runu.
   Nowe uruchomienie wymaga nowego UUID; nie nadpisuje wcześniejszego wyniku.

Źródło i pochodny wynik mają politykę retencji źródła, ale osobne terminy,
hold i tombstone. Usunięcie oryginału blokuje użycie ekstrakcji, nie oznacza
automatycznego usunięcia wszystkich jej bytes. Uprawniony host usuwa je zgodnie
z retencją Stage 03. Read zamkniętej sprawy jest dozwolony, nowa ekstrakcja nie.
Legacy inline SourceDocument pozostaje obsługiwany, bez przepisywania bytes.

## Zaufanie i mapa pozycji

`source_hash` zawsze oznacza hash całego oryginalnego pliku. `body_hash`
oznacza LW-CJSON-1 ekstrakcji. `text_hash` dotyczy UTF-8 konkretnego fragmentu;
nie jest hashem strony PDF ani bytes DOCX. Lokalizatory LINE/PARAGRAPH/PAGE/
MIME_PART/HEADER odnoszą się do struktury danego adaptera. Kandydaci wskazują
indeks fragmentu, zakres znaków Python `[start:end]` i dokładny quote;
model sprawdza hash fragmentu i zgodność cytatu. Nie udajemy bajtowych offsetów
w skompresowanym DOCX/PDF ani współrzędnych obrazu.

Klasyfikacja jest techniczna (TEXT/DOCUMENT/EMAIL/PDF/IMAGE/UNKNOWN), nie
rozstrzyga typu pisma prawnego. Heurystyki dat/kwot rozpoznają zapis, bez
walidacji kalendarza/rachunkowej/semantycznej. Party to jawna etykieta lub
nagłówek From/To, nie zweryfikowana tożsamość. FACT i EVIDENCE to propozycje
przeglądu cytowanych fragmentów. Instrukcje wewnątrz źródła są zwykłym tekstem.
`contradiction_check=NOT_RUN` jest obowiązkowe, nie raportujemy fałszywego PASS.
Wszystkie candidates mają wyłącznie CANDIDATE, bez acceptance i bez adaptera
promocji do Case Core. Pełny proces Facts/Evidence nie jest Stage 04.

Publiczny StorageService nie może zapisać przestrzeni `ingestion/`, więc
użytkownik StorageWrite nie podszywa się pod ekstraktor. Bezpośredni SQL,
ObjectStore i provisioning pozostają prywatnymi portami zaufanego hosta,
jak w Stage 03. Runtime nadal nie jest właścicielem ani BYPASSRLS.

## Format i kompletność

- TXT: UTF-8 z opcjonalnym BOM, oryginalne bytes zachowane, osobne linie.
- DOCX: tekst akapitów także w tabelach, tabulatory i przerwy; DTD/entities
  zabronione niezależnie od kodowania. Nie odczytujemy zewnętrznych relacji,
  makr ani obrazów. Headers/footnotes/drawings nie są objęte: PARTIAL_EXTRACTION.
- E-mail: nagłówki i części text/plain z jawnym kodowaniem; HTML i załączniki
  nie są renderowane/uruchamiane, ich pominięcie daje PARTIAL_EXTRACTION.
  Oryginalny MIME pozostaje kompletny. Załącznik wymaga osobnego importu.
- PDF: pypdf strict, tekst stron; szyfrowanie/malformed odrzucane. Zawsze
  PARTIAL_EXTRACTION (brak dowodu kolejności wizualnej i pokrycia obrazów).
  Puste strony sygnalizują OCR_REQUIRED, całkowity brak tekstu NEEDS_OCR.
- Obraz/skan: zachowanie oryginału, NEEDS_OCR, bez udawanej ekstrakcji.
- ZIP akt/inne: UNSUPPORTED. DOCX jest odczytywany w pamięci bez extractall.

Limity: 16 MiB bytes, DOCX 1000 wpisów/16 MB łącznie/4 MB na wpis,
200 stron PDF, 1000 fragmentów, 100000 znaków fragmentu, 500000 znaków tekstu,
4000 kandydatów, 8 MiB odpowiedzi parsera. Przekroczenie daje FAILED bez
częściowych kandydatów. Limit odpowiedzi nie jest niezależnym sandboxem OS.
FAILED/UNSUPPORTED/EMPTY/NEEDS_OCR są utrwalanymi wynikami do obsługi przez
hosta, nie sukcesem wydobycia. Nowe uruchomienie po naprawie zachowuje błąd.

## Weryfikacja

Runner Stage 04 wykonuje całą regresję i odrzuca skips. Raporty Stage 01–03
nie są odświeżane ani reinterpretowane. Nowy checker weryfikuje manifest,
bieżące tested_sources i JSON; historyczne tested_sources opisują historyczny
kod, dlatego nie porównuje ich do zmienionych implementacji bieżącego etapu.
CI wykonuje checker przed pip, potem pakiet i regresję na PostgreSQL 18.
Niezależny review oraz CI dokładnego SHA są odrębnymi bramkami od testów.
