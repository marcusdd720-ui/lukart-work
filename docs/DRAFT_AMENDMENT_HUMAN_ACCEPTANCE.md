# Edytor projektu i odbiór HUMAN

## Zapis poprawki

Istniejący transport `execute_core` przyjmuje operację `AmendDraft` w
`CoreRequest:1.0.0`. Jej `data` jest sprawdzane kontraktem `AmendDraft:1.0.0`:

```json
{
  "contract": "urn:lukart:work:AmendDraft:1.0.0",
  "draft_hash": "SHA-256 dokładnie odczytanego Draft",
  "edits": [{"statement_id": "UUID istniejącego zdania", "text": "Nowa treść"}]
}
```

Powyższy schemat objaśniający zawiera opisy zamiast identyfikatorów i nie jest
żądaniem do wykonania. Formularz pobiera prawdziwe wartości przez `query_draft`.
Zapis wymaga rzeczywistego uwierzytelnionego HUMAN, uprawnienia `AmendDraft`,
tego samego tenant/CASE, aktualnej rewizji, hash i sekwencji sprawy. SERVICE i AI
są odrzucani na serwerze. Nie przyjmuje się zmian źródeł, typów zdań, odwołań,
cytowań, aktora, statusu ani innych metadanych. Edytować można tekst istniejących
zdań; dodanie nowych faktów, źródeł i zdań wymaga normalnych wcześniejszych usług
CASE i nowego planu/generowania, a nie ukrytej zmiany źródeł w edytorze.

Każda poprawka tworzy nowy identyfikator Draft (PLANNED -> GENERATED), a
`supersedes` wskazuje dokładny poprzedni projekt. Poprzednik pozostaje niezmienny.
W danej linii historii jeden poprzednik ma jedną poprawkę; równoległy zapis
przegrywa przez sekwencję albo STALE. Ponowienie identycznego polecenia jest
idempotentne, także po restarcie; tożsamość aktora należy do hasha ponowienia.

Osobny niezmienny `HumanDraftAmendmentReceipt` zapisuje aktora, czas, uzasadnienie,
hash poprzednika, rezultat tekstowy i zmiany. `provenance.tool` nowej rewizji
GENERATED wiąże hash tego pokwitowania. Oryginalny ReproductionManifest opisuje
pochodzenie projektu bazowego; pozostaje zachowany wraz z oryginalnym trace AI.
Nie tworzy się fikcyjnego AIResult, wywołania modelu ani ModelExecutionReceipt.
Przy walidacji i renderowaniu sprawdzany jest cały łańcuch poprawek.

Nie przenosi się wcześniejszego przeglądu, walidacji ani akceptacji na nowy Draft.
Po zapisaniu należy jawnie ocenić obszary przeglądu HUMAN, wysłać go, wykonać
walidację i dopiero wtedy RenderDraft. Zapis poprawki i render nie nadają FINAL.
Podgląd PDF i pobranie DOCX/PDF korzystają z istniejących kontrolowanych odczytów.

`DraftEditorQuery:1.0.0` jest odczytem wymagającym istniejących uprawnień
`GetRevision` i `GetCaseHead`. Zwraca dokładny hash projektu, sekwencję i piny
potrzebne do przygotowania jawnych poleceń. Uprawnienia odczytu nie nadają praw
do zapisu, przeglądu, walidacji, renderowania ani zatwierdzania.

## Konfiguracja rzeczywistego HUMAN

Dotychczasowy lokalny host jest SERVICE/read-only. Nie staje się hostem HUMAN
przez zmianę nazwy lub rodzaju aktora. Nie zmieniaj jego DSN ani uprawnień,
nie restartuj go tylko w celu ponowienia zakończonych kontroli.

Gotowy punkt konfiguracji: `examples/human_case_operator_host.py`. Administrator
przekazuje poza repozytorium dwa zaufane prywatne pliki Python:

1. `LUKART_TRUSTED_CASE_HOST`: funkcja `build_operator()` składa zatwierdzone
   rzeczywiste komponenty jak w runbooku operatora: ograniczony runtime PostgreSQL
   z zapisem i storage, istniejący schemat, politykę retencji, zatwierdzony profil
   dokumentu, pakietu i drafting oraz prawidłowo skonfigurowane lokalne OCR.
   Nie używa fixture/testów ani profili syntetycznych do rzeczywistych spraw.
2. `LUKART_HUMAN_IDENTITY_ADAPTER`: `authenticate_human(operator)` rzeczywiście
   uwierzytelnia człowieka według istniejącej ewidencji administratora i zwraca
   `Principal` z prawdziwym HUMAN, tenant/CASE i jawnie nadanymi uprawnieniami.
   `deliver_capability_privately(token)` przekazuje sesję prywatnie na urządzeniu
   operatora, bez logowania i bez wysyłania do czatu. Adapter nie może zwracać
   domyślnego, syntetycznego ani przemianowanego aktora SERVICE.

Nie ma publicznej operacji nadania uprawnień ani logowania administratora przez
JSON. Ten plik nie zastępuje źródła tożsamości. Brak zatwierdzonego adaptera lub
uprawnienia blokuje uruchomienie; nie należy go zastępować pozornym adapterem.
Konfiguracja nie wykonuje migracji ani zmian ról bazy. Przykład uruchomienia po
powiązaniu obu rzeczywistych ścieżek przez administratora:

```powershell
python -B -X utf8 -m lukart_work.operator_host --config examples/human_case_operator_host.py --port 8766
```

Port 8766 pozwala zachować istniejący panel 8765 bez restartu. Uruchomienie
nowej konfiguracji/wdrożenie wymaga właściwej zgody. Samo przygotowanie pliku
nie poświadcza rzeczywistego uwierzytelnienia ani odbioru produktu.

Zakresy uprawnień są osobne: CreateCase, RegisterSource, działania ingestion,
ReviewCandidate i normalne decyzje fakty/dowody/plan/snapshot, GenerateDocument,
AmendDraft, RecordValidationReview, ValidateDraft, RenderDraft oraz wymagane
odczyty. Administrator nadaje tylko rzeczywiście zatwierdzone działania w
konkretnej sprawie. Nie nadawaj automatycznie praw FINAL ani uprawnień globalnych.
Rzeczywisty provider musi dostarczać wynik dla dokładnego request/snapshot;
brak wyniku blokuje generowanie, bez płatnego lub fikcyjnego zastępstwa.

## Jedna końcowa czynność operatora

Gdy uprawniona konfiguracja jest uruchomiona, operator przechodzi odbiór w panelu:
tworzy syntetyczną sprawę, dodaje przygotowany syntetyczny skan, sprawdza OCR i
kandydatów, wykonuje wymagane weryfikacje/plan, generuje projekt, poprawia tekst
w edytorze i jawnie zapisuje nowy Draft, ocenia go, uruchamia walidację oraz
DOCX/PDF i pobiera oba pliki. Czynność pozostaje rzeczywistym odbiorem HUMAN;
nie zastępują jej testowe konta ani wcześniejsze syntetyczne wyniki.

Jeżeli administrator nie ma rzeczywistego adaptera/grantu, jedyna wymagana
czynność przygotowawcza to wskazanie zatwierdzonej konfiguracji albo jej
ustanowienie w swoim istniejącym systemie uprawnień. Nie przesyłać sekretów.
