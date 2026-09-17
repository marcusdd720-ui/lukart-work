# Stage 04 — odbiór implementacji

Aktualny odbiór po review, CI i merge: [22-stage04-closure.md](22-stage04-closure.md).
Poniżej zachowano historyczny punkt kontrolny przed review.

Punkt wejścia: `f69ed44211f306e873617d08427588db8214be8f`, Stage 03 GO.
Macierz zakresu: 18-stage04-readiness.md. Interfejs: 19-stage04-implementation.md.

## Dowody i pokrycie

| Wymaganie | Test / kontrola |
|---|---|
| S04-01 | golden_original_history_approval_and_heads_unchanged; deleted_original_or_result_cannot_be_replayed; niezmienione historyczne schematy i Core SQL |
| S04-02 | text_quotes_offsets_dates_amounts_parties_never_confirmed; docx_table_paragraphs_and_original_preserved; email_multipart_and_untrusted_headers; pdf_text_page_and_scan_outcomes |
| S04-03/04 | dokładne cytaty/offsety; contract_rejects_forged_quote_hash_status_and_extra; golden porównuje wszystkie tabele Core przed i po |
| S04-05 | retry_new_run_actor_conflict_and_source_binding; process_restart_exact_output; concurrency_atomic_rollback_and_closed_case z odrębnymi authority/połączeniami |
| S04-06 | scope_authentication_ai_revocation_and_reserved_namespace; malformed_encrypted_xml_entities_and_size_fail_closed, w tym UTF-16 DTD; worker_timeout_and_bad_output_are_safe |
| S04-07 | pełny runner Stage 04, verify_package.py, metaschema JSON Schema 2020-12, manifest i diff; review/CI/merge jako osobne bramki |

Testy focused: 15 PASS po poprawieniu wywołania CloseCase w teście (brak target).
Następnie wzmocniono test współbieżności o osobne authority/połączenia oraz
testy o same-tenant cross-case i DTD UTF-16, objęte pełną regresją.
Pierwsza pełna regresja: 136 testów, 135 PASS, 1 ERROR środowiskowy
POSTGRES_BACKUP_TOOL_UNAVAILABLE w historycznym teście Stage 03. Sandbox
uniemożliwiał użycie zewnętrznego pg_dump; wymagane powtórzenie z dostępem
do narzędzi. Nie zaliczono tego wykonania jako odbioru.

Powtórna pełna regresja: **136 PASS, 0 failures/errors/skips, 104.344 s**,
w tym 121 dotychczasowych testów i 15 Stage 04. Rzeczywisty backup/restore
również PASS; wykonanie lokalne Python 3.12.14, PostgreSQL testowy.

Bieżący wynik pełnego wykonania: reports/stage04-status.json oraz
reports/stage04-unittest.txt. `executed_commit` wskazuje HEAD podczas testu;
przed pierwszym commitem kod Stage 04 jest w working tree, a rzeczywiste pliki
identyfikuje `tested_sources`. Nie przypisujemy nowych testów bazowemu SHA.
Runner sam nie zamyka etapu (`stage_04_closed=false`); zamknięcie wymaga review,
CI i merge dokładnego commita. Historia Stage 01–03 pozostaje niezmieniona.

verify_package.py: 63 kontrole PASS, 62 pliki JSON. Dodatkowo niezależny
jsonschema 4.26.0 Draft202012Validator: 60 metaschematów PASS (pozostałe
2 JSON to lifecycle i relacje, nie schematy). Raport z hashami:
reports/stage04-schema-validation.json. Nie jest to walidacja prawdziwości
treści ani zgodności wizualnej PDF/DOCX.

**Przed review: Stage 04 closed: NO.** Wynik końcowy ustala raport zamknięcia
wraz z dowodami dokładnego końcowego SHA. Pierwszy review jeszcze niewykonany;
limit trzech iteracji naprawczych po nim pozostaje w całości dostępny.
