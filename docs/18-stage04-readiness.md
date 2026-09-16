# Stage 04 — Ingestion: gotowość i macierz odbioru

Wejście: `f69ed44211f306e873617d08427588db8214be8f`, lokalny HEAD i zdalny
main zgodne (git ls-remote oraz API GitHub). Drzewo wejściowe czyste.
Brak AGENTS.md w repo i katalogach nadrzędnych. Przeczytano baseline,
specyfikację/ADR-01–09, AGR-01-001–007 oraz raporty 13–17.
CI wejścia: run 35151196713, head_sha zgodny, completed/success;
job 104979653652: wszystkie kroki SUCCESS. Zamknięcie Stage 03 i 121 PASS
udokumentowano w zadaniu 01a0a8dd-328e-7553-a822-94a841565bf3 i raporcie 17.
API main: protected=false, required checks puste. Nie zmieniamy ochrony.

**Gotowość implementacji: GO. Odbiór Stage 04 wymaga osobnych dowodów.**

## Granica zakresu

Baseline §7, §13, §22, §35 i §50 wyznacza Ingestion, ale nie osobny backlog.
Minimum P0: import oryginałów przez istniejący RegisterSource, deterministyczna
ekstrakcja tekstu/struktury, heurystyczna klasyfikacja i kandydaci z pochodzeniem.
Nowy moduł nie zmienia historycznych kontraktów ani Core SQL. Wynik jest
niezmiennym artefaktem raw_output Stage 03, nigdy Fact/Decision/approval.
Pełny lifecycle Facts/Evidence oraz zatwierdzanie zbioru kandydatów to Stage 05.

Obsługiwane P0: UTF-8 TXT (także ręczne deklaracje/formularz zapisany jako
tekst), DOCX (akapity i tabele), e-mail RFC822 (nagłówki i text/plain), PDF
z warstwą tekstową. Skany/obrazy są zachowywane, lecz otrzymują NEEDS_OCR;
brak tekstu nie jest sukcesem ekstrakcji. Automatyczny OCR, rozumienie układu
skanu i semantyczne rozstrzyganie sprzeczności wymagają osobno zweryfikowanego
adaptera — nie deklarujemy ich wykonania. ZIP akt i nieobsługiwane formaty
są zachowywane jako oryginały i oznaczane UNSUPPORTED, bez rozpakowywania na dysk.
Lista źródeł w §7 jest przykładowa ("mogą obejmować"), nie obietnicą wszystkich
adapterów w P0. Nie pobieramy URI ani nie wykonujemy makr/instrukcji dokumentu.

## Macierz wymagań i kryteriów

| ID | Podstawa | Implementacja | Kryterium |
|---|---|---|---|
| S04-01 | §7/13, SourceAnchor | odczyt dokładnego SourceDocument, hash/bytes, identyfikacja treści | oryginał i historyczny payload niezmienione; podmiana, brak, inny scope denied |
| S04-02 | §7, spec SourceAnchor | TXT/DOCX/email/PDF, osobna mapa pozycji i hash ekstrakcji | golden każdego adaptera, akapit/strona/część, błąd/pusty/skan jawny |
| S04-03 | §7/35 | klasyfikacja techniczna, daty/kwoty/jawne etykiety stron, kandydaci twierdzeń/dowodów | wyłącznie CANDIDATE, dokładny fragment i offset, bez dopisywania faktów |
| S04-04 | §7/26, ADR-06 | jawne ostrzeżenia i contradiction_check=NOT_RUN | brak automatycznej promocji; zero zmian Fact/Decision/head/approval |
| S04-05 | §27–28/43, ADR-09 | pin implementacji i parsera, immutable wynik/replay | retry identyczny; nowe ID uruchomienia zachowuje wcześniejszy wynik; restart, wersje, atomowy rollback |
| S04-06 | §36, spec izolacja | capability IngestSource/ReadIngestion, RLS storage, ograniczone parsowanie | cross-scope/AI/revoked denied, brak PII w błędach/logach, limity wejścia/ZIP/tekstu, malformed fail-closed |
| S04-07 | §47, zasady Stage 03 | focused/full, pakiet/schematy/manifest, review, CI/merge | zero failures/errors/skips, review dokładnego SHA, najwyżej 3 iteracje po pierwszym review, CI końcowego SHA SUCCESS |

## Zachowane ograniczenia

Modularny monolit/PostgreSQL; brak deploymentu, ROS, produkcji, Stage 05,
force push i przepisywania historii. Zastany egg-info w głównym checkout
pozostaje nietknięty i poza commitami. Testy wyłącznie syntetyczne; sekrety,
lokalne bazy i kopie pozostają poza Git. Retencja oryginału i wyniku osobna;
odczyt ekstrakcji wymaga nadal dostępnego oryginału. P0 nie stanowi walidacji
prawdziwości ani kompletności materiału i nie przyznaje FINAL.
