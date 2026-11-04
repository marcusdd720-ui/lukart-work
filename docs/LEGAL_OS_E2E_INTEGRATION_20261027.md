# LEGAL OS — jeden interfejs / integracja Generatora 2.0

LEGAL OS E2E: PARTIAL

Data wykonania: 2026-10-27. To raport implementacji, nie approval ani odbiór produkcyjny.

## Stan kodu

- Repozytorium: `marcusdd720-ui/lukart-work`.
- Istniejąca gałąź: `integration/legal-os-hidden-document-engine-v1`.
- Bazowy i bieżący HEAD: `64c42579819381988707f9b45c496ce84c01eb1e`.
- Zmiany pozostają lokalne, bez commitu, push, PR, CI i merge. Manifest wiąże dowody z dokładnymi SHA-256 zmienionych plików; stary PASS nie jest przenoszony automatycznie na tę poprawkę.
- Katalog pracy: `C:\Users\LukaszA\Projects\lukart-work-legal-os-integration` — worktree istniejącego repozytorium, nie druga aplikacja.
- Zachowano wcześniejszy eksport `LUKART-LEGAL-OS-TEST` oraz zmiany w `LUKART-HERMES-OS`. Istniejące prywatne środowisko eksportu wykorzystano tylko jako interpreter i źródło zainstalowanych bibliotek testowych; nie zmieniano jego plików ani ACL. Kod importowano jawnie z gałęzi integracyjnej, z `-I -B -X utf8`.

## Jeden interfejs

Istniejący `START-LUKART-LEGAL-OS.cmd` konfiguruje `http://127.0.0.1:8786/`. Host w trybie `--legal-os` udostępnia tam istniejący widok „Moja sprawa”; `/case` korzysta z tego samego widoku. W tej operacji hosta nie uruchamiano. Dostępność działającego adresu: **NOT VERIFIED**.

Implementacja: `lukart_work/legal_os_case_view.py` i istniejący `operator_host.py`. Nie dodano osobnego hosta, bazy ani interfejsu Generatora.

Dodano w tym samym widoku:

1. Opis sprawy zwykłym tekstem, rodzaj pisma odczytany z rzeczywistego `case_profile`, pełne nazwy i adresy nadawcy/adresata.
2. Zapis wszystkich danych przez istniejące `UploadAndIngest` oraz podgląd oryginału i istniejący przegląd kandydatów. Deklaracje nie stają się automatycznie zweryfikowanymi faktami/stronami.
3. Odczyt aktualnych zatwierdzonych planów i skonfigurowanych profili generatora. Nie dodano fikcyjnego katalogu rodzajów pism ani dostawców.
4. Wywołanie istniejącego `GenerateDocument` przez adapter silnika. Wymagane są zgodny zatwierdzony plan, jego snapshot i cele oraz zweryfikowane strony. Zmieniony opis lub adres wymagający ponownego przeglądu powoduje odmowę, zamiast wygenerowania pisma ze starych danych.
5. Wywołanie natywnego `ValidateDraft` i `RenderDraft`. Kontrola nie tworzy fikcyjnej opinii HUMAN; wykonanie walidacji nie oznacza PASS. Renderer zachowuje własne bramki.
6. Przekazanie zapisanego renderu do istniejącego pobierania DOCX/PDF, bez ponownego renderowania przy pobraniu. Zachowano edytor projektu i historię WORK.
7. Kontrolę kompletności formularza, jawne błędy i blokadę automatycznego ponawiania zapisu przy niepewnym wyniku. Zmiana/wyczyszczenie sesji czyści nowe pola; spóźniona odpowiedź nie odtwarza danych w wyczyszczonym formularzu.

## Dokładne pliki funkcjonalne i testy

- Zmieniony: `lukart_work/legal_os_case_view.py` — formularz, obsługa istniejącego endpointu `/api/embedded_session`, wspólny podgląd źródła i przyciski kolejnych operacji.
- Nowy: `lukart_work/legal_os_composer.py` — wąski adapter formularza do istniejących kontraktów/usług WORK; autorytatywny tenant/case z sesji, kontrola planu i danych, bez nowego silnika ani uprawnień.
- Nowy: `tests/test_legal_os_composer.py` — 17 testów kontraktów, zakresu i odmów na syntetycznych obiektach oraz atrapach usług.
- Nowy: `tests/test_legal_os_composer_dom.cjs` — 5 scenariuszy rzeczywistego JS widoku w symulowanym DOM/HTTP, wyłącznie dane syntetyczne.

## Dowody wykonania

Dowody: `evidence/legal-os-e2e-20261027/` w katalogu pracy.

| Kontrola | Wynik | Granica dowodu |
|---|---|---|
| Nowy adapter i dispatch sesji | 17/17 PASS | Usługi i podmioty syntetyczne; bez rzeczywistego uwierzytelnienia/DB |
| Zmieniony widok — celowane dotychczasowe testy | 14/14 PASS | Ponowiono tylko dla zmienionego komponentu, nie historyczne 20/28 testów Issue #80 |
| JS: formularz, sekwencja operacji, oba pobrania, odmowa, zmiana sesji | 5/5 PASS | Symulowany DOM/HTTP; nie przeglądarka i nie prawdziwy renderer |
| Składnia Python/JS i `git diff --check` | PASS | Kontrola statyczna |
| Rzeczywisty E2E przez przeglądarkę i Generator 2.0 | NOT VERIFIED | Nie wykonano; brak potwierdzonej autoryzowanej ścieżki HUMAN niezależnej od blokady |

`composer-tests.log` zawiera 31 testów: 17 nowego adaptera i 14 widoku. Po ostatniej zmianie wspólnego podglądu źródła ponowiono wyłącznie 14 testów widoku (`case-view-tests.log`) i 5 scenariuszy JS (`composer-dom-tests.log`). Niezmienione wyniki pozostawiono w mocy w ich pierwotnym zakresie. `case.js` i `case.html` to ekstrakty faktycznie testowanej wersji. `manifest.json` wiąże aktualne źródła i dowody; nie jest zatwierdzonym manifestem delivery.

Nie uruchamiano natywnego logowania, RUNAS, LSA, DPAPI, hosta ani połączeń PostgreSQL. Nie wywoływano modelu/dostawcy i nie instalowano zależności. Koszt dodatkowy: 0 PLN. W testach nie otwierano portów; transport był symulowany.

## Dokładny punkt blokady i następny krok

Istniejący `examples/human_case_operator_host.py:build_operator()` wymaga zaufanej konfiguracji operatora i `authenticate_human()` z istniejącego, zatwierdzonego adaptera tożsamości. Nie odnaleziono potwierdzonej, autoryzowanej izolowanej ścieżki wykonania tego kroku niezależnie od zablokowanego HUMAN/Issue #80. Testowe atrapy i sztucznie nadany Principal nie zastępują tej autoryzacji; nie użyto ich do uruchomienia aplikacji.

Ponadto realna syntetyczna sprawa musi posiadać wymagane przez WORK zweryfikowane strony, zaakceptowany snapshot i zatwierdzony plan. Nowy formularz zapisuje materiał i obsługuje istniejący przegląd kandydatów, lecz nie tworzy tych decyzji automatycznie. Tworzenie nowej sprawy od zera i zautomatyzowane zatwierdzanie planu nie zostały dodane. Sam wprowadzony opis nie jest dowodem gotowości do generowania.

Jeden następny krok: udostępnić zatwierdzoną izolowaną sesję WORK/HUMAN oraz syntetyczną sprawę z wymaganymi decyzjami, a następnie wykonać jeden odbiór w tym samym interfejsie: zapis danych → projekt istniejącym generatorem → walidacja → render → pobranie rzeczywistych DOCX i PDF. Jeśli dostęp nadal wymaga zablokowanego mechanizmu Issue #80 — STOP; bez obejścia i bez tworzenia nowego mechanizmu logowania w tej poprawce.

## Zachowany stan Issue #80

- LOGON SESSION CONTRACT: INVALID dla poprzednio badanej pary.
- LOGON LAUNCHER FIX: BLOCKED.
- A2 DELTA: PASS wyłącznie w wcześniej zatwierdzonym zakresie.
- DEPLOYMENT_GATE: BLOCKED.

Pakiety, checkpointy, approval, manifesty i dowody Issue #80 pozostawiono bez zmian. Nie powtarzano jego testów. Ten raport nie deklaruje GO-LIVE, SECURITY PASS ani zatwierdzenia deploymentu.
