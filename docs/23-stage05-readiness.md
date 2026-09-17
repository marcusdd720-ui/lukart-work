# Stage 05 — Facts / Evidence: gotowość i macierz

Wejście lokalne/zdalne main: `b4bb235487edef5af18dc83c3430839dad92de6f`.
Potwierdzone git ls-remote i API. CI main 35182284035: SUCCESS dla tego SHA.
Stage 04: GO, 136 PASS, niezależny review kodu i finalnego SHA GO (zadanie
bieżące, PR #2 oraz raporty 18–22). Drzewo czyste, brak AGENTS.md w repo i
katalogach nadrzędnych. Baseline, spec/ADR, AGR-01-001–007 oraz raporty Stage 04
przeczytane w bieżącym zadaniu. Main protected=false, brak required checks;
ustawienia pozostają bez zmian. Egg-info w głównym checkout pozostaje nietknięty.

**Gotowość implementacji: GO. Odbiór Stage 05 jeszcze niewykonany.**

## Zakres i decyzje wykonawcze

Baseline §7, §13, §23, §26–28, §35, §42, §47 i §50 określa Facts/Evidence.
Stage 02 ma podstawowe Add/Edit/Review/ConfirmFact i AddEvidence, a Stage 04
immutable kandydatów. Stage 05 łączy je kontrolowanym procesem człowieka.

Nowy FactEvidenceRequest:1.0.0, receipt przeglądu i projekcja macierzy nie
zmieniają historycznych CoreRequest, Fact, Evidence, Decision ani lifecycle.
Nowy serwis korzysta ze wspólnego mechanizmu transakcji/CAS/idempotencji/
audytu/outbox Core. Bez nowego SQL, bez ukrytego rejestrowania dowolnych encji.
Oryginał i ekstrakcja pozostają niezmienne. Akceptacja kandydata tworzy
CANDIDATE Fact i REGISTERED Evidence, nigdy CONFIRMED/ACCEPTED.

Odrzucony kandydat może zostać jawnie ponownie oceniony z oczekiwaną wersją
przeglądu; receipt poprzedniej oceny pozostaje. Raz przyjęty kandydat nie
tworzy ponownie encji — dalsze decyzje odbywają się na ich lifecycle.
Osobna ludzka FACT_ACCEPTANCE odnosi się do dokładnej poprzedniej rewizji.
Przyjęcie dowodu jest ludzką, audytowaną komendą; nie oznacza sądowego
dopuszczenia ani VERIFIED authenticity. Nie dodajemy fikcyjnego typu Decision.

## Macierz wymagań i odbioru

| ID | Podstawa | Zakres | Kryterium/test |
|---|---|---|---|
| S05-01 | §7/13/26 | wybór przypiętego kandydata, ludzki review, receipt, atomowa promocja/odrzucenie | błędny pin/index/scope/kind denied; reject/reconsider zachowuje historię; zero automatycznych approvals |
| S05-02 | §23/26, Fact lifecycle | EXTRACTED/REVIEWED/CONFIRMED/DISPUTED/REJECTED, kontrolowana edycja i wiązanie dowodów | dozwolone przejścia; dokładna human Decision; stale/revoked/changed-content denied |
| S05-03 | Evidence invariant | REVIEWED/ACCEPTED/CHALLENGED/EXCLUDED, opis/authenticity | tylko HUMAN; bez podmiany source; accepted nie znaczy authenticity VERIFIED; niedozwolone przejścia denied |
| S05-04 | §23/35/42, ADR-02/06 | macierz aktualnych faktów/dowodów i użyć, oddzielny stan aktualności potwierdzenia | zmiana dowodu/cofnięcie approval/brak oryginału lub ekstrakcji sygnalizowane; historyczny Fact nieprzepisany; dependency invalidation |
| S05-05 | §27–28/36 | scope, runtime/RLS, CAS/replay, audit/outbox i trwałość | cross-tenant/case/AI/SERVICE write/revocation denied; concurrent CAS; rollback; restart |
| S05-06 | §47 i zasady Stage 04 | focused/full regression, package/schema/manifest/diff, review i CI exact SHA | zero errors/failures/skips; niezależny subagent; maks. 3 iteracje; merge i post-merge |

## Granice

Brak UI (Stage 13), OCR i nowych parserów, automatycznego rozumienia sprzeczności,
prawnej oceny dopuszczalności dowodu, generatora tekstu/renderingu/FINAL.
Macierz jest projekcją authoritative Core, nie drugim źródłem prawdy.
Historyczne approvals zachowują status historyczny; bieżąca przydatność jest
osobną oceną. Stary kontrakt Core nadal istnieje dla kompatybilności; nowe
operacje Stage 05 host kieruje do FactEvidenceService. Nie reinterpretujemy
starych zatwierdzeń według nowych warunków przyjmowania dowodów.
Bez Stage 06, deploymentu, ROS, produkcji, force push, sekretów i baz w Git.
Upoważnienie do commitów stage05:, publikacji, CI i merge po odbiorze wynika
z polecenia użytkownika „na zasadach Stage 04”.
