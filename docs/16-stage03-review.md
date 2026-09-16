# Stage 03 — niezależny review i iteracje naprawcze

## Pierwszy review

Osobny subagent `stage03_independent_review` ocenił zamrożony commit
`4df0160088c595265e97ec96acb4726069860df6` względem wejścia f80ac2e.
Werdykt: **NO-GO do merge**. Przejrzał zakres, ADR, docs 13–15, storage,
retencję, backup, migracje, integrację Core, testy i zmiany kontraktów.
Nie wskazał innych blockerów poza poniższymi. Zachowanie historycznych
kontraktów i granica Stage 03 zostały ocenione jako zgodne z dokumentacją.

| Finding | Problem i dowód | Naprawa w iteracji 1 |
|---|---|---|
| S03-R1-01, P1 | migrations.py:27–46: adopcja sprawdzała kolumny i flagi RLS, lecz mogła zaakceptować osłabione policies/triggery/constraints i zapisać ledger poprawnego SQL | porównanie rzeczywistego katalogu z pustym wzorcem utworzonym transakcyjnie z opublikowanego SQL; typy, constraints, policies, triggery i funkcje; odmowa dryfu bez ledgeru |
| S03-R1-02, P1 | workflow:38–39 i integrity:10–12: CI push 35088578745 i PR 35088621185 FAIL na MANIFEST_COVERAGE po instalacji pakietu | odczytowa kontrola czystego checkout przed pip; nie wyłącza kontroli nieznanych plików repo |

Reproduktor recenzenta nie został wykonany: Python odmówił dostępu, oczekującą
eskalację przerwano. Główny agent poprosił o zakończenie przedłużającej się
oceny na zebranych dowodach. Finding migracji jest analizą statyczną;
120 PASS/62 package to dowody głównego agenta, nie wykonanie recenzenta.
Nie przedstawiamy przerwanego wykonania jako pozytywnego review.

## Iteracja naprawcza 1 z maksymalnie 3

Dedykowana regresja `test_review_r1_adoption_rejects_weakened_legacy_schema`
sprawdza wyłączony immutable trigger, dodatkową permissive policy, brak FK
i zmienioną funkcję immutable. Każdy przypadek musi zostać odrzucony bez
ledgeru. Poprawny schemat nadal jest przyjmowany; raw history/URN/hash/
approval pozostają identyczne w osobnym teście upgrade.

Nowy zamrożony commit wymaga re-review i SUCCESS CI własnego SHA. Bieżące
wyniki pełnej regresji zapisuje reports/stage03-status.json. Dotychczasowa
porażka CI nie jest ukrywana ani traktowana jako PASS.

Wynik iteracji 1: **121 testów PASS, 0 failures/errors/skips, 110.880 s**;
dwa testy ukierunkowane upgrade: PASS w 19.469 s. Pakiet: 62 kontrole/61 JSON
PASS. Wykorzystano 1 z 3 iteracji. Odbiór nadal wymaga re-review i CI.
