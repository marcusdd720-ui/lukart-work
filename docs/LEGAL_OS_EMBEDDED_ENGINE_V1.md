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
