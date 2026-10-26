# LUKART LEGAL OS — integracja niewidocznego silnika dokumentowego (inkrement 1)

Status: adapter Python i 15 testów jednostkowych na danych syntetycznych. NOT DEPLOYED / NOT E2E VERIFIED. Bez zmian w main, PR #79, ROS, lokalnej instancji V5 i istniejących sprawach.

## Docelowy model

Użytkownik widzi tylko LUKART LEGAL OS → Sprawy → Dokumenty. Generator Pism 2.0 działa w backendzie, nie ma osobnego interfejsu operatora dla użytkownika. WORK jest właścicielem kanonicznego CASE, dokumentów, decyzji HUMAN i renderów. Bez drugiej bazy spraw.

Otrzymany oryginał nie jest zmieniany. Metadane z OCR są kandydatami (sygnatura, adres, osoba podpisująca, data). Brak danych pozostaje jawny. Nowy dokument pobiera zweryfikowane informacje i odpowiedni profil, po czym korzysta z istniejącego renderer WORK.

## Pliki

- lukart_work/embedded_document_engine.py — adapter in-process.
- tests/test_embedded_document_engine.py — 15 testów celowanych.

## Dostępne operacje

- open_case: odczyt GetCaseHead, bez tworzenia nowego CASE.
- get_render: status zapisanego renderu.
- download_saved: odczyt istniejących DOCX/PDF bez ponownego renderowania.
- execute_confirmed: delegacja dokładnego, zaakceptowanego polecenia do natywnych zabezpieczeń WORK. Brak własnej autoryzacji.

Zaufany LEGAL OS host konstruuje istniejący GeneratorPismOperator zgodnie z operator_config.build_operator. Następnie tworzy EmbeddedDocumentEngine(existing_operator). Sesje, uprawnienia i tokeny pochodzą z istniejącego zaufanego hosta. Nigdy nie wolno tworzyć automatycznej fałszywej decyzji HUMAN: make_confirmation daje tylko fingerprint żądania po kliknięciu właściciela, nie podpis ani uwierzytelnienie. Autorytatywne kontrole wykonuje WORK.

## Test celowany

python -B -m unittest -v tests.test_embedded_document_engine

Testy używają wyłącznie atrap, nie prawdziwych spraw. Brak powtórki pełnych testów regresji.

## Następny inkrement (konkretny)

Podłączyć do rzeczywistej lokalnej karty sprawy LEGAL OS i jej uwierzytelnionej sesji. Wykonać jedno E2E syntetyczne: otworzyć istniejącą sprawę w jednym oknie, zobaczyć jej status, pobrać istniejący render DOCX/PDF, nie uruchamiając starego formularza V5.

Potem dodać połączony workflow import → fakty → projekt → edycja → eksport. Nie zgadywać endpointów lokalnego V5 8784; należy je zweryfikować przed połączeniem.

Kontrakt ROS↔WORK nadal jest PLANNED_NOT_IMPLEMENTED, a operacje wykonawcze zablokowane. Nie oznaczać pełnej integracji jako DONE przed rzeczywistym E2E i autoryzacją HUMAN.


## Inkrement 2 — karta sprawy + automatyczna lista dokumentów (2026-10-26)

**Zmiany w kodzie gałęzi integracyjnej:**

- `lukart_work/legal_os_case_view.py`: pojedynczy widok `/case` z tytułem i statusem aktualnej wersji CASE oraz listą zapisanych renderów; brak formularza operatora w widoku użytkownika.
- `lukart_work/operator_host.py`: `GET /case`, `/case.css`, `/case.js` i zamknięty katalog `POST /api/embedded_case` w istniejącym loopback host WORK.
- `lukart_work/embedded_document_engine.py`: `list_saved` odczytuje metadane `finalization_render` bez tworzenia nowego renderu, nowej bazy i bez egress oryginałów. Każdy odczyt używa autoryzowanej sesji WORK i uprawnienia `GetFinalization`, odrzuca AI, niewłaściwy CASE i wynik ponad 100 dokumentów (fail closed; paginacja osobnym etapem).
- Lista nie pokazuje jeszcze numerów sygnatur / adresatów — nie tworzymy tych metadanych z domysłów. Dokumenty identyfikowane są przechowywanymi render_id, ale identyfikatory są ukryte za nazwą i datą.
- Pobranie dokładnych DOCX/PDF nadal korzysta z `ReadFinalArtifact` i sprawdza oryginalne zapisane bajty.
- Ręczne identyfikatory tenant/case oraz token w tym inkremencie pozostają narzędziem zaufanej lokalnej sesji testowej. Jednolite logowanie i lista spraw jeszcze **nie istnieją**.
- Nie uruchamiać prawdziwych spraw w niezweryfikowanym panelu.

**Jednorazowe testy celowane (zamiast pełnej regresji starych dokumentów):**

```bash
python -B -m unittest -v tests.test_embedded_document_engine tests.test_legal_os_case_view tests.test_legal_os_case_title tests.test_legal_os_render_listing tests.test_legal_os_http_integration
```

Nowy `tests/test_legal_os_render_listing.py` sprawdza izolację, odmowę uprawnień, listowanie bez ponownego renderu i ograniczenia. Nowy `tests/test_legal_os_http_integration.py` sprawdza syntetyczną ścieżkę HTTP: `/case` → `open_case` → `list_saved` → `download PDF/DOCX`. Test HTTP używa atrap, nie rzeczywistego PostgreSQL.

**Stan wykonania:** kod zapisany w osobnej gałęzi; wynik testów i natywne E2E lokalnego Windows **NOT VERIFIED**, dopóki nie przejdą na exact HEAD i nie zostaną podłączone do autoryzowanej instancji. Desktop Commander zgłasza ONLINE, lecz pozostały limit zdalnych wywołań = 0%; brak zgody na płatny fallback.

### Następny inkrement — realne E2E i użyteczny workflow

1. Z istniejącej lokalnej konfiguracji WORK podłączyć operatora (bez nowej bazy), uruchomić **oddzielną instancję testową** z nowej gałęzi.
2. Otworzyć `http://127.0.0.1:<rzeczywisty-port>/case` (nie zakładać, że 8784 oznacza nową wersję).
3. Jedna syntetyczna sprawa: sprawdzić aktualny tytuł/status, listę renderów i pobranie zapisanych plików bez ponownego renderu.
4. Dopiero potem dodać do **tej samej karty sprawy** wejście: opis tekstowy + obraz/PDF/DOCX → OCR / kandydaci → HUMAN weryfikacja → projekt → edytor → eksport. Nie publikować nowego osobnego formularza.
5. Rozszerzać o przepisy/orzecznictwo oraz ROS wyłącznie po zweryfikowaniu osobnych kontraktów i licencji.

**Uwaga:** `Case Core` przechowuje kanoniczne dane. Nie synchronizować ich przez publiczne GitHub Actions. Nie wprowadzać rzeczywistych danych do testów syntetycznych.

## Inkrement 3 — jedna sesja, brak technicznych identyfikatorów na ekranie

**Stan kodu:** `/case` ma teraz tylko tymczasowe pole tokenu zaufanej sesji. Nie pokazuje już `tenant_id` i `case_id`; oba są wyznaczane po stronie serwera ze sprawdzonego `TokenAuthority`. Przeglądarka wysyła wyłącznie dozwolone nazwy operacji i identyfikator wybranego renderu. Backend `POST /api/embedded_session` dopisuje wyłącznie scope z natywnej sesji i deleguje do `read_case_action`, które ponownie stosuje natywne kontrole WORK. Nie ma możliwości wybrania innej sprawy przez podmianę `tenant_id` / `case_id` w JSON; nieznane pola są odrzucane.

Użytkownik otrzymuje widok: karta sprawy, tytuł/status, lista zapisanych dokumentów i przyciski pobierania. Silnik Generatora Pism 2.0 działa jako biblioteka; stary widok operatorski nie jest potrzebny do tych operacji.

**Zakres i luki:** wymagana jest jeszcze autoryzowana lokalna konfiguracja WORK i rzeczywiste sprawdzenie wdrożenia. Ten inkrement jest tylko do odczytu; nie zastępuje docelowego logowania, nie pozwala jeszcze wczytywać nowych pism, nie zatwierdza dokumentów ani nie uruchamia modelu AI. Przyszły workflow dokumentowy zostanie dodany do tej samej karty po oddzielnym potwierdzeniu bezpieczeństwa.

**Testy celowane (w jednym przebiegu, bez pełnej regresji):**

```bash
python -B -m unittest -v tests.test_embedded_document_engine tests.test_legal_os_case_view tests.test_legal_os_case_title tests.test_legal_os_render_listing tests.test_legal_os_http_integration
```

`test_legal_os_http_integration.py`: syntetyczna ścieżka HTTP `GET /case` → `POST /api/embedded_session open_case` → `list_saved` → `download`; brak wywołań renderera, odmowa dla obcej sprawy i aktora AI. Test nie korzysta z rzeczywistej bazy PostgreSQL.

**Warunki rzeczywistego odbioru end-to-end:** w izolowanym katalogu uruchomić jeden istniejący operator WORK przez zaufany plik konfiguracyjny; otworzyć `/case` na faktycznym porcie, połączyć uprawnioną sesję, odczytać jeden syntetyczny CASE i zapisane w nim pliki. Zachować odciski SHA-256 jako dowód, że pobrano dokładne oryginalne artefakty bez generacji. Bez tej próby stan pozostaje `LOCAL_E2E_NOT_VERIFIED`.

Zasada: bez przebudowy V5, bez ponownego otwierania wcześniejszych dokumentów, bez kopiowania prywatnych CASE do GitHub, bez płatnych fallbacków i bez zmian `main` / PR #79 / ROS.

