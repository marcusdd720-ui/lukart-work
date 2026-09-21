# Stage 11 — kryteria odbioru

Status: PENDING FINAL EXACT-SHA EVIDENCE

Ten dokument definiuje kryteria. Nie nadaje sam statusu CLOSED.

Stage 11 jest gotowy do zamknięcia dopiero po spełnieniu wszystkich warunków:

1. `tests/test_stage11.py` istnieje i każdy test rzeczywiście się wykonuje.
2. Brak SKIP.
3. Identyczny input/profile/renderer daje identyczny DOCX.
4. Identyczny input/profile/renderer daje identyczny PDF.
5. Fresh-process reproduction daje identyczne hashe.
6. Polski zestaw znaków jest obsługiwany przez dokładny font.
7. Zmiana SemanticDocument poza związanym Draft jest blokowana.
8. Cross-case i missing-ref są blokowane.
9. Attachment provenance jest jednoznaczny.
10. DOCX nie zawiera makr ani zewnętrznych relacji.
11. PDF osadza font i nie zawiera aktywnej zawartości.
12. RenderReceipt wiąże semantic/model/layout/artifact identity.
13. Pełna regresja Stage 01–10 przechodzi.
14. Exact-SHA CI Stage 10 przechodzi.
15. Exact-SHA CI Stage 11 przechodzi.
16. Niezależny review exact-SHA: P0=0, P1=0.
17. Merge do `main` jest wykonany bez obejścia polityki.
18. Post-merge Stage 10: SUCCESS.
19. Post-merge Stage 11: SUCCESS.
20. Dopiero wtedy można zapisać `Stage 11 CLOSED`.

Końcowy SHA, run IDs i review receipt są zapisywane przy PR/finalnym odbiorze,
aby nie tworzyć samoodnoszącego się commita raportowego po zamrożeniu kandydata.
