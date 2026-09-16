# Stage 03 — odbiór i dowody

## Stan przed niezależnym review

Wejście: f80ac2efda722ff9a8a0ec1c986906f7c199a6bc, potwierdzone na main
lokalnie i zdalnie, CI Stage 02 SUCCESS. Macierz: 13-stage03-readiness.md.
Implementacja i jawne ograniczenia: 14-stage03-implementation.md.

Pełna regresja: **120 PASS, 0 failures/errors/skips, 100.023 s**. W tym
109 dotychczasowych testów i 11 testów Stage 03. Pakiet: **62 kontrole PASS,
61 JSON**. Schematy historyczne, baseline i Core migration.sql niezmienione.
Raport `stage03-status.json` wskazuje HEAD w chwili testu, gdy implementacja
była w working tree; rzeczywisty zestaw testowanych plików identyfikują
`tested_sources`. Nie przypisujemy tych testów kodowi samego bazowego SHA.
Historyczne raporty Stage 01/02 nie zostały nadpisane.

| Wymaganie | Dowód lokalny |
|---|---|
| S03-01: bytes/trwałość/atomowość | versions_original_bytes_and_process_restart; atomic_rollback_and_concurrent_version_conflict; golden_source_snapshot_acceptance_and_retention |
| S03-02: wersje/piny/replay | 12 niezależnych kategorii, dwie wersje, konflikt zmienionej treści; exact_version_pin_limits_and_revoked_capability |
| S03-03: migracje/historyczne dane | upgrade_preserves_legacy_payloads_and_detects_ledger_drift; migration_rollback_and_unknown_version; stare testy nieznanego kontraktu |
| S03-04: izolacja/uprawnienia | isolation_authorization_and_sql_rls; corruption_and_runtime_immutability; Stage 02 RLS/replay/auth regression |
| S03-05: retencja/hold/tombstone | retention_hold_tombstone_and_no_resurrection; unknown_policy_and_future_deadline_fail_closed; golden z zachowaniem historycznej akceptacji |
| S03-06: backup/restore | backup_restore_preserves_raw_history_and_replay: rzeczywisty pg_dump/pg_restore, porównanie wszystkich tabel, replay, bytes, hold i tombstone, odmowa złego hasha |
| S03-07: DoD | lokalne testy wykonane; niezależny review, publikacja, CI końcowego SHA i merge pozostają wymagane |

Pierwszy przebieg ukierunkowany wykrył przekroczenie zakresu datetime przez
strefę serwera oraz błędną ścieżkę pg_dump. Naprawiono przed pierwszym review;
9/9 testów przeszło, następnie dodano dwa testy i wykonano 120/120 regresji.
Nie są to iteracje naprawcze po niezależnym review: wykorzystano **0 z 3**.

**Stage 03 closed: NO na tym punkcie kontrolnym.** Końcowe rozstrzygnięcie
wymaga dokładnego zamrożonego SHA i osobnych dowodów review/CI. Późniejsze
raporty odbioru zastępują ten status, nie historyczne wyniki wykonania.
